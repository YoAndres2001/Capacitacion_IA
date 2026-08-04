# 07 · Modelo de Datos · Diagrama ER

PostgreSQL 17. Todas las claves primarias son `UUID v4`. Todas las tablas incluyen
`created_at`, `updated_at` y, donde aplica, `deleted_at` (borrado lógico).

## 1. Diagrama ER

```mermaid
erDiagram
    COMPANY ||--o{ USER : "emplea"
    COMPANY ||--o{ PROJECT : "posee"
    COMPANY ||--o{ USER_GROUP : "define"

    USER ||--o{ PROJECT_MEMBER : "participa"
    USER ||--o{ ENROLLMENT : "cursa"
    USER ||--o{ CHAT_SESSION : "conversa"
    USER ||--o{ ATTEMPT : "rinde"
    USER ||--o{ AUDIT_LOG : "genera"
    USER }o--o{ USER_GROUP : "pertenece"

    PROJECT ||--o{ PROJECT_MEMBER : "tiene"
    PROJECT ||--|| VECTOR_COLLECTION : "posee"
    PROJECT ||--o{ TRAINING : "contiene"

    TRAINING ||--o{ MODULE : "estructura"
    TRAINING ||--o{ ENROLLMENT : "asigna"
    TRAINING ||--o{ EXAM : "evalúa"
    TRAINING ||--o{ CHAT_SESSION : "habilita"

    MODULE ||--o{ LESSON : "agrupa"
    LESSON ||--o{ MATERIAL : "adjunta"
    LESSON ||--o{ LESSON_PROGRESS : "registra"
    LESSON ||--o{ NOTE : "recibe"

    MATERIAL ||--o| TRANSCRIPT : "produce"
    MATERIAL ||--o{ CHAPTER : "divide"
    MATERIAL ||--o{ CONCEPT : "extrae"
    MATERIAL ||--o{ FAQ : "genera"
    MATERIAL ||--o{ CHUNK : "fragmenta"
    MATERIAL ||--o{ PROCESSING_JOB : "traza"

    TRANSCRIPT ||--o{ TRANSCRIPT_SEGMENT : "compone"

    ENROLLMENT ||--o{ LESSON_PROGRESS : "detalla"

    EXAM ||--o{ QUESTION : "contiene"
    EXAM ||--o{ ATTEMPT : "recibe"
    QUESTION ||--o{ QUESTION_OPTION : "ofrece"
    QUESTION ||--o{ ANSWER : "responde"
    ATTEMPT ||--o{ ANSWER : "agrupa"

    CHAT_SESSION ||--o{ CHAT_MESSAGE : "contiene"
    CHAT_MESSAGE ||--o{ MESSAGE_CITATION : "cita"
    CHUNK ||--o{ MESSAGE_CITATION : "es citado en"

    COMPANY ||--o{ AI_USAGE_LOG : "consume"

    COMPANY {
        uuid id PK
        varchar name
        varchar slug UK
        varchar tax_id
        varchar logo
        jsonb settings
        boolean is_active
        timestamptz created_at
    }

    USER {
        uuid id PK
        uuid company_id FK
        citext email UK
        varchar password
        varchar first_name
        varchar last_name
        varchar role
        varchar job_title
        varchar avatar
        varchar language
        varchar timezone
        boolean is_active
        boolean is_staff
        timestamptz last_login
        timestamptz created_at
    }

    PROJECT {
        uuid id PK
        uuid company_id FK
        varchar name
        varchar slug
        text description
        varchar code
        varchar color
        varchar icon
        varchar status
        timestamptz created_at
        timestamptz deleted_at
    }

    VECTOR_COLLECTION {
        uuid id PK
        uuid project_id FK UK
        varchar index_path
        varchar embedding_model
        integer dimension
        integer vector_count
        varchar status
        timestamptz last_rebuilt_at
    }

    TRAINING {
        uuid id PK
        uuid project_id FK
        varchar title
        varchar slug
        text description
        varchar level
        varchar cover_image
        integer estimated_minutes
        varchar status
        boolean chat_enabled
        boolean cross_material_search
        uuid created_by FK
        timestamptz published_at
        timestamptz created_at
        timestamptz deleted_at
    }

    MODULE {
        uuid id PK
        uuid training_id FK
        varchar title
        text description
        integer order
    }

    LESSON {
        uuid id PK
        uuid module_id FK
        varchar title
        text description
        varchar type
        integer order
        integer duration_seconds
        boolean is_mandatory
        text content
    }

    MATERIAL {
        uuid id PK
        uuid lesson_id FK
        uuid project_id FK
        varchar original_filename
        varchar file
        varchar mime_type
        bigint size_bytes
        char sha256
        varchar type
        varchar status
        varchar error_code
        text error_detail
        integer duration_seconds
        varchar thumbnail
        varchar language
        text summary
        boolean partial_analysis
        timestamptz processed_at
        timestamptz created_at
    }

    TRANSCRIPT {
        uuid id PK
        uuid material_id FK UK
        varchar language
        text full_text
        varchar model
        real confidence
    }

    TRANSCRIPT_SEGMENT {
        uuid id PK
        uuid transcript_id FK
        integer index
        real start_time
        real end_time
        text text
    }

    CHAPTER {
        uuid id PK
        uuid material_id FK
        integer order
        varchar title
        text summary
        real start_time
        real end_time
        integer start_page
        integer end_page
    }

    CONCEPT {
        uuid id PK
        uuid material_id FK
        varchar name
        text definition
        real relevance
        real first_mention_time
        integer page
    }

    FAQ {
        uuid id PK
        uuid material_id FK
        text question
        text answer
        integer order
    }

    CHUNK {
        uuid id PK
        uuid material_id FK
        uuid project_id FK
        uuid training_id FK
        integer index
        text content
        integer token_count
        real start_time
        real end_time
        integer page
        uuid chapter_id FK
        bigint faiss_id UK
        boolean embedded
        tsvector search_vector
    }

    PROCESSING_JOB {
        uuid id PK
        uuid material_id FK
        varchar celery_task_id
        varchar step
        varchar status
        integer progress
        text error
        timestamptz started_at
        timestamptz finished_at
    }

    ENROLLMENT {
        uuid id PK
        uuid user_id FK
        uuid training_id FK
        varchar status
        numeric progress
        timestamptz assigned_at
        timestamptz started_at
        timestamptz completed_at
        timestamptz due_date
        uuid assigned_by FK
    }

    LESSON_PROGRESS {
        uuid id PK
        uuid enrollment_id FK
        uuid lesson_id FK
        boolean completed
        integer position_seconds
        integer watched_seconds
        timestamptz last_viewed_at
        timestamptz completed_at
    }

    NOTE {
        uuid id PK
        uuid user_id FK
        uuid lesson_id FK
        text content
        real timestamp_seconds
    }

    EXAM {
        uuid id PK
        uuid training_id FK
        varchar title
        text description
        varchar status
        integer passing_score
        integer max_attempts
        integer time_limit_minutes
        integer min_progress_required
        varchar score_policy
        boolean shuffle_questions
        boolean generated_by_ai
        varchar generation_model
        uuid created_by FK
        timestamptz published_at
    }

    QUESTION {
        uuid id PK
        uuid exam_id FK
        varchar type
        text statement
        varchar level
        numeric points
        integer order
        text explanation
        text correct_text
        jsonb rubric
        uuid source_chunk_id FK
        uuid source_material_id FK
        real source_start_time
        integer source_page
        boolean generated_by_ai
    }

    QUESTION_OPTION {
        uuid id PK
        uuid question_id FK
        text text
        boolean is_correct
        integer order
        text feedback
    }

    ATTEMPT {
        uuid id PK
        uuid exam_id FK
        uuid user_id FK
        integer number
        varchar status
        numeric score
        numeric max_score
        boolean passed
        timestamptz started_at
        timestamptz submitted_at
        timestamptz graded_at
        text ai_feedback
    }

    ANSWER {
        uuid id PK
        uuid attempt_id FK
        uuid question_id FK
        jsonb selected_option_ids
        text text_answer
        numeric points_awarded
        boolean is_correct
        text feedback
        text review_hint
        varchar grading_method
        boolean needs_manual_review
    }

    CHAT_SESSION {
        uuid id PK
        uuid training_id FK
        uuid user_id FK
        varchar title
        timestamptz last_message_at
        timestamptz created_at
    }

    CHAT_MESSAGE {
        uuid id PK
        uuid session_id FK
        varchar role
        text content
        boolean grounded
        integer prompt_tokens
        integer completion_tokens
        integer latency_ms
        varchar model
        timestamptz created_at
    }

    MESSAGE_CITATION {
        uuid id PK
        uuid message_id FK
        uuid chunk_id FK
        uuid material_id FK
        varchar label
        real start_time
        integer page
        real score
    }

    AI_USAGE_LOG {
        uuid id PK
        uuid company_id FK
        uuid project_id FK
        uuid user_id FK
        varchar purpose
        varchar provider
        varchar model
        integer prompt_tokens
        integer completion_tokens
        numeric cost_usd
        integer latency_ms
        boolean success
        timestamptz created_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid company_id FK
        uuid user_id FK
        varchar action
        varchar entity_type
        uuid entity_id
        inet ip_address
        text user_agent
        jsonb changes
        timestamptz created_at
    }

    USER_GROUP {
        uuid id PK
        uuid company_id FK
        varchar name
        text description
    }

    PROJECT_MEMBER {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        varchar role
    }
```

## 2. Índices

```sql
-- Multi-tenancy y navegación
CREATE INDEX idx_user_company_active      ON users (company_id, is_active);
CREATE UNIQUE INDEX uq_user_email         ON users (email);
CREATE UNIQUE INDEX uq_project_slug       ON projects (company_id, slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_training_project_status  ON trainings (project_id, status) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_training_slug      ON trainings (project_id, slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_module_training_order    ON modules (training_id, "order");
CREATE INDEX idx_lesson_module_order      ON lessons (module_id, "order");

-- Materiales y pipeline
CREATE INDEX idx_material_status          ON materials (status);
CREATE INDEX idx_material_lesson          ON materials (lesson_id);
CREATE UNIQUE INDEX uq_material_hash      ON materials (project_id, sha256);
CREATE INDEX idx_job_material             ON processing_jobs (material_id, started_at DESC);

-- RAG
CREATE INDEX idx_chunk_project            ON chunks (project_id);
CREATE INDEX idx_chunk_training           ON chunks (training_id);
CREATE INDEX idx_chunk_material_index     ON chunks (material_id, index);
CREATE UNIQUE INDEX uq_chunk_faiss        ON chunks (project_id, faiss_id);
CREATE INDEX idx_chunk_search_vector      ON chunks USING GIN (search_vector);   -- búsqueda híbrida
CREATE INDEX idx_chunk_pending_embedding  ON chunks (project_id) WHERE embedded = false;

-- Aprendizaje
CREATE UNIQUE INDEX uq_enrollment         ON enrollments (user_id, training_id);
CREATE INDEX idx_enrollment_status        ON enrollments (training_id, status);
CREATE UNIQUE INDEX uq_lesson_progress    ON lesson_progress (enrollment_id, lesson_id);

-- Evaluación
CREATE INDEX idx_exam_training_status     ON exams (training_id, status);
CREATE INDEX idx_question_exam_order      ON questions (exam_id, "order");
CREATE UNIQUE INDEX uq_attempt_number     ON attempts (exam_id, user_id, number);
CREATE INDEX idx_attempt_user             ON attempts (user_id, status);
CREATE UNIQUE INDEX uq_answer             ON answers (attempt_id, question_id);

-- Chat y analítica
CREATE INDEX idx_chat_session_user        ON chat_sessions (user_id, training_id, last_message_at DESC);
CREATE INDEX idx_chat_message_session     ON chat_messages (session_id, created_at);
CREATE INDEX idx_ai_usage_company_date    ON ai_usage_logs (company_id, created_at DESC);
CREATE INDEX idx_ai_usage_project         ON ai_usage_logs (project_id, purpose, created_at DESC);
CREATE INDEX idx_audit_company_date       ON audit_logs (company_id, created_at DESC);
CREATE INDEX idx_audit_entity             ON audit_logs (entity_type, entity_id);
```

## 3. Restricciones de integridad

```sql
ALTER TABLE enrollments      ADD CONSTRAINT ck_progress_range   CHECK (progress >= 0 AND progress <= 100);
ALTER TABLE exams            ADD CONSTRAINT ck_passing_score    CHECK (passing_score BETWEEN 0 AND 100);
ALTER TABLE exams            ADD CONSTRAINT ck_max_attempts     CHECK (max_attempts >= 1);
ALTER TABLE questions        ADD CONSTRAINT ck_points_positive  CHECK (points > 0);
ALTER TABLE transcript_segments ADD CONSTRAINT ck_time_range    CHECK (end_time >= start_time);
ALTER TABLE chapters         ADD CONSTRAINT ck_chapter_range    CHECK (end_time IS NULL OR end_time >= start_time);
ALTER TABLE attempts         ADD CONSTRAINT ck_score_range      CHECK (score IS NULL OR (score >= 0 AND score <= max_score));
```

**Políticas de borrado**

| Relación | ON DELETE | Motivo |
|----------|-----------|--------|
| `chunks.material_id` | CASCADE | El chunk no existe sin su material |
| `transcripts.material_id` | CASCADE | Idem |
| `materials.lesson_id` | CASCADE | Idem |
| `attempts.exam_id` | PROTECT | No se pierde histórico de evaluación |
| `enrollments.training_id` | CASCADE | Borrado lógico previo obliga a confirmación |
| `questions.source_chunk_id` | SET NULL | La pregunta sobrevive al reproceso del material |
| `message_citations.chunk_id` | SET NULL | El histórico del chat se conserva |
| `audit_logs.user_id` | SET NULL | La bitácora no se pierde al borrar usuarios |

## 4. Búsqueda full-text (componente híbrido del RAG)

```sql
ALTER TABLE chunks ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('spanish', coalesce(content, ''))) STORED;
```

## 5. Estrategia de migraciones

- Migraciones Django versionadas y **reversibles**; una migración por cambio lógico.
- Índices creados con `CONCURRENTLY` en producción (`AddIndexConcurrently` + `atomic = False`).
- Cambios en dos fases para columnas obligatorias: (1) agregar nullable + backfill, (2) imponer `NOT NULL`.
- Datos iniciales mediante `data migrations` idempotentes (roles, empresa demo, catálogos).
- Nunca `DROP COLUMN` en el mismo despliegue que retira su uso en el código.

## 6. Particionamiento y retención (escala)

| Tabla | Estrategia | Umbral |
|-------|-----------|--------|
| `ai_usage_logs` | Partición por rango mensual (`created_at`) | > 10 M filas |
| `audit_logs` | Partición por rango mensual + retención 24 meses | > 10 M filas |
| `chat_messages` | Partición por rango mensual | > 50 M filas |
| `chunks` | Partición por `HASH(project_id)` | > 20 M filas |
| `transcript_segments` | Sin particionar; se archiva junto al material | — |
