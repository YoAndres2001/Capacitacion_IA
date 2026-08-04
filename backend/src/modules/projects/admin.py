from django.contrib import admin

from .infrastructure.models import Project, ProjectMember, VectorCollection


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "code", "status", "created_at")
    list_filter = ("status", "company")
    search_fields = ("name", "code", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "role")
    list_filter = ("role",)


@admin.register(VectorCollection)
class VectorCollectionAdmin(admin.ModelAdmin):
    list_display = (
        "project", "status", "embedding_model", "dimension",
        "vector_count", "index_type", "version", "last_rebuilt_at",
    )
    list_filter = ("status", "embedding_model")
    readonly_fields = ("vector_count", "version", "last_rebuilt_at")
