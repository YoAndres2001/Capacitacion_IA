"""
Validación de las preguntas que produce la IA (CU-13, RF-062).

Un modelo puede devolver JSON sintácticamente válido pero pedagógicamente
inservible: dos opciones correctas en una pregunta de selección única, un
verdadero/falso con cuatro alternativas, o la misma pregunta parafraseada. Estas
pruebas cubren ese filtro, que es lo que separa "generó JSON" de "generó un
examen usable".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.ai.domain.rag_policies import AnswerGroundingVerifier
from src.modules.assessments.domain.grading import tokens
from src.modules.assessments.infrastructure.exam_generator import (
    ExamGenerator,
    GenerationRequest,
    OptionOut,
    QuestionOut,
    _is_about_material,
)

pytestmark = pytest.mark.unit


def _options(*specs: tuple[str, bool]) -> list[OptionOut]:
    return [OptionOut(text=text, is_correct=correct) for text, correct in specs]


def _material_words(text: str) -> set[str]:
    return AnswerGroundingVerifier._content_words(text)


# ── Selección única ──────────────────────────────────────────
def test_seleccion_unica_valida_se_acepta():
    options = _options(("A", True), ("B", False), ("C", False), ("D", False))
    assert ExamGenerator._normalize_options("SINGLE_CHOICE", options) == options


def test_seleccion_unica_con_dos_correctas_se_descarta():
    """El error más común del modelo: marca dos alternativas como correctas."""
    options = _options(("A", True), ("B", True), ("C", False))
    assert ExamGenerator._normalize_options("SINGLE_CHOICE", options) == []


def test_seleccion_unica_sin_correcta_se_descarta():
    options = _options(("A", False), ("B", False), ("C", False))
    assert ExamGenerator._normalize_options("SINGLE_CHOICE", options) == []


def test_seleccion_unica_con_pocas_alternativas_se_descarta():
    options = _options(("A", True), ("B", False))
    assert ExamGenerator._normalize_options("SINGLE_CHOICE", options) == []


# ── Verdadero / Falso ────────────────────────────────────────
def test_verdadero_falso_valido_se_acepta():
    options = _options(("Verdadero", True), ("Falso", False))
    assert len(ExamGenerator._normalize_options("TRUE_FALSE", options)) == 2


def test_verdadero_falso_con_tres_alternativas_se_descarta():
    options = _options(("Verdadero", True), ("Falso", False), ("Depende", False))
    assert ExamGenerator._normalize_options("TRUE_FALSE", options) == []


# ── Selección múltiple ───────────────────────────────────────
def test_seleccion_multiple_valida_se_acepta():
    options = _options(("A", True), ("B", True), ("C", False), ("D", False), ("E", False))
    assert len(ExamGenerator._normalize_options("MULTIPLE_CHOICE", options)) == 5


def test_seleccion_multiple_con_todas_correctas_se_descarta():
    """Si todas son correctas la pregunta no discrimina nada."""
    options = _options(("A", True), ("B", True), ("C", True), ("D", True))
    assert ExamGenerator._normalize_options("MULTIPLE_CHOICE", options) == []


def test_seleccion_multiple_con_una_sola_correcta_se_descarta():
    options = _options(("A", True), ("B", False), ("C", False), ("D", False))
    assert ExamGenerator._normalize_options("MULTIPLE_CHOICE", options) == []


def test_las_alternativas_vacias_se_ignoran():
    options = _options(("A", True), ("  ", False), ("B", False), ("C", False))
    # Quedan 3 alternativas válidas: sigue siendo una selección única correcta.
    assert len(ExamGenerator._normalize_options("SINGLE_CHOICE", options)) == 3


# ── Duplicados semánticos ────────────────────────────────────
def test_pregunta_parafraseada_se_detecta_como_duplicada():
    previa = [tokens("¿Cuál es la frecuencia de conteo de la clase A?")]
    assert ExamGenerator._is_duplicate("¿Cuál es la frecuencia del conteo clase A?", previa)


def test_pregunta_distinta_no_es_duplicada():
    previa = [tokens("¿Cuál es la frecuencia de conteo de la clase A?")]
    assert not ExamGenerator._is_duplicate(
        "¿Qué motivos admite un ajuste de inventario?", previa
    )


def test_enunciado_vacio_se_trata_como_duplicado():
    assert ExamGenerator._is_duplicate("   ", [])


# ── Distribución por defecto ─────────────────────────────────
@pytest.mark.parametrize("total", [5, 10, 20, 40])
def test_la_distribucion_por_defecto_suma_el_total(total):
    distribution = ExamGenerator._default_distribution(total)
    assert sum(distribution.values()) == total


def test_la_distribucion_privilegia_la_seleccion_unica():
    distribution = ExamGenerator._default_distribution(10)
    assert distribution["SINGLE_CHOICE"] >= max(
        distribution["TRUE_FALSE"], distribution["SHORT_ANSWER"]
    )


# ── Lotes de generación ──────────────────────────────────────
def test_los_lotes_respetan_el_total_solicitado():
    distribution = {"SINGLE_CHOICE": 5, "TRUE_FALSE": 2, "SHORT_ANSWER": 1}
    batches = ExamGenerator._batches(distribution)

    total = sum(sum(batch.values()) for batch in batches)
    assert total == 8


def test_cada_lote_pide_un_solo_tipo_de_pregunta():
    """Un modelo pequeño resuelve mejor un tipo por llamada."""
    batches = ExamGenerator._batches({"SINGLE_CHOICE": 5, "OPEN_ENDED": 3})
    assert all(len(batch) == 1 for batch in batches)


def test_el_tope_corta_antes_de_persistir_el_excedente():
    """
    Un modelo pequeño ignora la cantidad solicitada y sigue redactando hasta
    agotar sus tokens: se observó devolver 7 preguntas en un lote de 2. Sin el
    tope, un examen de 10 preguntas acababa con 30.

    Con `limit=0` no debe tocar la base de datos: si intentara persistir alguna,
    la llamada fallaría por el examen nulo.
    """
    exceso = [
        QuestionOut(type="TRUE_FALSE", statement=f"Enunciado numero {n}.") for n in range(7)
    ]
    assert ExamGenerator(llm=None)._persist(None, exceso, [], [], 0, limit=0) == 0


def test_ningun_lote_excede_el_tamano_configurado():
    from django.conf import settings

    size = int(settings.AI_SETTINGS.get("EXAM_BATCH_SIZE", 2))
    batches = ExamGenerator._batches({"SINGLE_CHOICE": 7})
    assert all(sum(batch.values()) <= size for batch in batches)


def test_la_rotacion_reparte_el_material_entre_lotes():
    """Cada lote debe partir por una zona distinta del curso."""
    chunks = ["a", "b", "c", "d"]
    assert ExamGenerator._rotate(chunks, 0) == ["a", "b", "c", "d"]
    assert ExamGenerator._rotate(chunks, 1) == ["b", "c", "d", "a"]
    assert ExamGenerator._rotate(chunks, 6) == ["c", "d", "a", "b"]
    assert ExamGenerator._rotate([], 3) == []


# ── Aviso de avance ──────────────────────────────────────────
class _FakeExam:
    id = "9e2eb00b-6b99-464d-8291-2196a8f0a972"


def test_el_avance_informa_el_lote_y_el_total():
    recibidos = []
    request = GenerationRequest(
        training=None, title="t", num_questions=10, on_progress=recibidos.append
    )

    ExamGenerator._report(request, _FakeExam(), step="questions", progress=40, questions=3)

    assert recibidos == [
        {
            "exam_id": _FakeExam.id,
            "step": "questions",
            "progress": 40,
            "questions": 3,
            "total": 10,
        }
    ]


def test_un_fallo_al_publicar_el_avance_no_aborta_la_generacion():
    """Perder la barra de progreso es molesto; perder 40 minutos de trabajo, no."""

    def explota(_payload):
        raise RuntimeError("canal caído")

    request = GenerationRequest(training=None, title="t", on_progress=explota)

    ExamGenerator._report(request, _FakeExam(), step="done", progress=100, questions=5)


def test_sin_destinatario_no_se_publica_avance():
    request = GenerationRequest(training=None, title="t", on_progress=None)

    ExamGenerator._report(request, _FakeExam(), step="done", progress=100, questions=5)


# ── Anclaje al material ──────────────────────────────────────
MATERIAL = _material_words(
    "El inventario ciclico cuenta una porcion del inventario cada dia. La clasificacion "
    "ABC determina la frecuencia de conteo: clase A mensual, clase B trimestral, clase C "
    "semestral. Durante el conteo las ubicaciones quedan bloqueadas para movimientos."
)


def test_pregunta_sobre_el_material_se_acepta():
    candidate = QuestionOut(
        type="SINGLE_CHOICE",
        statement="¿Con qué frecuencia se cuenta la clase A en el inventario cíclico?",
        options=_options(("Mensual", True), ("Anual", False), ("Diaria", False)),
    )
    assert _is_about_material(candidate, MATERIAL) is True


def test_pregunta_inventada_por_el_modelo_se_descarta():
    """Caso real observado: el modelo generó preguntas de neurociencia."""
    candidate = QuestionOut(
        type="SINGLE_CHOICE",
        statement="¿Cuál afirmación es correcta sobre la estructura del cerebro humano?",
        options=_options(
            ("El cerebro tiene tres regiones principales", True),
            ("El cerebro tiene 100 billones de neuronas", False),
            ("La neuroplasticidad es irreversible", False),
        ),
    )
    assert _is_about_material(candidate, MATERIAL) is False


def test_los_distractores_no_condicionan_el_anclaje():
    """Las alternativas incorrectas pueden traer términos nuevos legítimamente."""
    candidate = QuestionOut(
        type="SINGLE_CHOICE",
        statement="¿Qué ocurre con las ubicaciones durante el conteo cíclico?",
        options=_options(
            ("Quedan bloqueadas para movimientos", True),
            ("Se transfieren a consignación externa", False),
            ("Se liquidan mediante subasta pública", False),
        ),
    )
    assert _is_about_material(candidate, MATERIAL) is True


def test_sin_material_ninguna_pregunta_se_acepta():
    candidate = QuestionOut(type="TRUE_FALSE", statement="Cualquier enunciado extenso aquí.")
    assert _is_about_material(candidate, set()) is False


# ── Trazabilidad al material ─────────────────────────────────
class _FakeChunk:
    def __init__(self, name: str) -> None:
        self.name = name


def test_source_index_apunta_al_fragmento_correcto():
    """El prompt numera desde 1; la lista de Python desde 0."""
    chunks = [_FakeChunk("a"), _FakeChunk("b"), _FakeChunk("c")]
    assert ExamGenerator._source_for(1, chunks) is chunks[0]
    assert ExamGenerator._source_for(3, chunks) is chunks[2]


def test_source_index_fuera_de_rango_no_rompe():
    chunks = [_FakeChunk("a")]
    assert ExamGenerator._source_for(9, chunks) is None
    assert ExamGenerator._source_for(0, chunks) is None
    assert ExamGenerator._source_for(None, chunks) is None


# ── Cuánto material hace falta ───────────────────────────────
def test_el_material_disponible_se_traduce_a_un_maximo_de_preguntas():
    """
    Antes se contaban FRAGMENTOS, y eso medía `CHUNK_SIZE_TOKENS`, no contenido.

    Caso real: un video de 90 s y un PDF corto entran en un fragmento cada uno,
    sumaban 2 de los 5 exigidos y la capacitación quedaba bloqueada con 3.423
    caracteres de material perfectamente utilizable.
    """
    from src.modules.assessments.infrastructure.exam_generator import max_questions_for

    assert max_questions_for(3423) == 11        # el caso que estaba bloqueado
    assert max_questions_for(11000) == 36       # la capacitación de demostración


def test_por_debajo_del_piso_no_hay_examen_posible():
    from src.modules.assessments.infrastructure.exam_generator import (
        MIN_CONTENT_CHARS,
        max_questions_for,
    )

    assert max_questions_for(MIN_CONTENT_CHARS - 1) == 0
    assert max_questions_for(0) == 0


def test_pedir_mas_preguntas_de_las_que_sostiene_el_material_falla_con_el_numero_util():
    """El error debe decir cuántas caben, no solo que no se puede."""
    from src.modules.assessments.infrastructure.exam_generator import assert_enough_content
    from src.shared.domain.exceptions import InsufficientContent

    chunks = [SimpleNamespace(content="x" * 3423)]

    with pytest.raises(InsufficientContent) as error:
        assert_enough_content(None, 30, chunks=chunks)

    assert error.value.details["max_questions"] == 11
    assert "11" in error.value.message


def test_con_material_suficiente_no_levanta_nada():
    from src.modules.assessments.infrastructure.exam_generator import assert_enough_content

    chunks = [SimpleNamespace(content="x" * 3423)]

    assert assert_enough_content(None, 10, chunks=chunks) is None
