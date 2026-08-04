"""Pruebas del dominio puro: sin base de datos, sin Django, sin IA."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.ai.domain.chunking import ChunkingPolicy, SourceBlock
from src.modules.ai.domain.rag_policies import (
    NO_CONTEXT_ANSWER,
    AnswerGroundingVerifier as AnswerGrounding,
    CitationPolicy,
    GroundingPolicy,
    RetrievedChunk,
)
from src.modules.assessments.domain.grading import AnswerMatcher, normalize
from src.modules.trainings.domain.material_state import MaterialStateMachine
from src.modules.trainings.domain.progress import (
    LessonProgressSnapshot,
    ProgressCalculator,
)
from src.shared.domain.exceptions import InvalidStateTransition
from src.shared.domain.value_object import Email, Slug, TimeRange

pytestmark = pytest.mark.unit


# ── Value objects ────────────────────────────────────────────
def test_email_se_normaliza_a_minusculas():
    assert Email("  Ana.Reyes@Empresa.CL ").value == "ana.reyes@empresa.cl"


@pytest.mark.parametrize("invalid", ["sin-arroba", "a@b", "@dominio.cl", ""])
def test_email_invalido_es_rechazado(invalid):
    from src.shared.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        Email(invalid)


def test_slug_rechaza_mayusculas_y_espacios():
    from src.shared.domain.exceptions import ValidationError

    assert Slug("erp-inventario").value == "erp-inventario"
    with pytest.raises(ValidationError):
        Slug("ERP Inventario")


def test_time_range_calcula_duracion_y_contiene():
    rango = TimeRange(start=60.0, end=180.0)
    assert rango.duration == 120.0
    assert rango.contains(120.0)
    assert not rango.contains(200.0)


# ── Máquina de estados del material ──────────────────────────
def test_transiciones_validas_del_material():
    assert MaterialStateMachine.can_transition("PENDING", "PROCESSING")
    assert MaterialStateMachine.can_transition("ANALYZING", "AVAILABLE")
    assert MaterialStateMachine.can_transition("ERROR", "PROCESSING")


def test_transicion_invalida_lanza_excepcion():
    with pytest.raises(InvalidStateTransition):
        MaterialStateMachine.assert_transition("PENDING", "AVAILABLE")


def test_solo_available_es_consultable():
    assert MaterialStateMachine.is_queryable("AVAILABLE")
    for status in ("PENDING", "PROCESSING", "ANALYZING", "ERROR"):
        assert not MaterialStateMachine.is_queryable(status)


# ── Progreso ─────────────────────────────────────────────────
def test_progreso_solo_cuenta_lecciones_obligatorias():
    snapshots = [
        LessonProgressSnapshot("1", True, True, 900, 900),
        LessonProgressSnapshot("2", True, False, 100, 900),
        LessonProgressSnapshot("3", False, False, 0, 900),  # opcional: no cuenta
    ]
    assert ProgressCalculator.compute(snapshots) == 50.0


def test_leccion_se_completa_al_90_por_ciento():
    assert ProgressCalculator.should_complete_lesson(900, 1000)
    assert not ProgressCalculator.should_complete_lesson(800, 1000)


def test_examen_requiere_avance_minimo():
    assert ProgressCalculator.can_take_exam(85.0, 80)
    assert not ProgressCalculator.can_take_exam(75.0, 80)


# ── RAG · grounding ──────────────────────────────────────────
def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        material_id=uuid4(),
        content="contenido",
        score=score,
        material_title="Sesión Inventario",
        material_type="VIDEO",
        start_time=872.4,
    )


def test_sin_resultados_no_hay_contexto():
    decision = GroundingPolicy().evaluate([])
    assert decision.is_grounded is False


def test_scores_bajos_no_sostienen_una_respuesta():
    decision = GroundingPolicy(min_score=0.35, min_top_score=0.45).evaluate(
        [_chunk(0.20), _chunk(0.18)]
    )
    assert decision.is_grounded is False


def test_buen_score_habilita_la_respuesta():
    decision = GroundingPolicy(min_score=0.35, min_top_score=0.45).evaluate(
        [_chunk(0.81), _chunk(0.52), _chunk(0.10)]
    )
    assert decision.is_grounded is True
    assert len(decision.chunks) == 2  # el de 0.10 se descarta


def test_la_respuesta_honesta_es_estable():
    assert "No encuentro esa información" in NO_CONTEXT_ANSWER


# ── RAG · citas ──────────────────────────────────────────────
def test_solo_se_aceptan_citas_existentes():
    chunks = [_chunk(0.9), _chunk(0.8)]
    citations = CitationPolicy.extract("Según [1] y [2], el proceso...", chunks)
    assert len(citations) == 2


def test_cita_inventada_se_descarta():
    chunks = [_chunk(0.9)]
    citations = CitationPolicy.extract("Como indica [7], el proceso...", chunks)
    assert citations == []


def test_sanitize_elimina_referencias_fuera_de_rango():
    limpio = CitationPolicy.sanitize("Ver [1] y también [9].", context_size=1)
    assert "[1]" in limpio
    assert "[9]" not in limpio


def test_cita_repetida_no_se_duplica():
    chunks = [_chunk(0.9)]
    citations = CitationPolicy.extract("[1] dice esto y [1] también aquello.", chunks)
    assert len(citations) == 1


# ── RAG · verificación posterior (RN-04) ─────────────────────
def _material_chunk(content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        material_id=uuid4(),
        content=content,
        score=0.8,
        material_title="Manual de Inventario",
        material_type="MD",
        page=3,
    )


INVENTARIO = _material_chunk(
    "El inventario cíclico consiste en contar una porción del inventario todos los días. "
    "La clasificación ABC define la frecuencia: clase A mensual, clase B trimestral y "
    "clase C semestral. Durante el conteo las ubicaciones quedan bloqueadas."
)


def test_respuesta_apoyada_en_el_material_se_acepta():
    verifier = AnswerGrounding()
    answer = (
        "El inventario cíclico consiste en contar una porción del inventario cada día. "
        "La clasificación ABC define la frecuencia del conteo: clase A mensual."
    )
    assert verifier.is_supported(answer, [INVENTARIO]) is True


def test_respuesta_de_conocimiento_propio_se_rechaza():
    """El caso real que motivó esta política: el modelo respondió de memoria."""
    verifier = AnswerGrounding()
    answer = (
        "La capital de Mongolia es Ulaanbaatar. Según los últimos datos disponibles, "
        "la población de Ulaanbaatar se sitúa en torno a 800.000 habitantes."
    )
    assert verifier.is_supported(answer, [INVENTARIO]) is False


def test_la_respuesta_honesta_siempre_se_considera_valida():
    verifier = AnswerGrounding()
    assert verifier.is_supported(NO_CONTEXT_ANSWER, [INVENTARIO]) is True


def test_sin_contexto_ninguna_respuesta_se_apoya():
    verifier = AnswerGrounding()
    assert verifier.is_supported("Cualquier afirmación extensa sobre bodegas.", []) is False


def test_respuestas_muy_cortas_no_se_penalizan():
    """'Sí' o 'No aplica' no tienen vocabulario suficiente para medir."""
    verifier = AnswerGrounding()
    assert verifier.is_supported("Sí, correcto.", [INVENTARIO]) is True


def test_se_deducen_las_fuentes_cuando_el_modelo_no_cita():
    """Los modelos pequeños ignoran los marcadores [n]; igual debe haber enlaces."""
    answer = (
        "La clasificación ABC define la frecuencia del conteo cíclico: "
        "clase A mensual, clase B trimestral, clase C semestral."
    )
    citations = CitationPolicy.infer_from_overlap(answer, [INVENTARIO])

    assert len(citations) == 1
    assert citations[0].chunk_id == INVENTARIO.chunk_id
    assert citations[0].page == 3


def test_no_se_deducen_fuentes_para_una_respuesta_ajena():
    answer = "La capital de Mongolia es Ulaanbaatar, con unos 800.000 habitantes."
    assert CitationPolicy.infer_from_overlap(answer, [INVENTARIO]) == []


def test_la_etiqueta_de_la_cita_indica_la_ubicacion():
    video = RetrievedChunk(
        chunk_id=uuid4(),
        material_id=uuid4(),
        content="contenido",
        score=0.8,
        material_title="Sesión Inventario",
        material_type="VIDEO",
        start_time=872.4,
    )
    assert video.label() == "Sesión Inventario · 14:32"
    assert INVENTARIO.label() == "Manual de Inventario · pág. 3"


# ── Chunking ─────────────────────────────────────────────────
def test_chunking_conserva_los_timestamps():
    blocks = [
        SourceBlock(text="palabra " * 300, order=i, start_time=i * 10.0, end_time=i * 10.0 + 10)
        for i in range(6)
    ]
    chunks = ChunkingPolicy(chunk_size_tokens=400, overlap_tokens=50).split(blocks)

    assert len(chunks) > 1
    assert all(chunk.start_time is not None for chunk in chunks)
    assert chunks[0].start_time == 0.0


def test_chunking_conserva_la_pagina():
    blocks = [SourceBlock(text="texto del documento", order=i, page=i + 1) for i in range(4)]
    chunks = ChunkingPolicy().split(blocks)
    assert chunks[0].page == 1


def test_solapamiento_debe_ser_menor_que_el_tamano():
    with pytest.raises(ValueError):
        ChunkingPolicy(chunk_size_tokens=100, overlap_tokens=100)


# ── Corrección ───────────────────────────────────────────────
def test_normalizacion_ignora_acentos_y_puntuacion():
    assert normalize("Inventario Cíclico.") == "inventario ciclico"


def test_seleccion_unica_correcta_da_todos_los_puntos():
    result = AnswerMatcher.grade_single_choice(["a"], ["a"], Decimal("2"))
    assert result.is_correct and result.points == Decimal("2")


def test_seleccion_multiple_penaliza_los_falsos_positivos():
    """Marcar todo no puede valer lo mismo que responder bien."""
    todos = AnswerMatcher.grade_multiple_choice(["a", "b", "c", "d"], ["a", "b"], Decimal("4"))
    exacto = AnswerMatcher.grade_multiple_choice(["a", "b"], ["a", "b"], Decimal("4"))

    assert exacto.points == Decimal("4")
    assert todos.points < exacto.points


def test_respuesta_corta_acepta_equivalencias():
    result = AnswerMatcher.grade_short_answer(
        "el inventario cíclico", "Inventario cíclico", Decimal("1")
    )
    assert result.is_correct


def test_respuesta_corta_ambigua_queda_marcada_como_parcial():
    result = AnswerMatcher.grade_short_answer(
        "es un conteo de inventario", "conteo periódico de inventario por zonas", Decimal("1")
    )
    assert result.partial or result.is_correct
