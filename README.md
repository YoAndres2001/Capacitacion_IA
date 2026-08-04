# Capacita IA · Plataforma de Capacitaciones con Inteligencia Artificial

Clon funcional de una plataforma de capacitaciones (concepto Plazzi) construido sobre **React + Django**,
con una capa de IA que transcribe videos, indexa documentos, responde por RAG, actúa como tutor virtual
y genera y corrige exámenes automáticamente.

> **La IA es 100 % gratuita por defecto**: Ollama local (LLM + embeddings) y `faster-whisper` local
> para transcripción. No se necesita ninguna API key. OpenAI queda disponible como alternativa
> cambiando una sola variable de entorno.

---

## Stack

| Capa | Tecnologías |
|------|-------------|
| Frontend | React 19 · Vite · TypeScript · Material UI · React Router · TanStack Query · Axios · React Hook Form · Zod |
| Backend | Django 5 · Django REST Framework · Python 3.13 · PostgreSQL 17 · Celery · Redis · JWT |
| Tiempo real | Django Channels + Daphne (**contenedor independiente**) |
| IA | LangChain · LangGraph · FAISS · Ollama (gratis) / OpenAI · faster-whisper · PyMuPDF · python-docx · python-pptx |
| Infra | Docker Compose (dev y prod) · nginx · Gunicorn · Flower |
| Arquitectura | Clean Architecture · SOLID · multi-tenant |

## Requisitos

- Docker Desktop 24+ con Docker Compose v2
- 8 GB de RAM y 4 núcleos como mínimo (con el modelo por defecto)
- ~15 GB de disco para modelos, media e índices

### Elegir el modelo según tu hardware

El modelo por defecto (`qwen2.5:1.5b-instruct`) está elegido para funcionar en **CPU**,
sin GPU y compartiendo la máquina con otros procesos. Si tienes más potencia, súbelo:

| Hardware | `OLLAMA_LLM_MODEL` | Tamaño | Análisis de un documento |
|----------|--------------------|--------|--------------------------|
| CPU 4 núcleos (por defecto) | `qwen2.5:1.5b-instruct` | ~1 GB | 1–3 min |
| CPU 8+ núcleos | `llama3.2:3b-instruct` | ~2 GB | 3–8 min |
| GPU NVIDIA | `qwen2.5:7b-instruct` | ~4.7 GB | < 1 min · mejor calidad |

Un modelo grande en CPU **no falla en silencio**: el material queda `AVAILABLE` con
`partial_analysis` (el chat RAG funciona porque los embeddings sí se generaron) y el log
indica que se superó `OLLAMA_TIMEOUT`. En ese caso, baja de modelo o reduce
`AI_ANALYSIS_MAX_CHARS`.

## Arranque rápido

```bash
cp .env.example .env
docker compose up -d
```

La primera vez, `ollama-init` descarga los modelos (varios minutos). Seguir el avance con:

```bash
docker compose logs -f ollama-init
```

Cuando termine:

| Servicio | URL |
|----------|-----|
| **Aplicación** | http://localhost:8088 |
| API (Swagger) | http://localhost:8088/api/docs/ |
| API (Redoc) | http://localhost:8088/api/redoc/ |
| Admin de Django | http://localhost:8088/admin/ |
| Flower (colas) | http://localhost:5599 |
| MailHog (correo dev) | http://localhost:8026 |

> Los puertos publicados se configuran con las variables `PORT_*` del `.env`.
> Vienen en un bloque poco común (8088, 8010, 8011, 5442, 6389, 11435…) para no
> chocar con otros proyectos que ya estén corriendo en la máquina.

### Dos contenedores aparecen detenidos: es correcto

`docker compose ps -a` muestra siempre **`migrate` y `ollama-init` como `Exited (0)`**.
No es un fallo: son tareas de arranque que se ejecutan una vez y terminan.

| Contenedor | Qué hace | Cuándo vuelve a correr |
|------------|----------|------------------------|
| `migrate` | Espera a PostgreSQL, aplica migraciones y siembra los datos demo (solo si la base está vacía) | En cada `docker compose up`; es idempotente |
| `ollama-init` | Descarga los modelos gratuitos de Ollama | En cada `up`; si ya están, termina en segundos |

Lo que importa es el **código de salida 0**. Si alguno sale con otro código, ahí sí
hay un problema y conviene revisarlo:

```bash
docker compose ps -a                  # ver estado y código de salida
docker compose logs migrate           # detalle de las migraciones
docker compose logs ollama-init       # descarga de modelos
```

Los 12 servicios restantes sí deben quedar `Up` y, los que tienen sonda, `healthy`.

**Usuarios de demostración** (creados por `seed_demo`):

| Rol | Email | Contraseña |
|-----|-------|-----------|
| Administrador | `admin@demo.cl` | `Demo1234!` |
| Instructor | `instructor@demo.cl` | `Demo1234!` |
| Estudiante | `estudiante@demo.cl` | `Demo1234!` |

## Comandos habituales

```bash
make up            # levantar en desarrollo
make down          # detener
make logs          # seguir logs
make migrate       # aplicar migraciones
make seed          # datos de demostración
make test          # tests del backend
make lint          # ruff + black + mypy + eslint
make shell         # shell de Django
make prod-up       # levantar en producción
```

Sin `make` (Windows/PowerShell):

```powershell
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
docker compose exec backend pytest src/tests/unit -q
docker compose exec ollama ollama list      # modelos gratuitos descargados
```

### Primer recorrido sugerido

1. Entra como `instructor@demo.cl` → **Capacitaciones** → abre *Inventario — Nivel Básico*.
2. En una lección, **sube un video o un PDF**. Verás el estado cambiar en vivo:
   `Pendiente → Procesando → Analizando → Disponible`.
3. Al quedar **Disponible**, abre el material para revisar lo que generó la IA:
   transcripción con timestamps, capítulos, resumen, conceptos y FAQ.
4. **Publica** la capacitación y genera una evaluación con IA (pestaña *Evaluaciones*).
5. Entra como `estudiante@demo.cl`, reproduce el curso y pregunta en el **chat**:
   la respuesta cita el minuto exacto y el enlace salta ahí.

## Estructura

```
docs/         Documentación técnica completa (14 documentos)
backend/      Django + Clean Architecture (domain · application · infrastructure · presentation)
frontend/     React + Vite + TypeScript (feature-first)
docker/       Dockerfiles multi-stage
nginx/        Reverse proxy (dev y prod)
scripts/      Utilidades
```

Detalle en [docs/09-estructura-carpetas.md](docs/09-estructura-carpetas.md).

## Documentación

| # | Documento |
|---|-----------|
| 01 | [Análisis funcional](docs/01-analisis-funcional.md) |
| 02 | [Requerimientos funcionales y no funcionales](docs/02-requerimientos.md) |
| 03 | [Historias de usuario](docs/03-historias-usuario.md) |
| 04 | [Casos de uso](docs/04-casos-uso.md) |
| 05 | [Arquitectura](docs/05-arquitectura.md) |
| 06 | [Modelo de dominio](docs/06-modelo-dominio.md) |
| 07 | [Modelo de datos · ER](docs/07-modelo-datos-er.md) |
| 08 | [Contenedores e infraestructura](docs/08-docker-infra.md) |
| 09 | [Estructura de carpetas](docs/09-estructura-carpetas.md) |
| 10 | [Diseño de la API REST](docs/10-api-rest.md) |
| 11 | [Diseño del sistema RAG con FAISS](docs/11-diseno-rag.md) |
| 12 | [Diseño del agente de IA](docs/12-agente-ia.md) |
| 13 | [Flujo de procesamiento de videos y documentos](docs/13-flujo-procesamiento.md) |
| 14 | [Roadmap del MVP](docs/14-roadmap-mvp.md) |
| ✓ | [**Verificación ejecutada**](docs/VERIFICACION.md) — qué se probó realmente y qué defectos se corrigieron |

## Cambiar de proveedor de IA

Todo el dominio depende de puertos (`LLMPort`, `EmbeddingsPort`, `TranscriberPort`,
`VectorStorePort`). Cambiar de proveedor es cambiar una variable:

```dotenv
# Gratis y local (por defecto)
AI_PROVIDER=ollama
OLLAMA_LLM_MODEL=qwen2.5:1.5b-instruct
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# De pago (opcional)
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Al cambiar el modelo de embeddings hay que reconstruir el índice del proyecto:
`POST /api/v1/projects/{id}/rebuild-index` (o el botón *Reconstruir índice* en la UI).
El sistema detecta el cambio de dimensión y fuerza la reconstrucción completa.

### Con GPU NVIDIA

```dotenv
OLLAMA_LLM_MODEL=qwen2.5:7b-instruct
AI_ANALYSIS_MAX_CHARS=14000
WHISPER_MODEL=medium
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```
y añadir el reservado de GPU a los servicios `ollama` y `celery-ingest` del compose.

## Producción

```bash
cp .env.example .env      # ajustar SECRET_KEY, DEBUG=0, dominios, SMTP real
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml up -d --scale backend=4 --scale celery-ingest=3
```

Los certificados TLS se montan en `nginx/certs/` (`fullchain.pem`, `privkey.pem`).

## Restricciones respetadas

- **No se utiliza Fable** en ninguna parte del proyecto.
- Los **WebSockets no corren dentro del contenedor principal de Django**: existe el servicio
  `websocket` con Django Channels + Daphne, independiente y escalable por separado.
- Toda la plataforma se ejecuta con Docker Compose, con perfiles de desarrollo y producción.
# Capacitacion_IA
