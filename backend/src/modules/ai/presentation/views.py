"""Vistas del módulo IA: chat RAG, agente tutor y consumo."""

from __future__ import annotations

from django.db.models import Count, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.modules.trainings.infrastructure.models import Enrollment, Training
from src.shared.container import get_embeddings, get_llm, get_vector_store
from src.shared.domain.exceptions import NotEnrolled, NotFoundError
from src.shared.presentation.permissions import IsAdmin

from ..application.use_cases.answer_question import AnswerInput, AnswerQuestionUseCase
from ..infrastructure.agent.graph import AgentState, TutorAgent
from ..infrastructure.models import AIUsageLog, ChatMessage, ChatSession
from ..infrastructure.rag.retriever import HybridRetriever
from ..infrastructure.usage import record_usage
from .serializers import (
    AgentRunSerializer,
    AIUsageSerializer,
    AskSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
    FeedbackSerializer,
)


def build_retriever(project_id):
    """Fábrica del recuperador híbrido para un proyecto."""
    embeddings = get_embeddings()
    return HybridRetriever(vector_store=get_vector_store(project_id), embeddings=embeddings)


def assert_can_use_chat(user, training: Training) -> None:
    if user.can_manage_content:
        return
    if not Enrollment.objects.filter(user=user, training=training).exists():
        raise NotEnrolled


class TrainingChatSessionsView(APIView):
    """Conversaciones del usuario dentro de una capacitación."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["IA"], responses=ChatSessionSerializer(many=True), summary="Mis conversaciones")
    def get(self, request, training_id):
        training = _training_or_404(request, training_id)
        assert_can_use_chat(request.user, training)
        sessions = ChatSession.objects.filter(training=training, user=request.user)
        return Response(ChatSessionSerializer(sessions, many=True).data)

    @extend_schema(tags=["IA"], request=None, responses=ChatSessionSerializer, summary="Nueva conversación")
    def post(self, request, training_id):
        training = _training_or_404(request, training_id)
        assert_can_use_chat(request.user, training)

        if not training.chat_enabled:
            return Response(
                {"error": {"code": "CHAT_DISABLED", "message": "El chat está deshabilitado en esta capacitación."}},
                status=status.HTTP_409_CONFLICT,
            )

        session = ChatSession.objects.create(
            training=training, user=request.user, title=request.data.get("title", "")
        )
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class ChatSessionViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Las conversaciones se crean desde su capacitación
    (`POST /trainings/{id}/chat-sessions`), que valida la inscripción y que el
    chat esté habilitado. La ruta de lista no expone `create`.
    """

    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]
    throttle_scope: str | None = None

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).select_related(
            "training__project"
        )

    @extend_schema(tags=["IA"], responses=ChatMessageSerializer(many=True), summary="Historial")
    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        session = self.get_object()
        history = (
            ChatMessage.objects.filter(session=session)
            .exclude(role=ChatMessage.Role.SYSTEM)
            .prefetch_related("citations")
        )
        return Response(ChatMessageSerializer(history, many=True).data)

    @extend_schema(
        tags=["IA"],
        request=AskSerializer,
        responses=ChatMessageSerializer,
        summary="Preguntar (CU-12) · el streaming va por WebSocket",
    )
    @action(detail=True, methods=["post"], url_path="ask", throttle_scope="ai_chat")
    def ask(self, request, pk=None):
        session = self.get_object()
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AnswerQuestionUseCase(
            llm=get_llm(), retriever_factory=build_retriever
        ).execute(
            AnswerInput(
                session_id=session.id,
                question=serializer.validated_data["content"],
                user_id=request.user.id,
                level=serializer.validated_data.get("level", "intermediate"),
            )
        )

        message = ChatMessage.objects.prefetch_related("citations").get(id=result.message_id)
        return Response(ChatMessageSerializer(message).data)

    @extend_schema(tags=["IA"], request=FeedbackSerializer, summary="Calificar una respuesta")
    @action(detail=True, methods=["post"], url_path=r"messages/(?P<message_id>[^/.]+)/feedback")
    def message_feedback(self, request, pk=None, message_id=None):
        session = self.get_object()
        serializer = FeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = ChatMessage.objects.filter(id=message_id, session=session).update(
            feedback=serializer.validated_data["feedback"]
        )
        if not updated:
            raise NotFoundError("Mensaje no encontrado.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentRunView(APIView):
    """RF-050 · Ejecuta el agente tutor con herramientas."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "ai_chat"

    @extend_schema(tags=["IA"], request=AgentRunSerializer, summary="Ejecutar el agente tutor")
    def post(self, request, training_id):
        training = _training_or_404(request, training_id)
        assert_can_use_chat(request.user, training)

        serializer = AgentRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = None
        history: list[tuple[str, str]] = []
        session_id = serializer.validated_data.get("session_id")
        if session_id:
            session = ChatSession.objects.filter(
                id=session_id, user=request.user, training=training
            ).first()
            if session:
                history = [
                    (message.role, message.content)
                    for message in ChatMessage.objects.filter(session=session).order_by(
                        "-created_at"
                    )[:6]
                ][::-1]

        agent = TutorAgent(llm=get_llm(), retriever=build_retriever(training.project_id))
        result = agent.run(
            AgentState(
                training_id=training.id,
                project_id=training.project_id,
                user_id=request.user.id,
                question=serializer.validated_data["instruction"],
                level=serializer.validated_data.get("level", "intermediate"),
                history=history,
                training_title=training.title,
                project_name=training.project.name,
            )
        )

        record_usage(
            usage=result.usage,
            purpose="AGENT",
            company_id=request.user.company_id,
            project_id=training.project_id,
            user_id=request.user.id,
        )

        if session is not None:
            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.USER,
                content=serializer.validated_data["instruction"],
            )
            message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content=result.answer,
                grounded=result.grounded,
                model=get_llm().model_name,
            )
            session.last_message_at = timezone.now()
            session.save(update_fields=["last_message_at", "updated_at"])
            message_id = str(message.id)
        else:
            message_id = None

        return Response(
            {
                "message_id": message_id,
                "intent": result.intent,
                "answer": result.answer,
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
                "tools_used": result.tool_calls,
            }
        )


class AIUsageView(APIView):
    """RF-073 · Panel de utilización de IA."""

    permission_classes = [IsAdmin]

    @extend_schema(
        tags=["IA"],
        parameters=[
            OpenApiParameter("project", str),
            OpenApiParameter("from", str),
            OpenApiParameter("to", str),
        ],
        summary="Consumo de IA",
    )
    def get(self, request):
        queryset = AIUsageLog.objects.filter(company_id=request.user.company_id)

        project_id = request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        if date_from := request.query_params.get("from"):
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to := request.query_params.get("to"):
            queryset = queryset.filter(created_at__lte=date_to)

        totals = queryset.aggregate(
            prompt_tokens=Sum("prompt_tokens"),
            completion_tokens=Sum("completion_tokens"),
            cost_usd=Sum("cost_usd"),
            calls=Count("id"),
        )
        by_purpose = list(
            queryset.values("purpose")
            .annotate(
                calls=Count("id"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                cost_usd=Sum("cost_usd"),
            )
            .order_by("-calls")
        )

        ungrounded = ChatMessage.objects.filter(
            session__training__project__company_id=request.user.company_id,
            role=ChatMessage.Role.ASSISTANT,
        )
        total_answers = ungrounded.count()
        without_context = ungrounded.filter(grounded=False).count()

        return Response(
            {
                "totals": {
                    "calls": totals["calls"] or 0,
                    "prompt_tokens": totals["prompt_tokens"] or 0,
                    "completion_tokens": totals["completion_tokens"] or 0,
                    "cost_usd": float(totals["cost_usd"] or 0),
                },
                "by_purpose": [
                    {**row, "cost_usd": float(row["cost_usd"] or 0)} for row in by_purpose
                ],
                "quality": {
                    "answers": total_answers,
                    "without_context": without_context,
                    "no_context_rate": round(
                        without_context / total_answers * 100, 2
                    ) if total_answers else 0.0,
                },
                "recent": AIUsageSerializer(queryset.order_by("-created_at")[:50], many=True).data,
            }
        )


class AIHealthView(APIView):
    """Estado del proveedor de IA configurado."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["IA"], summary="Salud del proveedor de IA")
    def get(self, request):
        llm = get_llm()
        embeddings = get_embeddings()
        available = llm.is_available()
        return Response(
            {
                "provider": llm.provider_name,
                "llm_model": llm.model_name,
                "embedding_model": embeddings.model_name,
                "available": available,
                "free": llm.provider_name == "ollama",
            },
            status=status.HTTP_200_OK if available else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _training_or_404(request, training_id) -> Training:
    training = (
        Training.objects.filter(
            id=training_id, project__company_id=request.user.company_id
        )
        .select_related("project")
        .first()
    )
    if training is None:
        raise NotFoundError("La capacitación no existe.")
    return training
