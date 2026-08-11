"""
Los capítulos de un video no pueden llevar timestamps inventados.

El prompt muestra el contenido con marcas `[mm:ss]`, pero el modelo redondea,
interpola y a veces inventa. Un capítulo en el minuto 47 de un video de 30 hace
que el reproductor salte al vacío, y nadie lo detecta hasta que un alumno hace
clic. Estas pruebas fijan el anclaje a segmentos reales de la transcripción.
"""

from __future__ import annotations

import pytest

from src.modules.ai.domain.chunking import SourceBlock
from src.modules.ai.infrastructure.analysis import ChapterOut, ground_chapter_times

pytestmark = pytest.mark.unit


def _blocks(*spans: tuple[float, float]) -> list[SourceBlock]:
    return [
        SourceBlock(text=f"segmento {index}", order=index, start_time=start, end_time=end)
        for index, (start, end) in enumerate(spans)
    ]


def test_un_timestamp_aproximado_se_ancla_al_segmento_real():
    blocks = _blocks((0.0, 8.0), (8.0, 320.5), (320.5, 640.0))

    grounded = ground_chapter_times([ChapterOut(title="Configuración", start=318.0)], blocks)

    assert grounded[0].start == 320.5


def test_un_timestamp_fuera_del_video_se_trae_al_ultimo_segmento():
    """El caso peligroso: el modelo cita un minuto que no existe."""
    blocks = _blocks((0.0, 60.0), (60.0, 120.0))

    grounded = ground_chapter_times([ChapterOut(title="Cierre", start=2800.0)], blocks)

    assert grounded[0].start == 60.0


def test_se_descarta_el_capitulo_sin_inicio():
    blocks = _blocks((0.0, 10.0))

    grounded = ground_chapter_times(
        [ChapterOut(title="Sin tiempo"), ChapterOut(title="Con tiempo", start=1.0)], blocks
    )

    assert [chapter.title for chapter in grounded] == ["Con tiempo"]


def test_un_fin_anterior_al_inicio_se_deja_vacio():
    """Guardar un rango imposible rompería el enlace del capítulo en el reproductor."""
    blocks = _blocks((0.0, 10.0), (300.0, 320.0))

    grounded = ground_chapter_times([ChapterOut(title="Raro", start=305.0, end=2.0)], blocks)

    assert grounded[0].start == 300.0
    assert grounded[0].end is None


def test_dos_capitulos_en_el_mismo_segmento_se_funden():
    blocks = _blocks((0.0, 10.0), (600.0, 620.0))

    grounded = ground_chapter_times(
        [
            ChapterOut(title="Inventario", start=598.0),
            ChapterOut(title="Inventario cíclico", start=601.0),
        ],
        blocks,
    )

    assert len(grounded) == 1


def test_los_capitulos_quedan_ordenados_por_tiempo():
    blocks = _blocks((0.0, 10.0), (100.0, 110.0), (200.0, 210.0))

    grounded = ground_chapter_times(
        [
            ChapterOut(title="Tercero", start=205.0),
            ChapterOut(title="Primero", start=1.0),
            ChapterOut(title="Segundo", start=101.0),
        ],
        blocks,
    )

    assert [chapter.title for chapter in grounded] == ["Primero", "Segundo", "Tercero"]


def test_sin_tiempos_en_la_transcripcion_no_se_toca_nada():
    """Un documento no tiene timestamps: la lista pasa intacta."""
    blocks = [SourceBlock(text="página", order=0, page=3)]
    chapters = [ChapterOut(title="Capítulo", start_page=3)]

    assert ground_chapter_times(chapters, blocks) is chapters
