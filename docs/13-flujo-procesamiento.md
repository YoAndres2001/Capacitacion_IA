# 13 · Flujo de Procesamiento de Videos y Documentos

## 1. Vista general

```mermaid
flowchart TD
    A[Usuario sube archivo] --> B{Validación<br/>extensión · MIME real · tamaño · hash}
    B -->|inválido| B1[400 y descarte]
    B -->|válido| C[Material PENDING<br/>+ tarea Celery encolada]
    C --> D[Estado PROCESSING · WebSocket]
    D --> E{Tipo}
    E -->|VIDEO| V1[ffmpeg: metadatos + miniatura]
    V1 --> V2[ffmpeg: audio FLAC 16 kHz mono<br/>+ troceo si supera el tope de subida]
    V2 --> V3[Groq Whisper: transcripción<br/>segmentos con start/end globales]
    E -->|PDF| D1[PyMuPDF: texto por página + OCR si escaneado]
    E -->|DOCX| D2[python-docx: párrafos, tablas, títulos]
    E -->|PPTX| D3[python-pptx: diapositivas + notas]
    E -->|TXT/MD| D4[lectura directa con detección de encoding]
    V3 --> N[Normalización a bloques con ubicación]
    D1 --> N
    D2 --> N
    D3 --> N
    D4 --> N
    N --> O[Estado ANALYZING · WebSocket]
    O --> P[Chunking semántico<br/>800 tokens · 15% solape]
    P --> Q[Embeddings por lotes]
    Q --> R[FAISS: add + persistencia atómica]
    P --> S[LLM: capítulos]
    S --> T[LLM: resumen ejecutivo y por capítulo]
    T --> U[LLM: conceptos clave]
    U --> W[LLM: FAQ]
    W --> X[LLM: banco de preguntas candidatas]
    R --> Y
    X --> Y[Persistir todo en PostgreSQL]
    Y --> Z[Estado AVAILABLE · WebSocket · evento MaterialProcessed]
    B1 --> END[ ]
    D -->|excepción| ERR[Estado ERROR con error_code<br/>reintento con backoff máx. 3]
```

## 2. Etapas detalladas

### Etapa 0 · Carga

- Carga por trozos de 5 MB con reanudación; los trozos viven 24 h.
- Al completar: ensamblado, SHA-256, validación de MIME real con `python-magic`, verificación de duplicado
  por `(project_id, sha256)`.
- Límites: video 4 GB, documento 100 MB.
- El archivo se guarda en `media/{company}/{project}/{material_id}/original.{ext}` con permisos restringidos.

### Etapa 1 · Extracción (cola `ingest`)

**Video**
```bash
ffprobe -v error -show_format -show_streams          # duración, códecs, resolución
ffmpeg -i input.mp4 -ss 00:00:03 -vframes 1 thumb.jpg
ffmpeg -i input.mp4 -vn -ac 1 -ar 16000 -c:a flac audio.flac
```

16 kHz mono es la frecuencia a la que Whisper trabaja internamente, así que la conversión no
pierde información; FLAC es sin pérdida y pesa alrededor de la mitad que el WAV equivalente,
lo que importa porque el archivo viaja por red hasta Groq.

**Transcripción (API Speech-to-Text de Groq)**

```
POST {GROQ_BASE_URL}/audio/transcriptions
  file=audio.flac
  model={GROQ_WHISPER_MODEL}          # whisper-large-v3
  response_format=verbose_json
  timestamp_granularities[]=segment
```

Salida: `{"text": ..., "segments": [{"start", "end", "text"}], "language", "duration"}`.

**Audios que no caben en una petición.** El tope de subida son 24 MB (nivel gratuito de Groq
con margen para las cabeceras multipart). Por encima de eso:

1. `ffmpeg -f segment -segment_time 600 -c:a flac` parte el audio en trozos de 10 minutos
   (recodificando, no copiando: el copiado directo puede dejar cabeceras FLAC incompletas).
2. Cada trozo se envía por separado, con reintentos y respeto del 429.
3. A los timestamps de cada trozo se les **suma su desplazamiento**, calculado con la duración
   real de las partes anteriores (`ffprobe`) y no con el valor nominal, que iría acumulando
   error de décimas hasta desplazar las citas varios segundos en un video largo.
4. Los índices de segmento se renumeran de forma global: cada trozo los devuelve desde 0.
5. El idioma detectado en el primer trozo se reenvía **traducido a código ISO** en los
   siguientes: Groq lo devuelve por su nombre (`"Spanish"`) pero su parámetro `language`
   solo acepta el código (`"es"`), y reenviarlo tal cual devuelve 400.

Es el punto más delicado del pipeline: si se perdiera el desplazamiento, el chat citaría el
minuto equivocado sin dar ningún error. Está cubierto por
`src/tests/unit/test_groq_transcriber.py` y por el test de integración del pipeline de video.

**Verificado contra la API real** con un video de 93 s, comparando la transcripción en una
sola petición contra la misma troceada en cuatro: el final coincide (92,00 s frente a
92,04 s), es decir, no hay deriva acumulada. El troceo sí parte alguna frase en el límite
del corte (20 segmentos en vez de 17); el texto no se pierde y el chunking posterior vuelve
a agruparlo, así que no se añade solapamiento entre trozos por un artefacto que solo afecta
a audios de más de 24 MB.

Para audios largos, la transcripción se reporta por progreso (`processing_jobs.progress`) al
terminar cada trozo.

**Documentos**

| Formato | Librería | Se preserva |
|---------|----------|-------------|
| PDF | PyMuPDF (`fitz`) | Página, orden de bloques, títulos por tamaño de fuente. Si la página no tiene texto → OCR (`pytesseract`) |
| DOCX | `python-docx` | Jerarquía de encabezados, párrafos, tablas → Markdown |
| PPTX | `python-pptx` | Nº de diapositiva, título, cuerpo y **notas del presentador** |
| TXT/MD | Lectura directa | Encoding detectado con `charset-normalizer` |

Alternativa unificada disponible: `unstructured` para formatos complejos u OCR avanzado.

### Etapa 2 · Normalización

Todo extractor devuelve la misma estructura, de modo que las etapas siguientes son idénticas para
video y documento:

```python
@dataclass
class ContentBlock:
    text: str
    start_time: float | None    # video
    end_time: float | None      # video
    page: int | None            # documento
    heading: str | None
    order: int
```

### Etapa 3 · Chunking

Ver `11-diseno-rag.md` §3. Reglas: 800 tokens, 15 % de solape, corte en fin de oración,
no cruzar frontera de capítulo, metadatos de ubicación siempre presentes.

### Etapa 4 · Embeddings e indexación

```
lotes de 64 → EmbeddingsPort.embed_documents() → normalización L2
            → FaissVectorStore.add(vectors, ids) → write_index atómico
            → Chunk.embedded = True (transacción por lote)
```
Si el proceso se interrumpe, al reintentar solo se procesan los chunks con `embedded = false`.

### Etapa 5 · Análisis con LLM

El costo de esta etapa es **casi proporcional a los tokens que el modelo genera**.
Medido en CPU con `qwen2.5:1.5b-instruct`: ~2 tokens/s, es decir 250–570 s por
cadena. Por eso el análisis es adaptativo:

| Tamaño del contenido | Estrategia | Llamadas al LLM |
|----------------------|-----------|-----------------|
| ≤ `AI_COMPACT_ANALYSIS_CHARS` (5.000 por defecto) | **Análisis compacto**: una sola llamada devuelve resumen, conceptos y FAQ; el material se registra como un único capítulo | **1** |
| Mayor | Cadenas independientes: capítulos, resumen, conceptos y FAQ | 4 |

Un documento de una página no tiene capítulos que detectar, así que ejecutar
cuatro cadenas sobre él cuadruplica el tiempo sin aportar nada. Además cada
cadena declara su propio `max_tokens` (400–700) para que una respuesta
innecesariamente extensa no dispare el tiempo de proceso.

Cadenas del análisis completo, cada una con salida validada por Pydantic y
reintento correctivo:

| Cadena | Entrada | Salida |
|--------|---------|--------|
| Capítulos | Transcripción/documento comprimido con marcas de tiempo o página | `[{title, start, end, summary}]` |
| Resumen ejecutivo | Resúmenes por capítulo (map-reduce) | Texto de 150–300 palabras |
| Conceptos | Capítulos + chunks representativos | `[{name, definition, relevance, first_mention_time/page}]` |
| FAQ | Contenido completo comprimido | `[{question, answer}]` (6–12) |
| Preguntas candidatas | Chunks con cobertura por capítulo | Banco reutilizable en CU-13 |

Para materiales largos se usa **map-reduce**: resumen por capítulo → resumen de resúmenes. Así el
pipeline funciona incluso con modelos locales de ventana modesta (8k tokens).

### Etapa 6 · Cierre

- `Material.status = AVAILABLE` (o `partial_analysis = true` si alguna cadena LLM falló pero los
  embeddings sí se generaron: el chat ya es funcional).
- Se emite `MaterialProcessed`; el instructor recibe notificación y sugerencia de generar examen.
- Se registra el consumo total de IA del material.

## 3. Idempotencia y reintentos

| Aspecto | Implementación |
|---------|----------------|
| Idempotencia | Cada etapa comprueba si su salida ya existe (transcripción, chunks, embeddings) y la omite |
| Reintentos | `autoretry_for=(TransientError,)`, `retry_backoff=True`, `max_retries=3` |
| Reproceso | `POST /materials/{id}/reprocess` borra las salidas derivadas y reencola desde cero |
| Limpieza | Los temporales (`audio.flac`, trozos) se eliminan en `finally` |
| Trazabilidad | `processing_jobs` guarda paso, progreso, tiempos y error de cada ejecución |

## 4. Códigos de error del pipeline

| `error_code` | Causa | Acción sugerida |
|--------------|-------|-----------------|
| `INVALID_FILE_TYPE` | MIME real ≠ extensión | Volver a subir el archivo correcto |
| `FILE_TOO_LARGE` | Excede el límite | Comprimir o dividir |
| `AUDIO_EXTRACTION_FAILED` | Video corrupto o sin pista de audio | Verificar el archivo |
| `NO_SPEECH_DETECTED` | Audio sin voz | Revisar la grabación |
| `TRANSCRIPTION_FAILED` | Fallo de Whisper | Reintentar o usar un modelo menor |
| `EXTRACTION_FAILED` | Documento corrupto o protegido | Quitar la protección |
| `EMPTY_CONTENT` | No se obtuvo texto (PDF escaneado sin OCR) | Habilitar OCR |
| `EMBEDDING_PROVIDER_UNAVAILABLE` | No se pudo cargar el modelo local de embeddings | Revisar `EMBEDDING_MODEL` y el volumen de caché; el material queda reprocesable |
| `LLM_ANALYSIS_FAILED` | Fallo en las cadenas de análisis | El material queda `AVAILABLE` con `partial_analysis` |
| `INDEX_WRITE_FAILED` | Error de IO en el volumen de índices | Revisar disco/permisos |

## 5. Rendimiento estimado

| Escenario | Dónde corre | Tiempo aprox. |
|-----------|-------------|---------------|
| Video 60 min · extracción y troceo de audio (ffmpeg) | CPU local | 1–3 min |
| Video 60 min · transcripción con Groq Whisper (6 trozos) | Groq | 1–3 min |
| Embeddings de 400 chunks con `MiniLM-L12` en CPU | CPU local | 30–90 s |
| Análisis LLM (4 cadenas) con `llama-3.3-70b-versatile` | Groq | 20–60 s |
| Análisis LLM en el nivel gratuito, tocando el límite de 12k tokens/min | Groq | 2–5 min (con esperas de 429) |
| PDF de 200 páginas | CPU local | 1–2 min + embeddings |

> **El cuello de botella ya no es la CPU, sino la cuota.** Si las cadenas de análisis agotan
> el cupo por minuto y los reintentos no alcanzan, el material igual queda `AVAILABLE` con
> `partial_analysis = true`: el chat RAG funciona porque los embeddings son locales y no
> dependen de Groq. Es una degradación deliberada, no un fallo silencioso — el log indica
> exactamente qué bajar (`AI_ANALYSIS_MAX_CHARS`, `LLM_MAX_TOKENS` o `AI_EXAM_BATCH_SIZE`).

**Optimizaciones aplicadas:** troceo del audio solo cuando excede el tope de subida, lotes de
embeddings, cola `ingest` separada con concurrencia baja (`--concurrency=2`) para no saturar
CPU, modelo de embeddings cargado una vez por proceso worker y compartido en un volumen entre
contenedores, y análisis en una sola llamada cuando el material es corto
(`AI_COMPACT_ANALYSIS_CHARS`).

## 6. Diagrama de secuencia completo (documento PDF)

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant API as backend
    participant CE as celery-ingest
    participant AI as celery-ai / Groq
    participant DB as PostgreSQL
    participant FS as FAISS
    participant WS as websocket

    FE->>API: POST /lessons/{id}/materials (PDF)
    API->>API: valida MIME real + hash
    API->>DB: INSERT material (PENDING)
    API->>CE: ingest_material.delay(id)
    API-->>FE: 201 {status: PENDING}
    FE->>WS: suscripción a /ws/materials/{id}/
    CE->>DB: status = PROCESSING
    CE->>WS: status.changed PROCESSING
    CE->>CE: PyMuPDF → bloques por página (OCR si aplica)
    CE->>DB: status = ANALYZING
    CE->>WS: status.changed ANALYZING
    CE->>CE: chunking (800/120) con page
    CE->>DB: INSERT chunks
    CE->>AI: embed_documents(lotes de 64)
    AI-->>CE: vectores
    CE->>FS: add + write_index atómico
    CE->>DB: chunks.embedded = true
    CE->>AI: capítulos · resumen · conceptos · FAQ · preguntas
    AI-->>CE: JSON validado
    CE->>DB: INSERT chapters/concepts/faqs + summary
    CE->>DB: status = AVAILABLE
    CE->>WS: completed
    WS-->>FE: material disponible
```
