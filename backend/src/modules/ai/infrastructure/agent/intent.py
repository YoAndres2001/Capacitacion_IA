"""
Detección de intención sin LLM (docs/12-agente-ia.md §5).

La mayoría de las preguntas se resuelve con una sola pasada de RAG. Detectar la
intención con reglas evita una llamada extra al modelo, que en un despliegue
local con CPU cuesta segundos.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Intent(StrEnum):
    FACTUAL = "factual"
    TIMESTAMP = "timestamp"
    SUMMARY = "summary"
    SIMPLIFY = "simplify"
    EXAMPLE = "example"
    COMPARE = "compare"
    EXERCISE = "exercise"
    STEP_BY_STEP = "step_by_step"
    ASSESSMENT = "assessment"


PATTERNS: list[tuple[Intent, re.Pattern[str]]] = [
    (Intent.TIMESTAMP, re.compile(r"\bminuto\s*\d+|\bmin\s*\d+|\d{1,2}:\d{2}|en qué momento|dónde explica", re.I)),
    (Intent.SUMMARY, re.compile(r"\bresum(e|en|ir|me)\b|\bsíntesis\b|de qué trata", re.I)),
    (Intent.SIMPLIFY, re.compile(r"como si fuera (un )?principiante|explícamelo (fácil|simple)|más simple|no entiendo nada", re.I)),
    (Intent.EXAMPLE, re.compile(r"\bejemplo\b|\bejemplifica\b|dame un caso", re.I)),
    (Intent.COMPARE, re.compile(r"\bcompara\b|\bdiferencia(s)?\b|\bversus\b|\bvs\b|en qué se diferencia", re.I)),
    (Intent.EXERCISE, re.compile(r"\bejercicio(s)?\b|\bpractica(r)?\b|ponme a prueba", re.I)),
    (Intent.ASSESSMENT, re.compile(r"\bexamen\b|\bevaluación\b|\bprueba\b|\bcuestionario\b", re.I)),
    (Intent.STEP_BY_STEP, re.compile(r"paso a paso|\bprocedimiento\b|\bcómo se hace\b|\bcómo hago\b", re.I)),
]


def detect_intent(question: str) -> Intent:
    for intent, pattern in PATTERNS:
        if pattern.search(question):
            return intent
    return Intent.FACTUAL
