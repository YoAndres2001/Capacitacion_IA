# 05 · Arquitectura

## 1. Vista de contexto (C4 nivel 1)

```mermaid
graph TB
    U[Usuario / Estudiante]
    A[Administrador / Instructor]
    subgraph "Capacita IA"
        SYS[Plataforma de Capacitaciones con IA]
    end
    SMTP[(Servidor SMTP)]
    LLM[(Proveedor LLM<br/>Ollama local / OpenAI)]
    OBJ[(Almacenamiento de archivos<br/>Volumen / S3)]

    U -->|HTTPS + WSS| SYS
    A -->|HTTPS + WSS| SYS
    SYS -->|SMTP| SMTP
    SYS -->|HTTP| LLM
    SYS -->|IO| OBJ
```

## 2. Vista de contenedores (C4 nivel 2 · = servicios Docker)

```mermaid
graph TB
    subgraph Edge
        NGINX[nginx<br/>reverse proxy · TLS · estáticos · media]
    end
    subgraph Frontend
        FE[frontend<br/>React 19 + Vite + TS + MUI]
    end
    subgraph "Backend HTTP"
        API[backend<br/>Django 5 + DRF + Gunicorn<br/>SIN WebSockets]
    end
    subgraph "Tiempo real"
        WS[websocket<br/>Django Channels + Daphne<br/>contenedor independiente]
    end
    subgraph Asíncrono
        W1[celery-worker-default]
        W2[celery-worker-ingest<br/>ffmpeg + Whisper]
        W3[celery-worker-ai]
        BEAT[celery-beat]
        FLOWER[flower · monitoreo]
    end
    subgraph Datos
        PG[(PostgreSQL 17)]
        RD[(Redis 7<br/>broker · cache · channel layer)]
        FS[(Volumen media<br/>+ índices FAISS)]
    end
    subgraph IA
        OLL[ollama<br/>LLM + embeddings gratis]
    end

    NGINX --> FE
    NGINX --> API
    NGINX --> WS
    API --> PG
    API --> RD
    API --> FS
    WS --> RD
    WS --> PG
    W1 & W2 & W3 & BEAT --> PG
    W1 & W2 & W3 & BEAT --> RD
    W2 & W3 --> FS
    W3 --> OLL
    API --> OLL
    W2 & W3 -->|publica eventos| RD
    RD -->|group_send| WS
```

**Decisión clave (restricción del cliente):** el contenedor `backend` corre **solo HTTP/WSGI** con Gunicorn.
Todo WebSocket vive en el contenedor `websocket` (Channels + Daphne). La comunicación entre ambos es
indirecta: el backend y los workers publican en el *channel layer* de Redis y Daphne entrega a los clientes.

## 3. Clean Architecture (dentro del backend)

```
┌──────────────────────────────────────────────────────────────┐
│ PRESENTATION      views · serializers · urls · permissions   │
│                   consumers (en el servicio websocket)       │
│                   ↓ depende de ↓                             │
├──────────────────────────────────────────────────────────────┤
│ APPLICATION       use cases · DTOs · puertos (interfaces)    │
│                   servicios de aplicación · unit of work     │
│                   ↓ depende de ↓                             │
├──────────────────────────────────────────────────────────────┤
│ DOMAIN            entidades · value objects · reglas         │
│                   excepciones de dominio · eventos           │
│                   *** SIN Django, sin DRF, sin ORM ***       │
└──────────────────────────────────────────────────────────────┘
             ↑ implementa los puertos ↑
┌──────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE    modelos ORM · repositorios · adaptadores   │
│                   LLM · embeddings · FAISS · storage · email │
│                   Celery tasks · publisher de eventos        │
└──────────────────────────────────────────────────────────────┘
```

**Regla de dependencias:** las flechas apuntan siempre hacia adentro.
`domain` no importa nada de `application`, `infrastructure` ni `presentation`.
`application` define **puertos** (clases abstractas) que `infrastructure` implementa.
La inyección se resuelve en un **contenedor de dependencias** simple (`src/shared/container.py`)
configurado por variables de entorno.

### Ejemplo del flujo de una petición

```
HTTP POST /api/v1/trainings/{id}/chat
   │
   ▼ presentation/views.py            ← DRF: autenticación, permisos, validación
   │   ChatSerializer(data).is_valid()
   ▼ application/use_cases/answer_question.py
   │   AnswerQuestionUseCase(retriever_port, llm_port, chat_repo).execute(dto)
   ▼ domain/services/citation_policy.py      ← regla pura: validar citas
   ▼ infrastructure/ai/faiss_retriever.py    ← implementa RetrieverPort
   ▼ infrastructure/ai/ollama_provider.py    ← implementa LLMPort
   ▼ infrastructure/persistence/repositories/chat_repository.py
```

## 4. Diagrama de componentes del backend

```mermaid
graph TD
    subgraph presentation
        V1[accounts.views] --> UC1
        V2[projects.views] --> UC2
        V3[trainings.views] --> UC3
        V4[ai.views] --> UC4
        V5[assessments.views] --> UC5
    end
    subgraph application
        UC1[Casos de uso Accounts]
        UC2[Casos de uso Projects]
        UC3[Casos de uso Trainings]
        UC4[Casos de uso AI]
        UC5[Casos de uso Assessments]
        P1[[LLMPort]]
        P2[[EmbeddingsPort]]
        P3[[VectorStorePort]]
        P4[[TranscriberPort]]
        P5[[DocumentExtractorPort]]
        P6[[StoragePort]]
        P7[[EventPublisherPort]]
        P8[[Repositorios]]
    end
    subgraph domain
        D1[Entidades y VOs]
        D2[Servicios de dominio]
        D3[Excepciones]
    end
    subgraph infrastructure
        I1[OllamaProvider / OpenAIProvider] -.implementa.-> P1
        I2[OllamaEmbeddings / OpenAIEmbeddings / HFLocal] -.-> P2
        I3[FaissVectorStore] -.-> P3
        I4[FasterWhisperTranscriber] -.-> P4
        I5[PyMuPDF / Docx / Pptx / Txt] -.-> P5
        I6[LocalStorage / S3Storage] -.-> P6
        I7[RedisChannelPublisher] -.-> P7
        I8[Repositorios Django ORM] -.-> P8
    end
    UC1 & UC2 & UC3 & UC4 & UC5 --> D1 & D2
    UC4 --> P1 & P2 & P3
```

## 5. Estrategia multi-tenant

- **Modelo:** *shared database, shared schema* con columna `company_id` (discriminador).
- **Aislamiento:** un middleware resuelve el tenant desde el JWT y lo deja en un `ContextVar`.
  Todos los managers de modelos con tenant heredan de `TenantManager`, que filtra automáticamente.
- **Aislamiento vectorial:** un índice FAISS por proyecto en `indices/{company_slug}/{project_id}/`.
  Físicamente separado → imposible el cruce entre empresas.
- **Archivos:** `media/{company_slug}/{project_id}/{material_id}/...`

## 6. Decisiones de arquitectura (ADR resumidos)

| ADR | Decisión | Alternativas | Razón |
|-----|----------|--------------|-------|
| ADR-01 | Clean Architecture con módulos por dominio | Django "app-por-tabla" | Reglas de negocio testeables sin BD; permite extraer módulos a microservicios |
| ADR-02 | FAISS con índice por proyecto | pgvector, Qdrant, Chroma | Requerido por el cliente; sin servicio extra; aislamiento natural. Se abstrae tras `VectorStorePort` para migrar |
| ADR-03 | WebSocket en contenedor aparte (Daphne) | ASGI unificado | Restricción explícita del cliente; escala y falla de forma independiente |
| ADR-04 | Ollama como proveedor por defecto | OpenAI | **Costo cero**, datos que no salen de la empresa; el puerto permite cambiar a OpenAI con una variable |
| ADR-05 | `faster-whisper` en vez de `openai-whisper` | Whisper original, API de OpenAI | 4× más rápido en CPU, menor RAM, gratuito y local |
| ADR-06 | Colas Celery separadas (`ingest`, `ai`, `default`) | Cola única | La transcripción es CPU-intensiva; no debe bloquear tareas cortas |
| ADR-07 | Chunks como fuente de verdad en PostgreSQL | Solo en FAISS | Permite regenerar embeddings y cambiar de modelo/proveedor sin perder datos |
| ADR-08 | RAG híbrido (vectorial + full-text) con RRF | Solo vectorial | Mejora *recall* en nombres propios, códigos y siglas del ERP |
| ADR-09 | JWT stateless + blacklist de refresh en Redis | Sesiones | Escalado horizontal sin estado compartido |
| ADR-10 | Salidas del LLM validadas con Pydantic | Parseo de texto libre | Robustez ante modelos pequeños locales |

## 6.1 Diagrama de clases (núcleo del dominio)

```mermaid
classDiagram
    class Company { +UUID id; +str name; +str slug; +bool is_active }
    class User { +UUID id; +Email email; +Role role; +UUID company_id; +bool is_active; +can_manage(project) }
    class Project { +UUID id; +str name; +str slug; +UUID company_id; +ProjectStatus status }
    class Training { +UUID id; +str title; +Level level; +TrainingStatus status; +publish(); +can_be_published() }
    class Module { +UUID id; +str title; +int order }
    class Lesson { +UUID id; +str title; +LessonType type; +int order; +int duration_seconds }
    class Material { +UUID id; +str filename; +MaterialType type; +MaterialStatus status; +mark_processing(); +mark_available(); +mark_error(code) }
    class Transcript { +str language; +List~Segment~ segments; +text_at(second) }
    class Chapter { +str title; +float start; +float end; +str summary }
    class Concept { +str name; +str definition; +float relevance }
    class Chunk { +str content; +int index; +float start_time; +int page; +bool embedded }
    class Enrollment { +UUID user_id; +UUID training_id; +EnrollmentStatus status; +float progress; +recalculate() }
    class Exam { +str title; +int passing_score; +int max_attempts; +ExamStatus status; +publish() }
    class Question { +QuestionType type; +str statement; +Level level; +float points; +str explanation }
    class Attempt { +float score; +bool passed; +AttemptStatus status; +submit(); +grade() }
    class ChatSession { +UUID training_id; +UUID user_id }
    class ChatMessage { +MessageRole role; +str content; +List~Citation~ citations }

    Company "1" --> "N" User
    Company "1" --> "N" Project
    Project "1" --> "N" Training
    Training "1" --> "N" Module
    Module "1" --> "N" Lesson
    Lesson "1" --> "N" Material
    Material "1" --> "0..1" Transcript
    Material "1" --> "N" Chapter
    Material "1" --> "N" Concept
    Material "1" --> "N" Chunk
    Training "1" --> "N" Enrollment
    Training "1" --> "N" Exam
    Exam "1" --> "N" Question
    Exam "1" --> "N" Attempt
    Training "1" --> "N" ChatSession
    ChatSession "1" --> "N" ChatMessage
```

## 7. Diagrama de secuencia · Chat RAG

```mermaid
sequenceDiagram
    participant U as Navegador
    participant N as nginx
    participant WS as websocket (Daphne)
    participant API as backend (Django)
    participant R as Redis
    participant F as FAISS
    participant L as Ollama

    U->>N: WSS /ws/chat/{session_id}/?token=JWT
    N->>WS: upgrade
    WS->>WS: valida JWT y pertenencia
    U->>WS: {"type":"question","content":"¿Qué es el inventario cíclico?"}
    WS->>API: HTTP interno POST /internal/chat/answer (o ejecuta caso de uso compartido)
    API->>L: reescritura de consulta
    API->>F: similarity_search(query_vec, filter=training_id, k=8)
    F-->>API: chunks + scores
    API->>API: umbral + reranking + validación de contexto
    alt sin contexto suficiente
        API-->>WS: {"type":"answer","content":"No encuentro esa información..."}
    else con contexto
        API->>L: generate(prompt con citas, stream=true)
        loop por token
            L-->>API: token
            API->>R: group_send(chat.{session}, token)
            R->>WS: token
            WS-->>U: {"type":"token","content":"..."}
        end
        API->>API: valida citas contra chunks entregados
        API-->>WS: {"type":"done","citations":[...],"usage":{...}}
    end
    WS-->>U: cierre del mensaje
```

## 8. Diagrama de secuencia · Ingesta de video

```mermaid
sequenceDiagram
    participant I as Instructor
    participant API as backend
    participant Q as Redis (broker)
    participant W as celery-worker-ingest
    participant FF as ffmpeg
    participant WH as faster-whisper
    participant L as Ollama
    participant F as FAISS
    participant WS as websocket

    I->>API: POST /materials (chunked upload)
    API->>API: valida MIME real, hash, cuota
    API->>Q: ingest_material.delay(id)
    API-->>I: 201 {status: PENDING}
    W->>Q: consume
    W->>WS: estado PROCESSING
    W->>FF: extraer audio wav 16k mono
    FF-->>W: audio.wav
    W->>WH: transcribe(audio)
    WH-->>W: segmentos con timestamps
    W->>WS: estado ANALYZING
    W->>W: chunking semántico con timestamps
    W->>L: embed(batch de chunks)
    L-->>W: vectores
    W->>F: add_vectors + persist
    W->>L: capítulos · resumen · conceptos · FAQ · preguntas candidatas
    L-->>W: JSON validado con Pydantic
    W->>API: persiste todo en PostgreSQL
    W->>WS: estado AVAILABLE
    WS-->>I: notificación en vivo
```

## 9. Diagrama de despliegue

```mermaid
graph TB
    subgraph "Host / Cluster"
        subgraph "red: edge"
            NX[nginx :80/:443]
        end
        subgraph "red: app"
            FE[frontend]
            BE1[backend x N]
            WS1[websocket x N]
        end
        subgraph "red: workers"
            CW1[celery ingest x N]
            CW2[celery ai x N]
            CW3[celery default]
            CB[celery beat x1]
        end
        subgraph "red: data (sin salida a internet)"
            PGX[(postgres:17)]
            RDX[(redis:7)]
            OLX[ollama]
        end
        VOL[(volúmenes: media, faiss_indices, postgres_data, ollama_models)]
    end
    NX --> FE & BE1 & WS1
    BE1 & WS1 & CW1 & CW2 & CW3 & CB --> PGX & RDX
    BE1 & CW1 & CW2 --> VOL
    CW2 & BE1 --> OLX
```

## 10. Evolución a microservicios

El monolito modular está preparado para extraer servicios sin reescribir el dominio:

| Fase | Extracción | Disparador |
|------|-----------|------------|
| 1 | `ai-service` (ingesta + RAG + agente) | La ingesta compite por recursos con la API |
| 2 | `assessment-service` | Reglas de evaluación con ciclo de vida propio |
| 3 | `identity-service` (Keycloak u OIDC propio) | Necesidad de SSO corporativo |

Cada módulo ya tiene su propio `domain`, `application`, `infrastructure` y `presentation`, y se comunica
con los demás mediante casos de uso y eventos — nunca importando modelos ORM ajenos.
