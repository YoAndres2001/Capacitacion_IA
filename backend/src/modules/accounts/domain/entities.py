"""Entidades del módulo Accounts (Python puro, sin Django)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.shared.domain.entity import AggregateRoot
from src.shared.domain.exceptions import BusinessRuleViolation
from src.shared.domain.value_object import Email, Slug


class Role(StrEnum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

    @property
    def can_manage_users(self) -> bool:
        return self in {Role.SUPERADMIN, Role.ADMIN}

    @property
    def can_manage_content(self) -> bool:
        return self in {Role.SUPERADMIN, Role.ADMIN, Role.INSTRUCTOR}

    @property
    def is_staff_like(self) -> bool:
        return self is not Role.STUDENT


@dataclass(kw_only=True)
class Company(AggregateRoot):
    name: str
    slug: Slug
    tax_id: str = ""
    is_active: bool = True
    settings: dict = field(default_factory=dict)

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()


@dataclass(kw_only=True)
class User(AggregateRoot):
    email: Email
    first_name: str
    last_name: str = ""
    role: Role = Role.STUDENT
    company_id: UUID | None = None
    job_title: str = ""
    language: str = "es"
    timezone: str = "America/Santiago"
    is_active: bool = True
    last_login: datetime | None = None

    def __post_init__(self) -> None:
        if self.role is not Role.SUPERADMIN and self.company_id is None:
            raise BusinessRuleViolation(
                "Todo usuario que no sea superadministrador debe pertenecer a una empresa."
            )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def belongs_to(self, company_id: UUID) -> bool:
        return self.role is Role.SUPERADMIN or self.company_id == company_id

    def can_manage_project(self, project_company_id: UUID) -> bool:
        return self.role.can_manage_content and self.belongs_to(project_company_id)

    def change_role(self, new_role: Role, *, actor: User) -> None:
        if not actor.role.can_manage_users:
            raise BusinessRuleViolation("Solo un administrador puede cambiar roles.")
        if new_role is Role.SUPERADMIN and actor.role is not Role.SUPERADMIN:
            raise BusinessRuleViolation(
                "Solo un superadministrador puede otorgar el rol de superadministrador."
            )
        self.role = new_role
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()
