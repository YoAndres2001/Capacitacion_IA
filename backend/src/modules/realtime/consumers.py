"""
Consumidores WebSocket · se ejecutan SOLO en el contenedor `websocket`.

Cumplen la restricción del proyecto: ningún WebSocket corre dentro del
contenedor principal de Django. La comunicación con el backend y los workers
es indirecta, a través del channel layer de Redis.
"""

from __future__ import annotations

import json
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from src.shared.infrastructure.logging import get_logger

logger = get_logger("realtime")


class PingConsumer(AsyncJsonWebsocketConsumer):
    """Sonda de salud del contenedor de tiempo real."""

    async def connect(self) -> None:
        await self.accept()
        await self.send_json({"type": "pong", "service": "websocket"})

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        await self.send_json({"type": "pong", "echo": content})


class AuthenticatedConsumer(AsyncJsonWebsocketConsumer):
    """Base: rechaza cualquier conexión sin JWT válido."""

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)  # 4401: no autenticado
            return
        self.user = user
        await self.post_authenticate()

    async def post_authenticate(self) -> None:  # pragma: no cover - lo implementan las subclases
        await self.accept()


class MaterialStatusConsumer(AuthenticatedConsumer):
    """
    Estado de procesamiento del material en vivo (HU-021).

    Recibe los eventos que publican los workers de ingesta en el grupo
    `material.<id>`.
    """

    async def post_authenticate(self) -> None:
        self.material_id = self.scope["url_route"]["kwargs"]["material_id"]

        if not await self._can_access(self.user, self.material_id):
            await self.close(code=4403)  # 4403: sin permiso
            return

        self.group_name = f"material.{self.material_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        snapshot = await self._snapshot(self.material_id)
        if snapshot:
            await self.send_json({"type": "status.changed", **snapshot})

    async def disconnect(self, code) -> None:
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    # ── Handlers del channel layer ───────────────────────────
    async def material_status(self, event: dict[str, Any]) -> None:
        await self.send_json({**event, "type": "status.changed"})

    async def domain_event(self, event: dict[str, Any]) -> None:
        await self.send_json({**event, "type": "status.changed"})

    # ── Consultas a la BD ────────────────────────────────────
    @database_sync_to_async
    def _can_access(self, user, material_id) -> bool:
        from src.modules.trainings.infrastructure.models import Enrollment, Material

        material = (
            Material.objects.select_related("project", "lesson__module__training")
            .filter(id=material_id)
            .first()
        )
        if material is None or material.project.company_id != user.company_id:
            return False
        if user.can_manage_content:
            return True
        return Enrollment.objects.filter(
            user=user, training_id=material.lesson.module.training_id
        ).exists()

    @database_sync_to_async
    def _snapshot(self, material_id) -> dict[str, Any] | None:
        from src.modules.trainings.infrastructure.models import Material

        material = Material.objects.filter(id=material_id).first()
        if material is None:
            return None
        job = material.processing_jobs.first()
        return {
            "material_id": str(material.id),
            "status": material.status,
            "step": job.step if job else "",
            "progress": job.progress if job else (100 if material.is_queryable else 0),
            "error_code": material.error_code or None,
        }


class ChatConsumer(AuthenticatedConsumer):
    """
    Chat RAG con respuesta en streaming (RF-049).

    El caso de uso corre en un hilo (`database_sync_to_async`) y publica cada
    token al socket mediante el callback `on_token`.
    """

    async def post_authenticate(self) -> None:
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]

        if not await self._owns_session(self.user, self.session_id):
            await self.close(code=4403)
            return

        self.group_name = f"chat.{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready", "session_id": str(self.session_id)})

    async def disconnect(self, code) -> None:
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        if content.get("type") != "question":
            await self.send_json({"type": "error", "message": "Tipo de mensaje no soportado."})
            return

        question = (content.get("content") or "").strip()
        if not question:
            await self.send_json({"type": "error", "message": "La pregunta está vacía."})
            return

        await self.send_json({"type": "thinking"})

        try:
            result = await self._answer(question, content.get("level", "intermediate"))
        except Exception as exc:
            logger.exception("Fallo al responder por WebSocket")
            await self.send_json(
                {
                    "type": "error",
                    "code": getattr(exc, "code", "AI_ERROR"),
                    "message": getattr(exc, "message", "No se pudo generar la respuesta."),
                }
            )
            return

        await self.send_json(
            {
                "type": "answer.done",
                "session_id": str(self.session_id),
                "message_id": str(result["message_id"]),
                "content": result["content"],
                "grounded": result["grounded"],
                "citations": result["citations"],
            }
        )

    async def token(self, event: dict[str, Any]) -> None:
        await self.send_json({"type": "token", "content": event.get("content", "")})

    # ── Ejecución del caso de uso ────────────────────────────
    @database_sync_to_async
    def _answer(self, question: str, level: str) -> dict[str, Any]:
        from asgiref.sync import async_to_sync

        from src.modules.ai.application.use_cases.answer_question import (
            AnswerInput,
            AnswerQuestionUseCase,
        )
        from src.modules.ai.presentation.views import build_retriever
        from src.shared.container import get_llm

        layer = self.channel_layer
        group = self.group_name

        def emit(chunk: str) -> None:
            async_to_sync(layer.group_send)(group, {"type": "token", "content": chunk})

        result = AnswerQuestionUseCase(
            llm=get_llm(), retriever_factory=build_retriever
        ).execute(
            AnswerInput(
                session_id=self.session_id,
                question=question,
                user_id=self.user.id,
                level=level,
                on_token=emit,
            )
        )

        return {
            "message_id": result.message_id,
            "content": result.content,
            "grounded": result.grounded,
            "citations": [
                {
                    "chunk_id": str(citation.chunk_id),
                    "material_id": str(citation.material_id),
                    "label": citation.label,
                    "start_time": citation.start_time,
                    "page": citation.page,
                    "score": citation.score,
                }
                for citation in result.citations
            ],
        }

    @database_sync_to_async
    def _owns_session(self, user, session_id) -> bool:
        from src.modules.ai.infrastructure.models import ChatSession

        return ChatSession.objects.filter(id=session_id, user=user).exists()


class NotificationConsumer(AuthenticatedConsumer):
    """Notificaciones personales: asignaciones, resultados de exámenes, avisos."""

    async def post_authenticate(self) -> None:
        self.group_name = f"user.{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code) -> None:
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def notification_message(self, event: dict[str, Any]) -> None:
        await self.send_json({**event, "type": "notification"})

    async def domain_event(self, event: dict[str, Any]) -> None:
        await self.send_json({**event, "type": "notification"})


def encode(payload: dict[str, Any]) -> str:  # pragma: no cover - utilidad de depuración
    return json.dumps(payload, ensure_ascii=False, default=str)
