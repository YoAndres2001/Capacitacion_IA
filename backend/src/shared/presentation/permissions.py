"""Permisos por rol y por pertenencia al tenant (RNF-21)."""

from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS


class Role:
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"


class _RolePermission(BasePermission):
    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, "role", None) in self.allowed_roles
        )


class IsSuperAdmin(_RolePermission):
    allowed_roles = (Role.SUPERADMIN,)


class IsAdmin(_RolePermission):
    """Administrador de empresa (o superadministrador)."""

    allowed_roles = (Role.SUPERADMIN, Role.ADMIN)
    message = "Se requiere rol de administrador."


class IsInstructor(_RolePermission):
    """Puede crear y editar contenido."""

    allowed_roles = (Role.SUPERADMIN, Role.ADMIN, Role.INSTRUCTOR)
    message = "Se requiere rol de instructor o administrador."


class IsStudent(_RolePermission):
    allowed_roles = (Role.STUDENT,)


class IsInstructorOrReadOnly(BasePermission):
    """Lectura para cualquier autenticado; escritura solo para instructor/admin."""

    message = "Solo instructores y administradores pueden modificar este recurso."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return getattr(user, "role", None) in {
            Role.SUPERADMIN,
            Role.ADMIN,
            Role.INSTRUCTOR,
        }


class InSameCompany(BasePermission):
    """
    Aísla tenants a nivel de objeto (RN-01).

    Devuelve 404 (no 403) desde las vistas, para no revelar la existencia del
    recurso en otra empresa: los querysets ya filtran por empresa.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if getattr(user, "role", None) == Role.SUPERADMIN:
            return True
        company_id = _company_of(obj)
        return company_id is None or company_id == getattr(user, "company_id", None)


class IsSelfOrAdmin(BasePermission):
    """El usuario puede operar sobre sí mismo; el admin, sobre cualquiera de su empresa."""

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if getattr(user, "role", None) in {Role.SUPERADMIN, Role.ADMIN}:
            return True
        return obj.pk == user.pk


def _company_of(obj) -> object | None:
    """Resuelve la empresa de un objeto recorriendo las relaciones habituales."""
    for attr in ("company_id", "project", "training", "module", "lesson", "exam", "enrollment"):
        if attr == "company_id" and hasattr(obj, "company_id"):
            return obj.company_id
        related = getattr(obj, attr, None)
        if related is not None:
            found = _company_of(related)
            if found is not None:
                return found
    return None
