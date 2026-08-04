"""Contrato base de los casos de uso (capa de aplicación)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class UseCase(ABC, Generic[TInput, TOutput]):
    """
    Un caso de uso = una intención del negocio = una única responsabilidad (SRP).

    Recibe un DTO de entrada, orquesta entidades y puertos, y devuelve un DTO de
    salida. No conoce HTTP, ni el ORM, ni el proveedor de IA.
    """

    @abstractmethod
    def execute(self, data: TInput) -> TOutput:  # pragma: no cover - contrato
        raise NotImplementedError

    def __call__(self, data: TInput) -> TOutput:
        return self.execute(data)
