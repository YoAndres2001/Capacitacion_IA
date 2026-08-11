# Verificación ejecutada

Registro de lo que se probó realmente sobre el sistema en marcha, no de lo que
debería funcionar. Ejecutado el 2026-08-03 sobre Windows 11 + Docker Desktop,
CPU sin GPU, con Ollama como proveedor de IA (costo US$ 0).

> **Documento histórico.** Corresponde al estado del sistema *antes* de la
> refactorización que dejó a **Groq como único proveedor externo de IA**. Se
> conserva porque documenta defectos reales encontrados y corregidos, pero los
> nombres de variables y modelos que aparecen aquí (`OLLAMA_*`, `faster-whisper`)
> ya no existen. Para la configuración vigente, ver el README y
> [docs/05-arquitectura.md](05-arquitectura.md).

## Infraestructura

| Verificación | Resultado |
|--------------|-----------|
| `docker compose up -d` levanta los 13 servicios | OK |
| Los 12 servicios de larga vida quedan `healthy` | OK |
| `migrate` aplica migraciones y siembra datos demo | OK |
| `GET /health/live` | `{"status": "ok"}` |
| `GET /health/ready` | base de datos, cache y almacenamiento OK |
| Swagger en `/api/docs/` | HTTP 200 |
| WebSocket independiente (Daphne) responde y queda `healthy` | OK |

## Backend

| Verificación | Resultado |
|--------------|-----------|
| `manage.py check` | sin incidencias |
| Migraciones generadas para los 5 módulos con modelos | OK |
| Tests unitarios de dominio (`pytest src/tests/unit`) | **37 pasan** |
| Login JWT con claims de rol y empresa | OK |
| Aislamiento por empresa en los listados | OK |
| Rate limiting por `throttle_scope` | activo |

## Pipeline de IA (extremo a extremo, con modelos gratuitos)

Documento real de 3,3 KB subido a una lección, procesado completo:

| Etapa | Resultado |
|-------|-----------|
| Validación de MIME real y hash | OK |
| Extracción de contenido (Markdown) | OK |
| Chunking con metadatos de ubicación | 2 fragmentos |
| Embeddings (`nomic-embed-text`, 768 dim) | 2/2 indexados |
| Índice FAISS en disco por proyecto | `index.faiss`, `mapping.json`, `meta.json` |
| Capítulos detectados por el LLM | **5**, coinciden con la estructura real del documento |
| Conceptos clave extraídos | **11** (inventario, stock físico, stock comprometido…) |
| Preguntas frecuentes generadas | **11** |
| Resumen ejecutivo | 573 caracteres, fiel al contenido |
| `partial_analysis` | `false` (las 4 cadenas completaron) |
| Costo total | **US$ 0** (modelo local) |

## Chat RAG y garantía anti-alucinación (RN-04)

| Caso | Pregunta | Resultado |
|------|----------|-----------|
| Dentro del material | "¿Cómo se calcula el costo promedio ponderado?" | Responde con la fórmula exacta del documento · `grounded: true` · **2 citas verificables** |
| Dentro del material | "¿Qué requisitos tiene un ajuste de inventario?" | Los 3 requisitos correctos (motivo, centro de costo, autorización sobre 50 UF) |
| Dentro del material | "Explícame los tipos de stock como principiante" | Adapta el nivel sin salirse del material |
| **Fuera del material** | "¿Cuál es la capital de Mongolia?" | *"No encuentro esa información en el material de esta capacitación."* · `grounded: false` · sin citas |
| **Fuera del material** | "¿Quién ganó el mundial de 1986?" | Misma respuesta honesta · `grounded: false` |

## Defectos encontrados y corregidos durante la verificación

Estos no son hipotéticos: aparecieron al ejecutar el sistema.

| # | Defecto | Corrección |
|---|---------|-----------|
| 1 | `throttle_scope` en `@action` rompía el arranque de los ViewSets | Atributo declarado a nivel de clase + `ScopedRateThrottle` en los defaults de DRF |
| 2 | El worker de ingesta no arrancaba: su imagen no instala dependencias de desarrollo | `settings/dev.py` agrega `django_extensions` solo si está disponible |
| 3 | Los workers Celery aparecían `unhealthy` (heredaban un healthcheck HTTP) | Healthcheck propio con `celery inspect ping`; `beat` sin healthcheck |
| 4 | El contenedor `websocket` aparecía `unhealthy` (healthcheck apuntaba al 8000) | Healthcheck propio en el puerto 8001 |
| 5 | nginx devolvía 502 tras recrear un contenedor (resolvía la IP solo al arrancar) | `resolver 127.0.0.11` + upstream en variable para re-resolución en caliente |
| 6 | Puertos publicados chocaban con otros proyectos de la máquina | Todos los puertos parametrizados con variables `PORT_*` |
| 7 | Un modelo de 7B en CPU superaba el timeout y dejaba el análisis incompleto | Modelo por defecto apto para CPU, `OLLAMA_TIMEOUT` a 900 s, `AI_ANALYSIS_MAX_CHARS` configurable y comando `ai_bench` de diagnóstico |
| 8 | **La IA respondía preguntas ajenas al material** (fallaba RN-04) | `AnswerGroundingVerifier`: verificación léxica posterior a la generación + instrucciones reforzadas junto a la pregunta. Cubierto por tests |
| 9 | Nunca se emitían citas (el modelo pequeño ignora los marcadores `[n]`) | `CitationPolicy.infer_from_overlap` deduce las fuentes reales por solapamiento. Cubierto por tests |
| 10 | Una salida no-JSON del modelo hacía fallar la tarea completa de generación de examen | `_ask_llm` captura el error de parseo y reintenta con instrucción correctiva |
| 11 | La generación de exámenes ignoraba el límite de contexto configurable | Usa el mismo `AI_ANALYSIS_MAX_CHARS` que las cadenas de análisis |
| 12 | Pedir todas las preguntas en una sola llamada no completaba nunca en CPU | Generación **por lotes** (`AI_EXAM_BATCH_SIZE`), un tipo de pregunta por llamada y rotación del material entre lotes. Medido: 3 preguntas en 465 s donde antes no volvía |
| 13 | **La IA generaba preguntas de temas ajenos al curso** (neurociencia en un curso de inventario) | Filtro de anclaje `_is_about_material`: cada pregunta debe compartir vocabulario con el material o se descarta. Cubierto por tests |
| 14 | **Crear una lección devolvía 405** (`POST /modules/{id}/lessons/`): `http_method_names` del ViewSet excluía `post` y eso bloquea también sus `@action` | Se componen mixins en vez de `ModelViewSet` en `ModuleViewSet`, `LessonViewSet`, `MaterialViewSet` y `ChatSessionViewSet`: las @action anidadas funcionan y la ruta de lista deja de exponer un `create` que habría producido registros huérfanos (lección sin módulo, material sin archivo) |
| 15 | Eliminar un material **no cancelaba su procesamiento**: la tarea seguía consumiendo un worker y CPU sobre contenido ya borrado, dejando las subidas siguientes en cola | El borrado revoca la tarea Celery (para eso existía `celery_task_id`, que nunca se llenaba) y el pipeline comprueba entre etapas si el material desapareció, abortando limpio y quitando los fragmentos huérfanos |
| 16 | El análisis ejecutaba **4 cadenas del LLM incluso para un documento de una página**, cuadruplicando el tiempo sin aportar nada (un documento corto no tiene capítulos que detectar) | Análisis adaptativo: bajo `AI_COMPACT_ANALYSIS_CHARS` se resuelve en **una sola llamada**. Medido: 367 s frente a más de 20 min |
| 17 | **`num_ctx` fijo en 8192** en todas las llamadas, cuando los prompts usan 400–1500 tokens | Ventana calculada por llamada (`fit_context`). Medido con el mismo prompt: 0,8 tok/s con ctx 8192 frente a 2,6 tok/s con ctx 2048 — **hasta 4× más rápido**. Cubierto por tests |

## Frontend

| Verificación | Resultado |
|--------------|-----------|
| `tsc --noEmit` con `strict: true` | sin errores |
| `npm run build` | OK · bundle inicial 209 kB (67 kB gz), MUI en chunk aparte |
| Carga diferida por feature | 14 chunks independientes |

## Pendiente de probar en este equipo

### Transcripción de video con Whisper

Implementada y con su worker dedicado (`celery-ingest` incluye `ffmpeg`,
`faster-whisper` y los extractores). No se ejecutó porque transcribir en CPU sin
GPU toma alrededor de 3× la duración del video, y esta máquina ya estaba al
límite con el resto del stack.

### Generación de exámenes con IA

El **mecanismo completo está verificado ejecutándose**; lo que no alcanza es la
capacidad del modelo pequeño.

| Aspecto | Estado |
|---------|--------|
| Endpoint y encolado asíncrono | OK — 202 con `task_id` |
| Guard `InsufficientContent` | OK — rechaza material insuficiente (2 fragmentos frente a los 5 exigidos) |
| Selección de fragmentos con cobertura por capítulo | OK |
| Generación por lotes con rotación del material | OK — **3/3 preguntas creadas en 465 s** |
| Reintento ante salida no parseable | OK — se observó recuperarse de un JSON truncado |
| Validación estructural de las preguntas | OK — **21 tests unitarios** |
| Persistencia con trazabilidad al fragmento de origen | OK |
| **Calidad del contenido con `qwen2.5:1.5b-instruct`** | **Insuficiente** |

**El hallazgo.** El modelo de 1.5B ignoró el material y generó preguntas sobre
neurociencia dentro de un curso de gestión de inventario. Se reforzó el prompt
(material primero, restricción repetida justo antes de la orden) y el
comportamiento persistió: no es un problema de prompt sino de capacidad del
modelo. Un 1.5B resuelve bien el chat RAG —donde el recuperador hace el trabajo
pesado y la respuesta está acotada— pero no la *generación* anclada.

**Lo que se hizo al respecto.** Se añadió un filtro de anclaje (`_is_about_material`)
que mide el solapamiento léxico entre el enunciado más su clave y el vocabulario
del material. En la prueba real descartó las dos preguntas inventadas y el examen
quedó con cero preguntas, que es el resultado correcto: **un examen sobre
neurociencia en un curso de inventario es peor que no tener examen**. El
administrador ve el examen vacío en borrador y sabe que debe reintentarlo con
otro modelo.

**Cómo obtener exámenes usables:**

```dotenv
OLLAMA_LLM_MODEL=qwen2.5:7b-instruct   # requiere GPU para tiempos razonables
AI_EXAM_BATCH_SIZE=5
AI_ANALYSIS_MAX_CHARS=10000
```

Antes de generar, conviene medir el hardware:

```bash
docker compose exec backend python manage.py ai_bench
```

Si la prueba de "salida JSON estructurada" supera los 30 s, el comando lo advierte
explícitamente.

## Cómo reproducir

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend python manage.py ai_bench      # diagnóstico de rendimiento
docker compose exec backend pytest src/tests/unit -q       # 37 tests
```

Luego seguir el recorrido descrito en el README (subir material, revisar el análisis,
publicar y conversar con el tutor).
