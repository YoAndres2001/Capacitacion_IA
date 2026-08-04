"""
Dimensionamiento de la ventana de contexto.

En CPU el `num_ctx` declarado domina el rendimiento: medido en este proyecto,
bajar de 8192 a 2048 multiplicó la velocidad por 2–4 con el mismo prompt. Estas
pruebas fijan el comportamiento para que nadie vuelva a poner un valor grande
fijo "por si acaso".
"""

from __future__ import annotations

import pytest

from src.modules.ai.infrastructure.providers.ollama import CONTEXT_BUCKETS, fit_context

pytestmark = pytest.mark.unit


def test_un_prompt_corto_usa_la_ventana_minima():
    assert fit_context(prompt_chars=400, max_output_tokens=200) == 2048


def test_la_ventana_crece_con_el_prompt():
    pequena = fit_context(prompt_chars=400, max_output_tokens=200)
    grande = fit_context(prompt_chars=20_000, max_output_tokens=200)
    assert grande > pequena


def test_la_ventana_considera_la_salida_esperada():
    """Pedir 2.000 tokens de salida no cabe en la ventana mínima."""
    corta = fit_context(prompt_chars=400, max_output_tokens=200)
    larga = fit_context(prompt_chars=400, max_output_tokens=2000)
    assert larga > corta


def test_nunca_supera_el_techo_configurado(settings):
    settings.AI_SETTINGS = {
        **settings.AI_SETTINGS,
        "OLLAMA": {**settings.AI_SETTINGS["OLLAMA"], "MAX_CTX": 4096},
    }
    assert fit_context(prompt_chars=200_000, max_output_tokens=4000) == 4096


def test_siempre_devuelve_un_tamano_valido():
    for chars in (0, 1_000, 10_000, 100_000):
        assert fit_context(chars, 500) in CONTEXT_BUCKETS


def test_deja_margen_para_la_plantilla_de_chat():
    """
    Un prompt que ocupa justo la ventana debe subir al siguiente escalón: el
    modelo añade tokens de plantilla que no están en el texto.
    """
    # 2048 tokens ≈ 8192 caracteres; con margen ya no cabe en 2048.
    assert fit_context(prompt_chars=8192, max_output_tokens=0) > 2048
