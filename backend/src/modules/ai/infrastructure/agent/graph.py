"""
Agente tutor · grafo Guard → Planner → ToolRouter → Reflect → Compose → Verify.

Se implementa con LangGraph cuando está disponible y, si no lo está, con un
ejecutor secuencial equivalente. La lógica de los nodos es la misma en ambos
casos: LangGraph aporta la orquestación, no las reglas.

Restricción de seguridad: el alcance (`training_id`, `user_id`) viaja en el
estado y jamás lo decide el modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ...domain.rag_policies import (
    NO_CONTEXT_ANSWER,
    AnswerGroundingVerifier,
    Citation,
    CitationPolicy,
    GroundingPolicy,
    RetrievedChunk,
)
from ...application.ports.llm import ChatMessage, LLMPort
from ..rag import prompts
from .intent import Intent, detect_intent
from .tools import TOOL_REGISTRY, ToolContext, ToolResult

logger = get_logger("ai.agent")

MAX_ITERATIONS = 3
MAX_TOOL_CALLS = 8


@dataclass
class AgentState:
    training_id: UUID
    project_id: UUID
    user_id: UUID
    question: str
    level: str = "intermediate"
    history: list[tuple[str, str]] = field(default_factory=list)
    training_title: str = ""
    project_name: str = ""

    intent: Intent = Intent.FACTUAL
    plan: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0

    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    usage: TokenUsage = field(default_factory=TokenUsage)
    refused: bool = False


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation]
    grounded: bool
    usage: TokenUsage
    tool_calls: list[dict[str, Any]]
    intent: str


class TutorAgent:
    def __init__(self, *, llm: LLMPort, retriever, grounding: GroundingPolicy | None = None) -> None:
        self._llm = llm
        self._retriever = retriever
        self._grounding = grounding or GroundingPolicy()

    # ═════════════════════════════════════════════════════════
    def run(self, state: AgentState) -> AgentResult:
        graph = _build_langgraph(self)
        if graph is not None:
            final = graph.invoke(state)
            state = final if isinstance(final, AgentState) else state
        else:
            state = self._run_sequential(state)

        return AgentResult(
            answer=state.answer,
            citations=state.citations,
            grounded=state.grounded,
            usage=state.usage,
            tool_calls=state.tool_calls,
            intent=state.intent.value,
        )

    def _run_sequential(self, state: AgentState) -> AgentState:
        """Ejecutor equivalente al grafo, usado si LangGraph no está instalado."""
        state = self.guard(state)
        if state.refused:
            return state

        state = self.planner(state)

        while state.iterations < MAX_ITERATIONS:
            state = self.tool_router(state)
            if self.reflect(state):
                break
            state.iterations += 1

        state = self.compose(state)
        return self.verify(state)

    # ═════════════════════════════════════════════════════════
    #  Nodos
    # ═════════════════════════════════════════════════════════
    def guard(self, state: AgentState) -> AgentState:
        """Valida que haya material consultable. El permiso ya se verificó en la vista."""
        from src.modules.trainings.infrastructure.models import Material

        has_material = Material.objects.filter(
            lesson__module__training_id=state.training_id, status=Material.Status.AVAILABLE
        ).exists()

        if not has_material:
            state.refused = True
            state.answer = (
                "Esta capacitación todavía no tiene material procesado, así que no puedo "
                "responder preguntas sobre su contenido."
            )
        return state

    def planner(self, state: AgentState) -> AgentState:
        """
        Detecta la intención y arma el plan.

        Para las intenciones frecuentes se usa un plan de plantilla: evita una
        llamada extra al LLM y reduce la latencia percibida (docs §12.5).
        """
        state.intent = detect_intent(state.question)
        state.plan = PLAN_BY_INTENT.get(state.intent, ["search_knowledge"])
        return state

    def tool_router(self, state: AgentState) -> AgentState:
        for tool_name in state.plan:
            if len(state.tool_calls) >= MAX_TOOL_CALLS:
                break
            result = self._invoke(tool_name, state)
            if result is None:
                continue
            state.tool_calls.append({"tool": tool_name, "summary": result.summary})
            state.tool_payloads.append({"tool": tool_name, "payload": result.payload})
            state.retrieved.extend(result.chunks)
        return state

    def reflect(self, state: AgentState) -> bool:
        """True cuando ya hay material suficiente para componer la respuesta."""
        if state.retrieved or state.tool_payloads:
            return True
        # Segundo intento: búsqueda genérica con la pregunta tal cual.
        if state.plan != ["search_knowledge"]:
            state.plan = ["search_knowledge"]
            return False
        return True

    def compose(self, state: AgentState) -> AgentState:
        decision = self._grounding.evaluate(_dedupe(state.retrieved))

        if not decision.is_grounded and not state.tool_payloads:
            state.answer = NO_CONTEXT_ANSWER
            state.grounded = False
            return state

        context_chunks = decision.chunks
        extra = _render_tool_payloads(state.tool_payloads)

        messages = [
            ChatMessage(
                role="system",
                content=prompts.build_chat_system(
                    training_title=state.training_title,
                    project_name=state.project_name,
                    level=state.level,
                )
                + INTENT_INSTRUCTIONS.get(state.intent, ""),
            ),
            ChatMessage(
                role="user",
                content=prompts.build_chat_user(
                    context=prompts.build_context(context_chunks) + extra,
                    history_block=prompts.build_history_block(state.history),
                    question=state.question,
                ),
            ),
        ]

        response = self._llm.generate(messages)
        state.answer = response.content
        state.usage = state.usage + response.usage
        state.grounded = decision.is_grounded
        state.retrieved = context_chunks
        return state

    def verify(self, state: AgentState) -> AgentState:
        """
        Nodo Verify (RN-04): comprueba que la respuesta se apoye en el material
        y elimina cualquier cita inventada.
        """
        if not state.grounded:
            return state

        # Las herramientas pueden aportar datos que no son chunks citables;
        # en ese caso la verificación léxica no aplica.
        only_retrieval = all(
            entry["tool"] in {"search_knowledge", "find_timestamp"}
            for entry in state.tool_payloads
        )
        if only_retrieval and not AnswerGroundingVerifier().is_supported(
            state.answer, state.retrieved
        ):
            logger.info(
                "Respuesta del agente descartada por no apoyarse en el material",
                extra={"training_id": str(state.training_id)},
            )
            state.answer = NO_CONTEXT_ANSWER
            state.grounded = False
            state.citations = []
            return state

        if NO_CONTEXT_ANSWER[:40] in state.answer:
            state.grounded = False
            state.citations = []
            return state

        state.answer = CitationPolicy.sanitize(state.answer, len(state.retrieved))
        state.citations = CitationPolicy.extract(state.answer, state.retrieved)
        if not state.citations:
            state.citations = CitationPolicy.infer_from_overlap(state.answer, state.retrieved)
        return state

    # ── Interno ──────────────────────────────────────────────
    def _invoke(self, tool_name: str, state: AgentState) -> ToolResult | None:
        tool: Callable[..., ToolResult] | None = TOOL_REGISTRY.get(tool_name)
        if tool is None:
            return None

        ctx = ToolContext(
            training_id=state.training_id,
            project_id=state.project_id,
            user_id=state.user_id,
            retriever=self._retriever,
        )
        try:
            if tool_name in {"search_knowledge", "find_timestamp"}:
                key = "query" if tool_name == "search_knowledge" else "topic"
                return tool(ctx, **{key: state.question})
            if tool_name == "get_concepts":
                return tool(ctx)
            if tool_name == "list_materials":
                return tool(ctx)
            return tool(ctx)  # herramientas sin argumentos obligatorios
        except TypeError:
            # La herramienta requiere argumentos que esta intención no aporta.
            return None
        except Exception:
            logger.warning("Fallo al ejecutar herramienta", extra={"tool": tool_name})
            return None


PLAN_BY_INTENT: dict[Intent, list[str]] = {
    Intent.FACTUAL: ["search_knowledge"],
    Intent.TIMESTAMP: ["find_timestamp", "search_knowledge"],
    Intent.SUMMARY: ["search_knowledge", "get_concepts"],
    Intent.SIMPLIFY: ["search_knowledge"],
    Intent.EXAMPLE: ["search_knowledge"],
    Intent.COMPARE: ["list_materials", "search_knowledge"],
    Intent.EXERCISE: ["search_knowledge", "get_concepts"],
    Intent.STEP_BY_STEP: ["search_knowledge"],
    Intent.ASSESSMENT: ["get_concepts", "search_knowledge"],
}

INTENT_INSTRUCTIONS: dict[Intent, str] = {
    Intent.SIMPLIFY: "\nExplica como si el usuario fuera principiante absoluto, con analogías simples.",
    Intent.EXAMPLE: "\nIncluye al menos un ejemplo concreto tomado del material.",
    Intent.STEP_BY_STEP: "\nEstructura la respuesta como una lista numerada de pasos accionables.",
    Intent.COMPARE: "\nPresenta la comparación en una tabla markdown con una fila por diferencia.",
    Intent.EXERCISE: "\nPropón 3 ejercicios prácticos con su solución al final, basados en el material.",
    Intent.SUMMARY: "\nEntrega un resumen estructurado con viñetas por tema.",
}


def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        key = str(chunk.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def _render_tool_payloads(payloads: list[dict[str, Any]]) -> str:
    """Añade al contexto los datos estructurados que produjeron las herramientas."""
    lines: list[str] = []
    for entry in payloads:
        if entry["tool"] in {"search_knowledge", "find_timestamp"}:
            continue  # ya están representados como chunks citables
        lines.append(f"\n\n[DATOS · {entry['tool']}]\n{entry['payload']}")
    return "".join(lines)[:3000]


def _build_langgraph(agent: TutorAgent):
    """Construye el grafo con LangGraph si la dependencia está disponible."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:  # pragma: no cover - se usa el ejecutor secuencial
        return None

    try:
        graph = StateGraph(AgentState)
        graph.add_node("guard", agent.guard)
        graph.add_node("planner", agent.planner)
        graph.add_node("tools", agent.tool_router)
        graph.add_node("compose", agent.compose)
        graph.add_node("verify", agent.verify)

        graph.set_entry_point("guard")
        graph.add_conditional_edges(
            "guard", lambda s: END if s.refused else "planner", {END: END, "planner": "planner"}
        )
        graph.add_edge("planner", "tools")
        graph.add_conditional_edges(
            "tools",
            lambda s: "compose" if agent.reflect(s) or s.iterations >= MAX_ITERATIONS else "tools",
            {"compose": "compose", "tools": "tools"},
        )
        graph.add_edge("compose", "verify")
        graph.add_edge("verify", END)
        return graph.compile()
    except Exception:  # pragma: no cover - versión incompatible
        logger.warning("No se pudo compilar el grafo LangGraph; se usa el ejecutor secuencial")
        return None
