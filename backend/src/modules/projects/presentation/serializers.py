from __future__ import annotations

from django.utils.text import slugify
from rest_framework import serializers

from src.modules.accounts.infrastructure.models import User
from src.modules.accounts.presentation.serializers import UserSerializer

from ..infrastructure.models import Project, ProjectMember, VectorCollection


class VectorCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VectorCollection
        fields = [
            "id", "status", "embedding_model", "provider", "dimension",
            "vector_count", "index_type", "version", "last_rebuilt_at", "error_detail",
        ]
        read_only_fields = fields


class ProjectMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user", write_only=True
    )

    class Meta:
        model = ProjectMember
        fields = ["id", "user", "user_id", "role", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    training_count = serializers.IntegerField(read_only=True)
    material_count = serializers.IntegerField(read_only=True)
    vector_collection = VectorCollectionSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "code", "description", "color", "icon",
            "status", "training_count", "material_count", "vector_collection",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs: dict) -> dict:
        request = self.context["request"]
        # En un PATCH parcial puede no venir el nombre: se conserva el del proyecto
        # para no regenerar el slug a partir de una cadena vacía.
        name = attrs.get("name") or (self.instance.name if self.instance else "")
        slug = attrs.get("slug") or slugify(name)
        attrs["slug"] = slug

        qs = Project.objects.filter(company_id=request.user.company_id, slug=slug)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"slug": "Ya existe un proyecto con este identificador en la empresa."},
                code="PROJECT_SLUG_TAKEN",
            )
        return attrs


class ProjectStatsSerializer(serializers.Serializer):
    trainings = serializers.IntegerField()
    published_trainings = serializers.IntegerField()
    materials = serializers.IntegerField()
    materials_available = serializers.IntegerField()
    materials_processing = serializers.IntegerField()
    materials_error = serializers.IntegerField()
    chunks = serializers.IntegerField()
    vectors = serializers.IntegerField()
    enrolled_users = serializers.IntegerField()
