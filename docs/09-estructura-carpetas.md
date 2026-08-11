# 09 · Estructura de Carpetas

## Raíz

```
Project Capacitacion IA/
├── docs/                       # Documentación técnica (este directorio)
├── backend/                    # Django 5 + DRF (Clean Architecture)
├── frontend/                   # React 19 + Vite + TypeScript
├── nginx/                      # Configuración del reverse proxy
├── docker/                     # Dockerfiles y entrypoints
├── scripts/                    # Utilidades (seed, backup, bootstrap)
├── docker-compose.yml          # Desarrollo
├── docker-compose.prod.yml     # Producción
├── .env.example
├── Makefile
└── README.md
```

## Backend — Clean Architecture

```
backend/
├── manage.py
├── pyproject.toml              # ruff, black, mypy, pytest
├── requirements/
│   ├── base.txt  dev.txt  prod.txt  ai.txt
├── config/                     # Configuración del proyecto Django
│   ├── settings/
│   │   ├── base.py  dev.py  prod.py  test.py
│   ├── urls.py                 # Enrutado HTTP (backend)
│   ├── wsgi.py                 # Servido por Gunicorn (contenedor backend)
│   ├── asgi.py                 # Servido por Daphne (contenedor websocket)
│   ├── routing.py              # Rutas WebSocket
│   └── celery.py
└── src/
    ├── shared/                             # Núcleo transversal
    │   ├── domain/
    │   │   ├── entity.py                   # Entity, AggregateRoot
    │   │   ├── value_object.py
    │   │   ├── events.py                   # DomainEvent
    │   │   └── exceptions.py               # DomainError y jerarquía
    │   ├── application/
    │   │   ├── use_case.py                 # UseCase[Input, Output]
    │   │   ├── dto.py
    │   │   ├── unit_of_work.py
    │   │   └── ports/                      # Puertos transversales
    │   │       ├── repository.py
    │   │       ├── storage.py
    │   │       ├── event_publisher.py
    │   │       └── notifier.py
    │   ├── infrastructure/
    │   │   ├── models.py                   # BaseModel (uuid, timestamps, soft delete)
    │   │   ├── managers.py                 # TenantManager
    │   │   ├── tenancy.py                  # ContextVar del tenant
    │   │   ├── storage/                    # LocalStorage, S3Storage
    │   │   ├── events/                     # RedisChannelPublisher
    │   │   └── email/
    │   ├── presentation/
    │   │   ├── exception_handler.py        # DomainError → HTTP
    │   │   ├── pagination.py
    │   │   ├── permissions.py              # IsAdmin, IsInstructor, InSameCompany...
    │   │   ├── mixins.py
    │   │   └── middleware.py               # tenant, request_id, logging
    │   └── container.py                    # Composition root (inyección)
    │
    ├── modules/
    │   ├── accounts/
    │   │   ├── domain/
    │   │   │   ├── entities.py             # User, Company (puras)
    │   │   │   ├── value_objects.py        # Email, Role
    │   │   │   └── repositories.py         # UserRepository (interfaz)
    │   │   ├── application/
    │   │   │   ├── dtos.py
    │   │   │   └── use_cases/
    │   │   │       ├── authenticate_user.py
    │   │   │       ├── create_user.py
    │   │   │       ├── request_password_reset.py
    │   │   │       └── confirm_password_reset.py
    │   │   ├── infrastructure/
    │   │   │   ├── models.py               # CompanyModel, UserModel (ORM)
    │   │   │   ├── repositories.py         # DjangoUserRepository
    │   │   │   ├── admin.py
    │   │   │   └── migrations/
    │   │   └── presentation/
    │   │       ├── serializers.py  views.py  urls.py
    │   │
    │   ├── projects/       # misma estructura de 4 capas
    │   ├── trainings/      # trainings, modules, lessons, materials, enrollments, progress
    │   ├── ai/
    │   │   ├── domain/                     # Chunk, Citation, GroundingPolicy, CitationPolicy
    │   │   ├── application/
    │   │   │   ├── ports/
    │   │   │   │   ├── llm.py              # LLMPort
    │   │   │   │   ├── embeddings.py       # EmbeddingsPort
    │   │   │   │   ├── vector_store.py     # VectorStorePort
    │   │   │   │   ├── transcriber.py      # TranscriberPort
    │   │   │   │   └── extractor.py        # DocumentExtractorPort
    │   │   │   └── use_cases/
    │   │   │       ├── ingest_material.py
    │   │   │       ├── answer_question.py
    │   │   │       ├── run_agent.py
    │   │   │       └── rebuild_index.py
    │   │   ├── infrastructure/
    │   │   │   ├── providers/              # groq_provider.py, groq_http.py,
    │   │   │   │                           # sentence_transformers_provider.py,
    │   │   │   │                           # parsing.py, factory.py
    │   │   │   ├── transcription/          # groq_whisper.py, ffmpeg.py
    │   │   │   ├── extraction/             # pdf.py, docx.py, pptx.py, txt.py, factory.py
    │   │   │   ├── vectorstore/            # faiss_store.py, index_manager.py
    │   │   │   ├── rag/                    # chunker.py, retriever.py, prompts.py
    │   │   │   ├── agent/                  # graph.py, tools.py, state.py
    │   │   │   ├── models.py  repositories.py  tasks.py
    │   │   └── presentation/
    │   │       ├── serializers.py  views.py  urls.py
    │   ├── assessments/    # exams, questions, attempts, grading (IA y determinístico)
    │   ├── analytics/      # dashboards y reportes (solo lectura)
    │   └── realtime/       # consumers de Channels (usados por el contenedor websocket)
    │       ├── consumers/  auth.py  routing.py
    └── tests/
        ├── unit/           # domain + application (sin BD)
        ├── integration/    # repositorios, adaptadores IA con dobles
        └── e2e/            # API con pytest-django
```

**Cómo leer la estructura:** por cada módulo, `domain` es Python puro, `application` orquesta y define
puertos, `infrastructure` implementa (ORM, IA, IO) y `presentation` expone HTTP. La dependencia siempre
apunta hacia `domain`.

## Frontend

```
frontend/
├── index.html
├── vite.config.ts  tsconfig.json  .eslintrc.cjs  .prettierrc
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── app/
    │   ├── router.tsx              # Rutas + guards por rol
    │   ├── providers.tsx           # QueryClient, Theme, Auth, Snackbar
    │   ├── theme.ts                # MUI: claro/oscuro, tipografía, paleta
    │   └── queryClient.ts
    ├── shared/
    │   ├── api/
    │   │   ├── client.ts           # Axios + interceptores + refresh automático
    │   │   ├── endpoints.ts
    │   │   └── types.ts            # Tipos generados/derivados de la API
    │   ├── components/             # AppLayout, DataTable, ConfirmDialog, FileDropzone,
    │   │                           # StatusChip, EmptyState, PageHeader, Loading
    │   ├── hooks/                  # useAuth, useWebSocket, useDebounce, usePagination
    │   ├── utils/                  # formatters, validators, storage, time
    │   └── constants/
    ├── features/
    │   ├── auth/                   # login, forgot/reset password, AuthContext
    │   ├── dashboard/              # Dashboard admin y dashboard usuario
    │   ├── users/                  # CRUD de usuarios, invitaciones
    │   ├── projects/               # CRUD de proyectos
    │   ├── trainings/              # CRUD, constructor de módulos/lecciones, subida de material
    │   ├── player/                 # Reproductor + transcripción + capítulos + notas
    │   ├── chat/                   # Chat IA con streaming y citas clickeables
    │   ├── exams/                  # Generación, edición, rendición y resultados
    │   └── analytics/              # Reportes y gráficos
    └── types/
```

**Convenciones del frontend**

- *Feature-first*: cada carpeta de `features/` contiene `api/`, `components/`, `hooks/`, `pages/`, `schemas/`.
- Estado de servidor exclusivamente con **TanStack Query** (nada de Redux para datos remotos).
- Formularios con **React Hook Form + Zod**; el esquema Zod es la única fuente de validación en cliente.
- Todo llamado HTTP pasa por `shared/api/client.ts` (adjunta el JWT, refresca al recibir 401, mapea errores).
- Rutas con *lazy loading* por feature.
