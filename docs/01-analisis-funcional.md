# 01 · Análisis Funcional

**Producto:** Plataforma de Capacitaciones con IA (clon funcional de Plazzi + capa de Inteligencia Artificial)
**Nombre interno:** `Capacita IA`
**Versión del documento:** 1.0

---

## 1. Contexto y problema

Las empresas de software (ERP, WMS, CRM, portales) invierten una cantidad enorme de horas de consultores
senior en capacitar usuarios finales sobre sus productos. Ese conocimiento vive en:

- Videos de sesiones de capacitación grabadas (Teams / Zoom / Meet).
- Manuales en PDF, DOCX, PPTX.
- La cabeza de los consultores.

Los problemas concretos:

| # | Problema | Impacto |
|---|----------|---------|
| P1 | El video grabado es un bloque opaco de 2 horas. Nadie lo vuelve a ver. | Conocimiento inaccesible |
| P2 | El usuario tiene una duda puntual ("¿cómo anulo una guía de despacho?") y no sabe en qué minuto de qué video está. | Tickets de soporte evitables |
| P3 | No hay forma de medir si el usuario realmente entendió. | Riesgo en puesta en marcha |
| P4 | Crear exámenes manualmente por cada módulo del ERP es inviable. | No se evalúa |
| P5 | Cada cliente/proyecto tiene su propia parametrización; el conocimiento no es intercambiable. | Contenido genérico inútil |

## 2. Propuesta de valor

Una plataforma donde el administrador sube el material **una sola vez** y la IA lo transforma en una
experiencia de aprendizaje: transcripción indexada por minuto, capítulos, resumen, conceptos clave,
chat tipo ChatGPT restringido al contenido del curso (RAG), exámenes generados y corregidos
automáticamente, y un tutor virtual que adapta la explicación al nivel del usuario.

> **Regla de oro del producto:** la IA **nunca inventa**. Si la respuesta no está en el material del
> proyecto, responde "no encuentro esa información en este material" y sugiere al instructor.

## 3. Actores

| Actor | Descripción | Interfaz |
|-------|-------------|----------|
| **Superadministrador** | Gestiona empresas (tenants), planes y configuración global. | Admin |
| **Administrador de empresa** | Crea proyectos, capacitaciones, sube material, crea usuarios, asigna cursos, ve estadísticas. | Admin |
| **Instructor / Content Manager** | Crea y edita contenido y exámenes de los proyectos asignados. No gestiona usuarios. | Admin |
| **Usuario / Estudiante** | Consume capacitaciones, ve videos, chatea con la IA, rinde exámenes. | Usuario |
| **Sistema IA (agente)** | Actor no humano: procesa material, responde, genera y corrige evaluaciones. | — |
| **Worker asíncrono (Celery)** | Actor no humano: ejecuta el pipeline de ingesta. | — |

## 4. Dominio funcional (mapa de módulos)

```
┌────────────────────────────────────────────────────────────────────┐
│ M1 · Identidad y Acceso     M2 · Organización        M3 · Contenido│
│   Empresas, usuarios,         Proyectos /              Capacitación│
│   roles, permisos, JWT        Aplicaciones             Módulos     │
│   perfil, recuperación        (ERP, WMS, CRM)          Lecciones   │
│                                                        Materiales  │
├────────────────────────────────────────────────────────────────────┤
│ M4 · Aprendizaje            M5 · Inteligencia        M6 · Evaluación│
│   Inscripciones               Ingesta (Whisper)        Exámenes     │
│   Progreso                    Chunking + Embeddings    Preguntas    │
│   Reanudar video              FAISS por proyecto       Intentos     │
│   Notas                       RAG / Chat               Corrección IA│
│                               Agente (LangGraph)       Feedback     │
├────────────────────────────────────────────────────────────────────┤
│ M7 · Analítica              M8 · Plataforma                         │
│   Dashboard admin             Auditoría, logs, notificaciones       │
│   Progreso por usuario        WebSocket (tiempo real)               │
│   Uso de IA / costos          Almacenamiento de archivos            │
└────────────────────────────────────────────────────────────────────┘
```

## 5. Flujos funcionales principales

### 5.1 Flujo del Administrador (creación de conocimiento)

1. Crea un **Proyecto** (ej. "ERP Sistemas Expertos v12").
2. Crea una **Capacitación** dentro del proyecto (ej. "Módulo Inventario — Nivel Básico").
3. Estructura la capacitación en **Módulos** y **Lecciones**.
4. Sube el **Material** a una lección (video MP4 o documento PDF/DOCX/PPTX/TXT).
5. El material entra en estado `PENDING` → `PROCESSING` → `ANALYZING` → `AVAILABLE` (o `ERROR`).
   El admin ve el avance en tiempo real vía WebSocket.
6. Al quedar `AVAILABLE`, revisa lo que generó la IA: transcripción, capítulos, resumen, conceptos, FAQ.
7. Genera un **Examen** con IA (elige nº de preguntas, tipos, dificultad), lo revisa y lo publica.
8. **Asigna** la capacitación a usuarios o a grupos.
9. Monitorea **progreso**, resultados y consumo de IA.

### 5.2 Flujo del Usuario (consumo)

1. Inicia sesión → ve sus **cursos asignados** con % de avance.
2. Entra a una capacitación → reproductor de video con **transcripción sincronizada** y **capítulos**.
3. El progreso se guarda automáticamente (última posición, lecciones completadas).
4. Abre el **Chat IA** lateral y pregunta en lenguaje natural. La respuesta incluye **citas con
   timestamp** clickeables que saltan al minuto exacto del video.
5. Al completar el contenido, **rinde el examen**.
6. Recibe **corrección automática**: puntaje, respuesta correcta, explicación del error y
   **enlace a la sección del video/documento que debe repasar**.
7. Puede reintentar según la política del examen.

### 5.3 Flujo de la IA (ingesta)

```
Upload → Validación (MIME/tamaño/antivirus) → Cola Celery
   ↓
[VIDEO]  ffmpeg extrae audio (wav 16kHz mono)
   ↓
Whisper (faster-whisper) → transcripción con timestamps por segmento
   ↓
[DOCUMENTO] PyMuPDF / python-docx / python-pptx → texto + metadatos de página
   ↓
Normalización → Chunking semántico (con solapamiento) manteniendo start/end y página
   ↓
Embeddings (proveedor desacoplado) → índice FAISS del PROYECTO
   ↓
LLM: resumen ejecutivo · capítulos · conceptos clave · FAQ · banco de preguntas candidatas
   ↓
Estado AVAILABLE + notificación WebSocket
```

## 6. Reglas de negocio

| ID | Regla |
|----|-------|
| RN-01 | Todo dato pertenece a una **empresa (tenant)**. Ningún usuario puede leer datos de otra empresa. |
| RN-02 | Cada **proyecto** tiene su propia colección vectorial FAISS aislada. |
| RN-03 | El chat de una capacitación **solo** recupera chunks de esa capacitación (o del proyecto si el admin lo habilita). |
| RN-04 | Si el retriever no supera el umbral de similitud, la IA responde "sin información suficiente". Nunca alucina. |
| RN-05 | Un material en estado distinto de `AVAILABLE` no es consultable por el chat ni usable para generar exámenes. |
| RN-06 | Un examen generado por IA nace en estado `DRAFT`; requiere aprobación humana para pasar a `PUBLISHED`. |
| RN-07 | Un usuario solo puede rendir un examen si su progreso en la capacitación ≥ `min_progress_required` (por defecto 80 %). |
| RN-08 | Las preguntas abiertas y de respuesta corta se corrigen con LLM usando rúbrica; las cerradas, determinísticamente. |
| RN-09 | El nº de intentos está limitado por `max_attempts`; se conserva el mejor puntaje (configurable). |
| RN-10 | Los embeddings deben poder regenerarse sin pérdida: la fuente de verdad son los `chunks` en PostgreSQL. |
| RN-11 | Todo consumo de LLM se registra (tokens, modelo, costo estimado, usuario, propósito). |
| RN-12 | Eliminar un material elimina sus chunks y marca el índice del proyecto para reconstrucción. |

## 7. Estados

**Material:** `PENDING` → `PROCESSING` (extracción/transcripción) → `ANALYZING` (LLM + embeddings) → `AVAILABLE` | `ERROR`
**Capacitación:** `DRAFT` → `PUBLISHED` → `ARCHIVED`
**Inscripción:** `ASSIGNED` → `IN_PROGRESS` → `COMPLETED` | `EXPIRED`
**Examen:** `DRAFT` → `PUBLISHED` → `ARCHIVED`
**Intento:** `IN_PROGRESS` → `SUBMITTED` → `GRADING` → `GRADED`

## 8. Alcance del MVP

**Incluido:** M1–M7 completos con IA (Ollama local gratuito por defecto, OpenAI opcional),
Docker Compose dev/prod, WebSocket en contenedor independiente, Swagger.

**Excluido (post-MVP):** certificados PDF, gamificación, SCORM/xAPI, app móvil nativa,
video en vivo, subtítulos multi-idioma, SSO SAML.

## 9. Métricas de éxito

- ≥ 80 % de las preguntas del chat respondidas con cita válida (sin "no encuentro información").
- Tiempo de ingesta ≤ 1× la duración del video (con GPU) / ≤ 3× (CPU).
- Reducción de tickets de soporte de nivel 1 en el proyecto piloto.
- ≥ 70 % de aprobación en el primer intento de examen tras completar el curso.
