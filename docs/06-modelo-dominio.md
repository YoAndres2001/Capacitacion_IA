# 06 · Modelo de Dominio

Lenguaje ubicuo y descripción de entidades, value objects, agregados, servicios y eventos de dominio.
Esta capa **no depende de Django**.

## 1. Lenguaje ubicuo

| Término | Definición |
|---------|-----------|
| **Empresa (Company)** | Tenant. Contenedor raíz de todo dato. |
| **Proyecto (Project)** | Aplicación o producto sobre el que se capacita (ERP, WMS, CRM). Dueño de una colección vectorial. |
| **Capacitación (Training)** | Curso dentro de un proyecto. Unidad que se asigna, se consume y se evalúa. |
| **Módulo (Module)** | Agrupación ordenada de lecciones dentro de una capacitación. |
| **Lección (Lesson)** | Unidad mínima de consumo. Puede ser video, documento o texto. |
| **Material** | Archivo físico asociado a una lección; es lo que la IA procesa. |
| **Transcripción (Transcript)** | Texto del audio con segmentos temporizados. |
| **Capítulo (Chapter)** | Tramo temático del material con inicio, fin y resumen. |
| **Concepto (Concept)** | Término clave detectado con su definición y ubicación. |
| **Fragmento (Chunk)** | Porción de texto indexable con su metadato de ubicación. Fuente de verdad del RAG. |
| **Colección vectorial** | Índice FAISS de un proyecto. |
| **Inscripción (Enrollment)** | Vínculo entre usuario y capacitación, con progreso. |
| **Examen (Exam)** | Instrumento de evaluación de una capacitación. |
| **Intento (Attempt)** | Ejecución de un examen por un usuario. |
| **Cita (Citation)** | Referencia verificable a un fragmento usado en una respuesta de IA. |

## 2. Agregados

```
Agregado COMPANY          raíz: Company
Agregado USER             raíz: User
Agregado PROJECT          raíz: Project        → VectorCollection
Agregado TRAINING         raíz: Training       → Module → Lesson
Agregado MATERIAL         raíz: Material       → Transcript(Segment) → Chapter → Concept → Faq → Chunk
Agregado ENROLLMENT       raíz: Enrollment     → LessonProgress
Agregado EXAM             raíz: Exam           → Question → QuestionOption
Agregado ATTEMPT          raíz: Attempt        → Answer
Agregado CHAT             raíz: ChatSession    → ChatMessage → Citation
```

**Invariantes por agregado**

- `Training` no puede publicarse sin al menos una lección con material `AVAILABLE`.
- `Material` no expone contenido consultable si su estado ≠ `AVAILABLE`.
- `Exam` publicado no admite modificación de preguntas si ya tiene intentos.
- `Attempt` no puede pasar a `GRADED` con respuestas sin corregir.
- `Enrollment.progress` ∈ [0, 100] y se deriva de `LessonProgress`, nunca se asigna a mano.

## 3. Value Objects

| VO | Reglas |
|----|--------|
| `Email` | Formato válido, normalizado a minúsculas. Inmutable. |
| `Slug` | `^[a-z0-9]+(-[a-z0-9]+)*$`, 2–60 caracteres. |
| `TimeRange` | `start >= 0`, `end > start`. Métodos `duration`, `contains(t)`, `overlaps(other)`. |
| `Score` | 0–100 con 2 decimales. Operaciones seguras de suma ponderada. |
| `Percentage` | 0–100. |
| `FileMetadata` | `filename`, `size_bytes`, `mime_type`, `sha256`. Valida extensión permitida por tipo. |
| `Citation` | `material_id`, `chunk_id`, `label`, `start_time?`, `page?`. Debe apuntar a un chunk existente. |
| `TokenUsage` | `prompt_tokens`, `completion_tokens`, `model`, `cost_usd`. |

## 4. Enumeraciones

```python
Role            = SUPERADMIN | ADMIN | INSTRUCTOR | STUDENT
ProjectStatus   = ACTIVE | ARCHIVED
TrainingStatus  = DRAFT | PUBLISHED | ARCHIVED
TrainingLevel   = BEGINNER | INTERMEDIATE | ADVANCED
LessonType      = VIDEO | DOCUMENT | TEXT | QUIZ
MaterialType    = VIDEO | PDF | DOCX | PPTX | TXT | MD | AUDIO
MaterialStatus  = PENDING | PROCESSING | ANALYZING | AVAILABLE | ERROR
EnrollmentStatus= ASSIGNED | IN_PROGRESS | COMPLETED | EXPIRED
ExamStatus      = DRAFT | PUBLISHED | ARCHIVED
QuestionType    = SINGLE_CHOICE | MULTIPLE_CHOICE | TRUE_FALSE | SHORT_ANSWER | OPEN_ENDED
AttemptStatus   = IN_PROGRESS | SUBMITTED | GRADING | GRADED | EXPIRED
MessageRole     = USER | ASSISTANT | SYSTEM | TOOL
ScorePolicy     = BEST | LAST | AVERAGE
```

## 5. Entidades principales (contrato)

### `Material` (raíz de agregado)

```python
@dataclass
class Material:
    id: UUID
    lesson_id: UUID
    project_id: UUID
    metadata: FileMetadata
    type: MaterialType
    status: MaterialStatus
    duration_seconds: int | None
    error_code: str | None
    processed_at: datetime | None
    partial_analysis: bool

    # Transiciones de estado — únicas formas legales de cambiar `status`
    def mark_processing(self) -> None
    def mark_analyzing(self) -> None
    def mark_available(self, *, partial: bool = False) -> None
    def mark_error(self, code: str, detail: str = "") -> None
    def can_be_reprocessed(self) -> bool           # status in {AVAILABLE, ERROR}
    def is_queryable(self) -> bool                 # status == AVAILABLE
```

Transiciones válidas (cualquier otra lanza `InvalidStateTransition`):

```
PENDING    → PROCESSING | ERROR
PROCESSING → ANALYZING  | ERROR
ANALYZING  → AVAILABLE  | ERROR
AVAILABLE  → PROCESSING          (reproceso)
ERROR      → PROCESSING          (reintento)
```

### `Enrollment`

```python
def recalculate_progress(self, lesson_progresses: list[LessonProgress], total_lessons: int) -> None:
    """progress = completadas / total * 100. Al llegar a 100 → COMPLETED con completed_at."""

def can_take_exam(self, exam: Exam) -> bool:
    """progress >= exam.min_progress_required"""
```

### `Attempt`

```python
def submit(self, at: datetime) -> None            # IN_PROGRESS → SUBMITTED
def start_grading(self) -> None                   # SUBMITTED  → GRADING
def apply_grade(self, answers: list[Answer], passing_score: int) -> None
    """Suma puntos obtenidos / totales → Score; passed = score >= passing_score; → GRADED"""
def is_expired(self, now: datetime) -> bool       # time_limit_minutes superado
```

### `Exam`

```python
def publish(self) -> None
    """Requiere >= 1 pregunta, suma de puntos > 0 y todas con respuesta correcta definida."""
def can_edit_questions(self, has_attempts: bool) -> bool
    """False si status == PUBLISHED y has_attempts."""
```

## 6. Servicios de dominio

| Servicio | Responsabilidad (lógica pura, sin IO) |
|----------|---------------------------------------|
| `ProgressCalculator` | Calcula el avance de una capacitación a partir del progreso de lecciones y sus pesos. |
| `CitationPolicy` | Valida que toda cita de una respuesta corresponda a un chunk realmente recuperado; descarta las inválidas. |
| `GroundingPolicy` | Decide si el contexto recuperado es suficiente (umbral de score, nº mínimo de chunks, cobertura). |
| `ScoringService` | Calcula el puntaje de un intento según `ScorePolicy` y ponderaciones. |
| `AnswerMatcher` | Corrección determinística de preguntas cerradas y normalización de respuesta corta. |
| `ChunkingPolicy` | Define tamaño, solapamiento y reglas de corte respetando límites de oración y de capítulo. |
| `QuestionValidator` | Verifica que una pregunta generada sea válida y no duplicada semánticamente. |
| `MaterialStateMachine` | Centraliza las transiciones legales de estado. |

## 7. Eventos de dominio

| Evento | Emisor | Consumidores |
|--------|--------|--------------|
| `MaterialUploaded` | Caso de uso de subida | Encolar ingesta |
| `MaterialStatusChanged` | `Material` | WebSocket, auditoría |
| `MaterialProcessed` | Pipeline de ingesta | Sugerir generación de examen; notificar instructor |
| `TrainingPublished` | `Training` | Notificar a usuarios asignados |
| `UserEnrolled` | Caso de uso de asignación | Email de bienvenida al curso |
| `LessonCompleted` | Progreso | Recalcular avance; verificar habilitación de examen |
| `TrainingCompleted` | `Enrollment` | Habilitar examen final / futuro certificado |
| `AttemptGraded` | Corrección | Notificar resultado; analítica |
| `AIQueryAnswered` | Chat | Registro de consumo y analítica |
| `AIAnsweredWithoutContext` | Chat | Alertar al instructor: hay una brecha de contenido |

Los eventos se publican mediante `EventPublisherPort`; en la infraestructura se traducen a
`group_send` de Redis (tiempo real) y/o tareas Celery (efectos secundarios).

## 8. Excepciones de dominio

```
DomainError
├── ValidationError            (VO inválido)
├── InvalidStateTransition     (estado ilegal)
├── BusinessRuleViolation
│   ├── TrainingNotPublishable
│   ├── ExamNotPublishable
│   ├── ExamLocked             (tiene intentos)
│   ├── MaxAttemptsReached
│   ├── InsufficientProgress
│   └── MaterialNotQueryable
├── NotFoundError
└── PermissionDeniedError
```

Cada excepción de dominio se mapea en `presentation` a un código HTTP y a un `error_code` estable
documentado en la API (ver `10-api-rest.md`).
