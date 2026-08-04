# 10 · Diseño de la API REST

- **Base:** `/api/v1`
- **Formato:** JSON (UTF-8). Fechas en ISO-8601 UTC.
- **Auth:** `Authorization: Bearer <access_token>` (JWT).
- **Documentación viva:** `/api/docs/` (Swagger UI), `/api/redoc/`, `/api/schema/` (OpenAPI 3.1) generada con `drf-spectacular`.

## 1. Convenciones

| Aspecto | Convención |
|---------|-----------|
| Nombres | Recursos en plural, kebab-case en rutas: `/training-materials` |
| Paginación | `?page=1&page_size=20` → `{count, next, previous, results}` |
| Orden | `?ordering=-created_at` |
| Filtros | `?status=AVAILABLE&project=<uuid>&search=texto` |
| Campos parciales | `?fields=id,title,status` |
| Idempotencia | `Idempotency-Key` en POST de carga y de generación IA |
| Versionado | Prefijo de ruta `/v1`; cambios incompatibles → `/v2` |

### Formato de error (uniforme)

```json
{
  "error": {
    "code": "MATERIAL_NOT_READY",
    "message": "El material aún está siendo procesado.",
    "details": { "status": "ANALYZING", "progress": 62 },
    "request_id": "01J9Z7K3P2Q"
  }
}
```

| HTTP | Uso |
|------|-----|
| 400 | `VALIDATION_ERROR`, `INVALID_FILE_TYPE` |
| 401 | `AUTHENTICATION_FAILED`, `TOKEN_EXPIRED` |
| 403 | `PERMISSION_DENIED`, `NOT_ENROLLED`, `USER_DISABLED` |
| 404 | `NOT_FOUND` (también cuando el recurso es de otra empresa) |
| 409 | `PROJECT_SLUG_TAKEN`, `DUPLICATE_MATERIAL`, `MATERIAL_NOT_READY`, `EXAM_LOCKED`, `MAX_ATTEMPTS_REACHED` |
| 422 | `BUSINESS_RULE_VIOLATION` |
| 429 | `RATE_LIMIT_EXCEEDED` (+ header `Retry-After`) |
| 503 | `AI_PROVIDER_UNAVAILABLE` |

## 2. Autenticación

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/login` | Emite `access` + `refresh` |
| POST | `/auth/refresh` | Rota el refresh y emite nuevo access |
| POST | `/auth/logout` | Invalida el refresh (blacklist) |
| GET | `/auth/me` | Perfil y permisos del usuario autenticado |
| PATCH | `/auth/me` | Actualiza perfil |
| POST | `/auth/change-password` | Cambio de contraseña autenticado |
| POST | `/auth/password-reset` | Solicita enlace de recuperación (responde 202 siempre) |
| POST | `/auth/password-reset/confirm` | Confirma con token + nueva contraseña |

```http
POST /api/v1/auth/login
{"email": "admin@demo.cl", "password": "Demo1234!"}

200 OK
{
  "access": "eyJhbGciOi...",
  "refresh": "eyJhbGciOi...",
  "user": {
    "id": "7c1e...", "email": "admin@demo.cl", "first_name": "Ana",
    "role": "ADMIN", "company": {"id": "9a2f...", "name": "Sistemas Expertos"}
  }
}
```

## 3. Usuarios y empresa

| Método | Ruta | Rol |
|--------|------|-----|
| GET/POST | `/users` | ADMIN |
| GET/PATCH/DELETE | `/users/{id}` | ADMIN |
| POST | `/users/{id}/activate` · `/deactivate` | ADMIN |
| POST | `/users/bulk-invite` | ADMIN — carga CSV |
| GET/POST | `/user-groups` · `/user-groups/{id}/members` | ADMIN |
| GET/PATCH | `/company` | ADMIN — datos de la empresa actual |
| GET/POST | `/companies` | SUPERADMIN |

## 4. Proyectos

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/projects` | Listar/crear |
| GET/PATCH/DELETE | `/projects/{id}` | Detalle/editar/archivar |
| GET/POST/DELETE | `/projects/{id}/members` | Responsables del proyecto |
| GET | `/projects/{id}/stats` | Capacitaciones, materiales, usuarios, vectores |
| POST | `/projects/{id}/rebuild-index` | Reconstruye la colección FAISS (asíncrono) |
| GET | `/projects/{id}/vector-collection` | Estado del índice |

## 5. Capacitaciones y contenido

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/trainings` | `?project=<uuid>&status=PUBLISHED` |
| GET/PATCH/DELETE | `/trainings/{id}` | |
| GET | `/trainings/{id}/detail` | Árbol completo: módulos → lecciones → materiales |
| POST | `/trainings/{id}/publish` · `/unpublish` | Valida RN-05 |
| POST | `/trainings/{id}/duplicate` | Clona la estructura |
| GET | `/trainings/{id}/search?q=` | Búsqueda dentro del curso (transcripciones y documentos) |
| GET/POST | `/trainings/{id}/modules` | |
| PATCH/DELETE | `/modules/{id}` | |
| POST | `/trainings/{id}/modules/reorder` | `{"order": ["uuid1","uuid2"]}` |
| GET/POST | `/modules/{id}/lessons` | |
| PATCH/DELETE | `/lessons/{id}` | |
| POST | `/modules/{id}/lessons/reorder` | |

## 6. Materiales (carga y procesamiento)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/lessons/{id}/materials/upload-session` | Inicia carga por trozos → `{upload_id, chunk_size}` |
| PUT | `/materials/uploads/{upload_id}/chunk?index=N` | Envía un trozo (binario) |
| POST | `/materials/uploads/{upload_id}/complete` | Ensambla, valida y crea el material |
| POST | `/lessons/{id}/materials` | Carga directa (multipart) para archivos pequeños |
| GET | `/materials/{id}` | Metadatos y estado |
| DELETE | `/materials/{id}` | Borrado lógico + limpieza de chunks |
| POST | `/materials/{id}/reprocess` | Reencola la ingesta |
| GET | `/materials/{id}/status` | `{status, step, progress, error_code}` |
| GET | `/materials/{id}/stream` | URL firmada / `X-Accel-Redirect` del video |
| GET | `/materials/{id}/transcript` | Transcripción con segmentos |
| GET | `/materials/{id}/chapters` | Capítulos detectados |
| PATCH | `/chapters/{id}` | Corrección manual del título/resumen |
| GET | `/materials/{id}/concepts` · `/faqs` · `/summary` | Salidas del análisis IA |
| GET | `/materials/{id}/chunks` | Diagnóstico (ADMIN) |

```http
POST /api/v1/lessons/8f3.../materials/upload-session
{"filename":"sesion-inventario.mp4","size_bytes":1288490188,"mime_type":"video/mp4"}

201 Created
{"upload_id":"up_01J9...","chunk_size":5242880,"expires_at":"2026-08-04T12:00:00Z"}
```

## 7. Aprendizaje

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/me/trainings` | Cursos asignados con avance |
| GET | `/me/trainings/{id}` | Detalle + progreso por lección |
| POST | `/trainings/{id}/enrollments` | Asignar usuarios/grupos (ADMIN) |
| DELETE | `/enrollments/{id}` | Desasignar |
| GET | `/trainings/{id}/enrollments` | Progreso de todos (ADMIN) |
| PATCH | `/lessons/{id}/progress` | `{position_seconds, watched_seconds}` |
| POST | `/lessons/{id}/complete` | Marca completada |
| GET/POST | `/lessons/{id}/notes` · PATCH/DELETE `/notes/{id}` | Notas personales |

## 8. IA · Chat y agente

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/trainings/{id}/chat-sessions` | Listar/crear conversación |
| GET | `/chat-sessions/{id}/messages` | Historial paginado |
| POST | `/chat-sessions/{id}/messages` | Pregunta (respuesta síncrona; el streaming va por WS) |
| DELETE | `/chat-sessions/{id}` | Elimina la conversación |
| POST | `/trainings/{id}/agent/run` | Ejecuta el agente con una instrucción y herramientas |
| GET | `/ai/usage` | Consumo `?project=&from=&to=&group_by=day` |
| GET | `/ai/health` | Estado del proveedor y modelos cargados |

```http
POST /api/v1/chat-sessions/3b7.../messages
{"content":"¿Qué explicó el instructor sobre inventario cíclico?"}

200 OK
{
  "id": "b21c...",
  "role": "ASSISTANT",
  "grounded": true,
  "content": "El instructor explica que el inventario cíclico consiste en ...",
  "citations": [
    {"material_id":"aa1...","label":"Sesión Inventario · 14:32","start_time":872.4,"score":0.81},
    {"material_id":"bb2...","label":"Manual WMS · pág. 23","page":23,"score":0.74}
  ],
  "usage": {"prompt_tokens": 1840, "completion_tokens": 260, "model": "qwen2.5:7b-instruct"}
}
```

Respuesta sin contexto suficiente (RN-04):
```json
{ "role": "ASSISTANT", "grounded": false,
  "content": "No encuentro esa información en el material de esta capacitación. Te sugiero consultar al instructor.",
  "citations": [] }
```

## 9. Evaluación

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/trainings/{id}/exams` | Listar/crear manual |
| POST | `/trainings/{id}/exams/generate` | **Generación con IA** (asíncrona) |
| GET/PATCH/DELETE | `/exams/{id}` | |
| POST | `/exams/{id}/publish` · `/archive` | |
| GET/POST | `/exams/{id}/questions` · PATCH/DELETE `/questions/{id}` | Edición humana de lo generado |
| POST | `/exams/{id}/attempts` | Inicia un intento (valida RN-07 y RN-09) |
| GET | `/attempts/{id}` | Estado y respuestas guardadas |
| PATCH | `/attempts/{id}/answers` | Guardado parcial |
| POST | `/attempts/{id}/submit` | Entrega → corrección automática |
| GET | `/attempts/{id}/result` | Puntaje, feedback y secciones a repasar |
| GET | `/me/attempts` | Historial del usuario |
| GET | `/exams/{id}/results` | Resultados agregados (ADMIN) |

```http
POST /api/v1/trainings/5d2.../exams/generate
{
  "title": "Evaluación Inventario Básico",
  "num_questions": 10,
  "level": "INTERMEDIATE",
  "distribution": {"SINGLE_CHOICE": 5, "TRUE_FALSE": 2, "SHORT_ANSWER": 2, "OPEN_ENDED": 1},
  "passing_score": 70,
  "language": "es"
}

202 Accepted
{"task_id":"c8f...","exam_id":"e91...","status":"GENERATING"}
```

## 10. Analítica

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/analytics/overview` | KPIs del dashboard admin |
| GET | `/analytics/progress` | `?project=&training=&user=` |
| GET | `/analytics/exam-results` | Distribución de notas, preguntas más falladas |
| GET | `/analytics/ai-usage` | Tokens, costo, tasa de "sin contexto" |
| GET | `/analytics/export` | `?report=progress&format=csv` |

## 11. WebSocket (contenedor independiente)

Base: `wss://host/ws/` · autenticación por `?token=<access_jwt>` validada en `connect`.

| Canal | Eventos servidor → cliente |
|-------|---------------------------|
| `/ws/materials/{material_id}/` | `status.changed`, `progress`, `completed`, `failed` |
| `/ws/chat/{session_id}/` | `token`, `answer.done`, `error` · cliente → servidor: `question`, `cancel` |
| `/ws/notifications/` | `notification`, `enrollment.assigned`, `attempt.graded` |

```json
// servidor → cliente
{"type":"status.changed","material_id":"aa1...","status":"ANALYZING","step":"embeddings","progress":62}
{"type":"token","session_id":"3b7...","content":"El inventario "}
{"type":"answer.done","session_id":"3b7...","message_id":"b21c...","citations":[...]}
```

## 12. Seguridad y límites

| Endpoint | Límite |
|----------|--------|
| `POST /auth/login` | 5 / min / IP |
| `POST /auth/password-reset` | 3 / hora / IP |
| `POST /chat-sessions/{id}/messages` | 30 / min / usuario |
| `POST /exams/generate` | 10 / hora / empresa |
| Carga de material | 20 archivos / hora / usuario |
| General autenticado | 1000 / hora / usuario |

Adicional: validación de MIME real, nombres saneados, `Content-Disposition: attachment` en descargas,
CSP estricta, CSRF activo para el admin de Django, y ORM parametrizado (sin SQL crudo interpolado).

## 13. Salud

| Ruta | Descripción |
|------|-------------|
| `GET /health/live` | 200 si el proceso responde |
| `GET /health/ready` | Verifica PostgreSQL, Redis, almacenamiento e índice FAISS |
| `GET /metrics` | Métricas Prometheus |
