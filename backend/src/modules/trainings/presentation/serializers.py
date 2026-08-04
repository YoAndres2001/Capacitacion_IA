"""Serializadores del módulo Trainings."""

from __future__ import annotations

from django.utils.text import slugify
from rest_framework import serializers

from src.modules.accounts.presentation.serializers import UserSerializer

from ..infrastructure.models import (
    Enrollment,
    Lesson,
    LessonProgress,
    Material,
    Module,
    Note,
    ProcessingJob,
    Training,
    UploadSession,
)


class MaterialSerializer(serializers.ModelSerializer):
    is_queryable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Material
        fields = [
            "id", "original_filename", "mime_type", "size_bytes", "type",
            "status", "error_code", "error_detail", "duration_seconds",
            "page_count", "language", "summary", "partial_analysis",
            "is_queryable", "processed_at", "created_at",
        ]
        read_only_fields = fields


class MaterialStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    step = serializers.CharField(allow_blank=True)
    progress = serializers.IntegerField()
    error_code = serializers.CharField(allow_blank=True)
    error_detail = serializers.CharField(allow_blank=True)


class ProcessingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingJob
        fields = ["id", "step", "status", "progress", "error", "started_at", "finished_at"]


class LessonSerializer(serializers.ModelSerializer):
    materials = MaterialSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "module", "title", "description", "type", "order",
            "duration_seconds", "is_mandatory", "content", "materials", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"module": {"required": False}}


class LessonBriefSerializer(serializers.ModelSerializer):
    material_status = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ["id", "title", "type", "order", "duration_seconds", "is_mandatory", "material_status"]

    def get_material_status(self, obj: Lesson) -> str | None:
        material = obj.materials.all().first()
        return material.status if material else None


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)
    lesson_count = serializers.IntegerField(source="lessons.count", read_only=True)

    class Meta:
        model = Module
        fields = ["id", "training", "title", "description", "order", "lessons", "lesson_count", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"training": {"required": False}}


class TrainingSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    created_by = UserSerializer(read_only=True)
    module_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)
    enrollment_count = serializers.IntegerField(read_only=True)
    can_be_published = serializers.SerializerMethodField()

    class Meta:
        model = Training
        fields = [
            "id", "project", "project_name", "title", "slug", "description",
            "level", "cover_image", "estimated_minutes", "status",
            "chat_enabled", "cross_material_search", "created_by",
            "module_count", "lesson_count", "enrollment_count",
            "can_be_published", "published_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_by", "published_at", "created_at", "updated_at"]

    def get_can_be_published(self, obj: Training) -> bool:
        return obj.can_be_published()

    def validate(self, attrs: dict) -> dict:
        title = attrs.get("title") or getattr(self.instance, "title", "")
        project = attrs.get("project") or getattr(self.instance, "project", None)
        if project is not None and title:
            slug = slugify(title)[:220]
            qs = Training.objects.filter(project=project, slug=slug)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                slug = f"{slug}-{Training.objects.filter(project=project).count() + 1}"
            attrs["slug"] = slug
        return attrs


class TrainingDetailSerializer(TrainingSerializer):
    """Árbol completo: módulos → lecciones → materiales."""

    modules = ModuleSerializer(many=True, read_only=True)

    class Meta(TrainingSerializer.Meta):
        fields = [*TrainingSerializer.Meta.fields, "modules"]


class ReorderSerializer(serializers.Serializer):
    order = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


# ── Materiales / carga ───────────────────────────────────────


class UploadSessionCreateSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1)
    mime_type = serializers.CharField(max_length=120, required=False, allow_blank=True)


class UploadSessionSerializer(serializers.ModelSerializer):
    total_chunks = serializers.IntegerField(read_only=True)
    received_count = serializers.SerializerMethodField()

    class Meta:
        model = UploadSession
        fields = [
            "id", "filename", "size_bytes", "chunk_size", "total_chunks",
            "received_count", "completed", "expires_at",
        ]

    def get_received_count(self, obj: UploadSession) -> int:
        return len(obj.received_chunks or [])


# ── Aprendizaje ──────────────────────────────────────────────


class LessonProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonProgress
        fields = [
            "id", "lesson", "completed", "position_seconds",
            "watched_seconds", "last_viewed_at", "completed_at",
        ]
        read_only_fields = ["id", "lesson", "completed_at"]


class ProgressUpdateSerializer(serializers.Serializer):
    position_seconds = serializers.IntegerField(min_value=0)
    watched_seconds = serializers.IntegerField(min_value=0, required=False)


class EnrollmentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    training_title = serializers.CharField(source="training.title", read_only=True)
    project_name = serializers.CharField(source="training.project.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id", "user", "training", "training_title", "project_name",
            "status", "progress", "assigned_at", "started_at",
            "completed_at", "due_date",
        ]
        read_only_fields = ["id", "user", "status", "progress", "assigned_at", "started_at", "completed_at"]


class MyTrainingSerializer(serializers.ModelSerializer):
    """Vista del estudiante: la capacitación con su propio avance."""

    training_id = serializers.UUIDField(source="training.id", read_only=True)
    title = serializers.CharField(source="training.title", read_only=True)
    description = serializers.CharField(source="training.description", read_only=True)
    level = serializers.CharField(source="training.level", read_only=True)
    cover_image = serializers.ImageField(source="training.cover_image", read_only=True)
    estimated_minutes = serializers.IntegerField(source="training.estimated_minutes", read_only=True)
    project_name = serializers.CharField(source="training.project.name", read_only=True)
    chat_enabled = serializers.BooleanField(source="training.chat_enabled", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id", "training_id", "title", "description", "level", "cover_image",
            "estimated_minutes", "project_name", "chat_enabled", "status",
            "progress", "assigned_at", "started_at", "completed_at", "due_date",
        ]


class AssignEnrollmentSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    group_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    due_date = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("user_ids") and not attrs.get("group_ids"):
            raise serializers.ValidationError("Indique al menos un usuario o un grupo.")
        return attrs


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ["id", "lesson", "content", "timestamp_seconds", "created_at", "updated_at"]
        read_only_fields = ["id", "lesson", "created_at", "updated_at"]


class CourseSearchResultSerializer(serializers.Serializer):
    material_id = serializers.UUIDField()
    material_title = serializers.CharField()
    material_type = serializers.CharField()
    lesson_id = serializers.UUIDField()
    excerpt = serializers.CharField()
    start_time = serializers.FloatField(allow_null=True)
    page = serializers.IntegerField(allow_null=True)
    rank = serializers.FloatField()
