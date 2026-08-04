"""Modelos ORM del módulo Projects (aplicaciones de la empresa)."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from src.modules.accounts.infrastructure.models import Company, User
from src.shared.infrastructure.managers import TenantManager
from src.shared.infrastructure.models import BaseModel, BaseSoftDeleteModel


class Project(BaseSoftDeleteModel):
    """
    Aplicación o producto sobre el que se capacita (ERP, WMS, CRM, Portal).

    Cada proyecto posee su propio conocimiento: una colección vectorial FAISS
    aislada (RN-02).
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Activo")
        ARCHIVED = "ARCHIVED", _("Archivado")

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(_("nombre"), max_length=150)
    slug = models.SlugField(_("identificador"), max_length=60)
    code = models.CharField(_("código"), max_length=30, blank=True)
    description = models.TextField(_("descripción"), blank=True)
    color = models.CharField(max_length=9, default="#1976d2")
    icon = models.CharField(max_length=40, default="apps")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    objects = TenantManager()

    class Meta:
        db_table = "projects"
        verbose_name = _("proyecto")
        verbose_name_plural = _("proyectos")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_project_slug",
            )
        ]
        indexes = [models.Index(fields=["company", "status"], name="idx_project_company_status")]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class ProjectMember(BaseModel):
    """Responsables del proyecto (instructores y administradores asignados)."""

    class Role(models.TextChoices):
        OWNER = "OWNER", _("Responsable")
        EDITOR = "EDITOR", _("Editor")
        VIEWER = "VIEWER", _("Lector")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EDITOR)

    class Meta:
        db_table = "project_members"
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="uq_project_member")
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.project} ({self.role})"


class VectorCollection(BaseModel):
    """
    Metadatos del índice FAISS de un proyecto.

    La fuente de verdad de los datos son los `chunks` en PostgreSQL; este
    registro solo describe el índice y permite detectar cambios de modelo
    que obliguen a reconstruir (RN-10).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pendiente")
        READY = "READY", _("Listo")
        REBUILDING = "REBUILDING", _("Reconstruyendo")
        ERROR = "ERROR", _("Error")

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="vector_collection"
    )
    index_path = models.CharField(max_length=500)
    embedding_model = models.CharField(max_length=120, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    dimension = models.PositiveIntegerField(default=0)
    vector_count = models.PositiveIntegerField(default=0)
    index_type = models.CharField(max_length=40, default="FlatIP")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    last_rebuilt_at = models.DateTimeField(null=True, blank=True)
    error_detail = models.TextField(blank=True)

    class Meta:
        db_table = "vector_collections"
        verbose_name = _("colección vectorial")
        verbose_name_plural = _("colecciones vectoriales")

    def __str__(self) -> str:
        return f"Índice de {self.project.name} ({self.vector_count} vectores)"

    def mark_ready(self, *, count: int, dimension: int, model: str, provider: str) -> None:
        self.status = self.Status.READY
        self.vector_count = count
        self.dimension = dimension
        self.embedding_model = model
        self.provider = provider
        self.version += 1
        self.save(
            update_fields=[
                "status", "vector_count", "dimension", "embedding_model",
                "provider", "version", "updated_at",
            ]
        )

    def needs_full_rebuild(self, *, model: str, dimension: int) -> bool:
        """Cambiar el modelo de embeddings o su dimensión invalida el índice."""
        if not self.embedding_model:
            return False
        return self.embedding_model != model or (self.dimension and self.dimension != dimension)
