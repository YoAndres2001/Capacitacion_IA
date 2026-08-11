"""
Utilidades de parseo y normalización compartidas por los adaptadores de IA.

Viven fuera de `groq_provider` porque también las usa el adaptador de
embeddings locales (normalización L2) y las pruebas las ejercitan de forma
aislada, sin necesidad de un proveedor concreto.
"""

from __future__ import annotations

import json
from typing import Any

from src.shared.infrastructure.logging import get_logger

logger = get_logger("ai.parsing")


#: Palabras clave que el modo estricto de Structured Outputs no admite. Pydantic
#: las emite de forma natural (`default` por cada campo opcional, `maxLength` por
#: cada `Field(max_length=...)`) y su sola presencia hace que la API rechace el
#: esquema entero con un 400.
_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "default",
        "maxLength",
        "minLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
    }
)


def strict_schema(model: type) -> dict[str, Any]:
    """
    Traduce un modelo Pydantic al JSON Schema que exige Structured Outputs.

    El esquema que genera Pydantic no sirve tal cual: el modo estricto exige que
    todo objeto declare `additionalProperties: false` y liste **todos** sus
    campos en `required` (los opcionales se expresan admitiendo `null`), y no
    tolera las palabras clave de validación que Pydantic añade.

    Se deriva del modelo en vez de escribirlo a mano para que no puedan
    divergir: si mañana se añade un campo a la clase, el esquema lo acompaña.
    """
    schema = model.model_json_schema()  # type: ignore[attr-defined]
    definitions = schema.pop("$defs", {})
    return _tighten(_inline(schema, definitions))


def _inline(node: Any, definitions: dict[str, Any]) -> Any:
    """Sustituye cada `$ref` por su definición: el modo estricto no las resuelve."""
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            return _inline(definitions.get(reference.rsplit("/", 1)[-1], {}), definitions)
        return {key: _inline(value, definitions) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline(item, definitions) for item in node]
    return node


def _tighten(node: Any) -> Any:
    if isinstance(node, list):
        return [_tighten(item) for item in node]
    if not isinstance(node, dict):
        return node

    cleaned = {
        key: _tighten(value) for key, value in node.items() if key not in _UNSUPPORTED_KEYWORDS
    }
    properties = cleaned.get("properties")
    if isinstance(properties, dict):
        cleaned["type"] = "object"
        cleaned["additionalProperties"] = False
        cleaned["required"] = list(properties)
    return cleaned


def normalize(vector: list[float]) -> list[float]:
    """Normalización L2: permite usar producto interno como similitud coseno."""
    magnitude = sum(component * component for component in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [component / magnitude for component in vector]


def parse_json_loosely(content: str) -> Any:
    """
    Parsea JSON tolerando el ruido típico de una salida generada.

    Quita vallas de código, recorta hasta el primer `{`/`[` y el último `}`/`]`,
    y como último recurso repara una salida cortada a mitad (ver
    `repair_truncated_json`).
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    repaired = repair_truncated_json(text)
    if repaired is not None:
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            pass
        else:
            logger.warning(
                "Salida del modelo cortada por límite de tokens: se rescataron los "
                "elementos completos y se descartó el fragmento final a medias."
            )
            return parsed

    raise ValueError(f"El modelo no devolvió JSON válido: {content[:300]}")


def repair_truncated_json(text: str) -> str | None:
    """
    Reconstruye un JSON que el modelo dejó a medias al agotar `max_tokens`.

    En modo JSON la salida es válida hasta el punto en que se corta, así que
    basta con retroceder al último elemento que sí quedó completo y cerrar las
    estructuras que seguían abiertas. Un examen recupera así las preguntas que
    el modelo alcanzó a terminar en lugar de perder el lote entero.

    Devuelve `None` si no hay ningún elemento completo que rescatar.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    cut: tuple[int, tuple[str, ...]] | None = None

    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character in "{[":
            stack.append("}" if character == "{" else "]")
        elif character in "}]":
            if not stack or stack[-1] != character:
                return None  # JSON mal formado, no solo incompleto
            stack.pop()
            # Un elemento acaba de cerrarse. Si todavía queda algo abierto por
            # encima, este es un punto seguro por el que cortar.
            if stack:
                cut = (index + 1, tuple(stack))

    if cut is None:
        return None

    end, pending = cut
    return text[:end] + "".join(reversed(pending))
