"""Modelos ORM del módulo Accounts."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from src.shared.infrastructure.models import BaseModel, TimeStampedModel


class Company(BaseModel):
    """Tenant raíz. Todo dato del sistema cuelga de una empresa (RN-01)."""

    name = models.CharField(_("nombre"), max_length=150)
    slug = models.SlugField(_("identificador"), max_length=60, unique=True)
    tax_id = models.CharField(_("RUT / Tax ID"), max_length=30, blank=True)
    logo = models.ImageField(upload_to="companies/logos/", blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "companies"
        verbose_name = _("empresa")
        verbose_name_plural = _("empresas")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", User.Role.STUDENT)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra):
        extra.setdefault("role", User.Role.SUPERADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("El superusuario debe tener is_staff e is_superuser en True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """Usuario identificado por email, siempre asociado a una empresa."""

    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", _("Superadministrador")
        ADMIN = "ADMIN", _("Administrador")
        INSTRUCTOR = "INSTRUCTOR", _("Instructor")
        STUDENT = "STUDENT", _("Estudiante")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        verbose_name=_("empresa"),
    )
    email = models.EmailField(_("correo"), unique=True, db_index=True)
    first_name = models.CharField(_("nombre"), max_length=100)
    last_name = models.CharField(_("apellido"), max_length=100, blank=True)
    role = models.CharField(
        _("rol"), max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True
    )
    job_title = models.CharField(_("cargo"), max_length=120, blank=True)
    avatar = models.ImageField(upload_to="users/avatars/", blank=True, null=True)
    language = models.CharField(max_length=10, default="es")
    timezone = models.CharField(max_length=50, default="America/Santiago")
    phone = models.CharField(max_length=30, blank=True)

    is_active = models.BooleanField(_("activo"), default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        db_table = "users"
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
        ordering = ["first_name", "last_name"]
        indexes = [
            models.Index(fields=["company", "is_active"], name="idx_user_company_active"),
            models.Index(fields=["company", "role"], name="idx_user_company_role"),
        ]

    def __str__(self) -> str:
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name

    # ── Reglas de acceso (espejo del dominio, para uso en vistas) ──
    @property
    def is_admin(self) -> bool:
        return self.role in {self.Role.SUPERADMIN, self.Role.ADMIN}

    @property
    def can_manage_content(self) -> bool:
        return self.role in {self.Role.SUPERADMIN, self.Role.ADMIN, self.Role.INSTRUCTOR}

    def belongs_to(self, company_id) -> bool:
        return self.role == self.Role.SUPERADMIN or str(self.company_id) == str(company_id)


class UserGroup(BaseModel):
    """Grupo de usuarios para asignación masiva de capacitaciones."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, related_name="user_groups", blank=True)

    class Meta:
        db_table = "user_groups"
        verbose_name = _("grupo de usuarios")
        verbose_name_plural = _("grupos de usuarios")
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uq_group_company_name")
        ]

    def __str__(self) -> str:
        return self.name


class PasswordResetToken(BaseModel):
    """Token de un solo uso para recuperación de contraseña (RF-007)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_tokens")
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "password_reset_tokens"
        indexes = [models.Index(fields=["user", "used_at"], name="idx_reset_user_used")]

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class AuditLog(BaseModel):
    """Bitácora de acciones sensibles (RF-009, RF-083)."""

    class Action(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", _("Inicio de sesión")
        LOGIN_FAILED = "LOGIN_FAILED", _("Intento fallido")
        LOGOUT = "LOGOUT", _("Cierre de sesión")
        PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED", _("Solicitud de recuperación")
        PASSWORD_CHANGED = "PASSWORD_CHANGED", _("Cambio de contraseña")
        USER_CREATED = "USER_CREATED", _("Usuario creado")
        USER_UPDATED = "USER_UPDATED", _("Usuario actualizado")
        USER_DEACTIVATED = "USER_DEACTIVATED", _("Usuario desactivado")
        ROLE_CHANGED = "ROLE_CHANGED", _("Rol modificado")
        CONTENT_CREATED = "CONTENT_CREATED", _("Contenido creado")
        CONTENT_DELETED = "CONTENT_DELETED", _("Contenido eliminado")
        MATERIAL_UPLOADED = "MATERIAL_UPLOADED", _("Material cargado")
        EXAM_PUBLISHED = "EXAM_PUBLISHED", _("Examen publicado")
        INDEX_REBUILT = "INDEX_REBUILT", _("Índice reconstruido")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="audit_logs", null=True, blank=True
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = _("registro de auditoría")
        verbose_name_plural = _("registros de auditoría")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"], name="idx_audit_company_date"),
            models.Index(fields=["entity_type", "entity_id"], name="idx_audit_entity"),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.created_at:%Y-%m-%d %H:%M}"
