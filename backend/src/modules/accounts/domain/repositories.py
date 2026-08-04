"""Puertos de persistencia del módulo Accounts (interfaces del dominio)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.domain.value_object import Email

from .entities import Company, User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: Email) -> User | None: ...

    @abstractmethod
    def exists_email(self, email: Email) -> bool: ...

    @abstractmethod
    def save(self, user: User) -> User: ...

    @abstractmethod
    def list_by_company(self, company_id: UUID) -> list[User]: ...


class CompanyRepository(ABC):
    @abstractmethod
    def get_by_id(self, company_id: UUID) -> Company | None: ...

    @abstractmethod
    def get_by_slug(self, slug: str) -> Company | None: ...

    @abstractmethod
    def save(self, company: Company) -> Company: ...
