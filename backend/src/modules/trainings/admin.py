from django.contrib import admin

from .infrastructure.models import (
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


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


class MaterialInline(admin.TabularInline):
    model = Material
    extra = 0
    readonly_fields = ("status", "sha256", "size_bytes", "processed_at")


@admin.register(Training)
class TrainingAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "level", "status", "published_at", "created_at")
    list_filter = ("status", "level", "project")
    search_fields = ("title", "description")
    inlines = [ModuleInline]


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "training", "order")
    list_filter = ("training",)
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "type", "order", "duration_seconds", "is_mandatory")
    list_filter = ("type", "is_mandatory")
    inlines = [MaterialInline]


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename", "project", "type", "status",
        "duration_seconds", "partial_analysis", "processed_at",
    )
    list_filter = ("status", "type", "project")
    search_fields = ("original_filename", "summary")
    readonly_fields = ("sha256", "size_bytes", "mime_type", "processed_at")


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("material", "step", "status", "progress", "started_at", "finished_at")
    list_filter = ("status", "step")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "training", "status", "progress", "assigned_at", "completed_at")
    list_filter = ("status", "training__project")
    search_fields = ("user__email", "training__title")


admin.site.register([LessonProgress, Note, UploadSession])
