"""
Recuperación de la salida JSON que el modelo deja a medias.

En modo JSON el modelo emite JSON válido hasta que agota `max_tokens` y se corta
a mitad de una palabra. Medido en este proyecto: un lote de preguntas se cortaba
en el límite exacto de tokens y el examen entero se quedaba en cero preguntas.
Estas pruebas fijan el rescate de la parte que sí llegó completa.
"""

from __future__ import annotations

import json

import pytest

from src.modules.ai.infrastructure.providers.parsing import (
    parse_json_loosely,
    repair_truncated_json,
)

pytestmark = pytest.mark.unit


# ── Reparación ───────────────────────────────────────────────
def test_recupera_los_elementos_completos_de_una_lista_cortada():
    """Caso real: la segunda pregunta se corta dentro de una alternativa."""
    truncated = (
        '{"questions": [{"type": "TRUE_FALSE", "statement": "La bodega tiene cuatro niveles."}, '
        '{"type": "TRUE_FALSE", "statement": "El sistema impide exce'
    )
    parsed = json.loads(repair_truncated_json(truncated))
    assert len(parsed["questions"]) == 1
    assert parsed["questions"][0]["statement"] == "La bodega tiene cuatro niveles."


def test_descarta_la_coma_que_quedo_colgando():
    truncated = '{"questions": [{"a": 1}, '
    assert json.loads(repair_truncated_json(truncated)) == {"questions": [{"a": 1}]}


def test_cierra_varios_niveles_a_la_vez():
    truncated = '{"questions": [{"options": [{"text": "Verdadero"}, {"text": "Fal'
    parsed = json.loads(repair_truncated_json(truncated))
    assert parsed == {"questions": [{"options": [{"text": "Verdadero"}]}]}


def test_una_llave_de_cierre_dentro_de_una_cadena_no_confunde_al_reparador():
    truncated = '{"questions": [{"statement": "Usa }] al final"}, {"statement": "cor'
    parsed = json.loads(repair_truncated_json(truncated))
    assert parsed["questions"][0]["statement"] == "Usa }] al final"


def test_las_comillas_escapadas_no_cierran_la_cadena():
    truncated = '{"questions": [{"statement": "Dice \\"alto\\" aqui"}, {"statement": "cor'
    parsed = json.loads(repair_truncated_json(truncated))
    assert parsed["questions"][0]["statement"] == 'Dice "alto" aqui'


def test_sin_ningun_elemento_completo_no_hay_nada_que_rescatar():
    assert repair_truncated_json('{"questions": [{"type": "TRUE_F') is None


def test_un_json_mal_formado_no_se_intenta_reparar():
    """Cerrar de más es corrupción, no truncamiento: mejor fallar."""
    assert repair_truncated_json('{"questions": [}]}') is None


# ── Integración con el parser ────────────────────────────────
def test_el_parser_rescata_la_salida_cortada():
    truncated = (
        '{"questions": [{"type": "TRUE_FALSE", "statement": "Enunciado completo."}, '
        '{"type": "TRUE_FALSE", "statement": "Enunciado a med'
    )
    assert parse_json_loosely(truncated) == {
        "questions": [{"type": "TRUE_FALSE", "statement": "Enunciado completo."}]
    }


def test_el_json_completo_sigue_parseando_sin_tocarse():
    assert parse_json_loosely('{"questions": [{"a": 1}]}') == {"questions": [{"a": 1}]}


def test_el_json_entre_vallas_de_codigo_sigue_parseando():
    assert parse_json_loosely('```json\n{"questions": []}\n```') == {"questions": []}


def test_una_salida_sin_json_alguno_sigue_fallando():
    with pytest.raises(ValueError):
        parse_json_loosely("Claro, aquí tienes las preguntas que me pediste.")


# ── Esquema estricto para Structured Outputs ─────────────────
def test_el_esquema_estricto_exige_todos_los_campos_y_cierra_el_objeto():
    """
    Structured Outputs rechaza el esquema de Pydantic tal cual.

    Exige `additionalProperties: false` y **todos** los campos en `required`,
    incluidos los que tienen valor por defecto. Sin esta traducción la API
    responde 400 y cada generación de examen degradaría a modo JSON.
    """
    from pydantic import BaseModel, Field

    from src.modules.ai.infrastructure.providers.parsing import strict_schema

    class Opcion(BaseModel):
        texto: str = Field(max_length=200)
        correcta: bool = False

    class Pregunta(BaseModel):
        enunciado: str
        opciones: list[Opcion] = Field(default_factory=list)

    schema = strict_schema(Pregunta)

    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == ["enunciado", "opciones"]

    # La referencia a `Opcion` queda embebida, no como `$ref`.
    assert "$defs" not in schema
    opcion = schema["properties"]["opciones"]["items"]
    assert sorted(opcion["required"]) == ["correcta", "texto"]
    assert opcion["additionalProperties"] is False


def test_el_esquema_estricto_elimina_las_palabras_clave_no_admitidas():
    """`default` y `maxLength` hacen que la API rechace el esquema entero."""
    import json as _json

    from pydantic import BaseModel, Field

    from src.modules.ai.infrastructure.providers.parsing import strict_schema

    class Modelo(BaseModel):
        titulo: str = Field(default="sin título", max_length=50)

    serializado = _json.dumps(strict_schema(Modelo))

    assert "default" not in serializado
    assert "maxLength" not in serializado
