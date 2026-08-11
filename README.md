# Nexora · Plataforma de Capacitaciones con Inteligencia Artificial

Clon funcional de una plataforma de capacitaciones (concepto Plazzi) construido sobre **React + Django**,
con una capa de IA que transcribe videos, indexa documentos, responde por RAG, actúa como tutor virtual
y genera y corrige exámenes automáticamente.

> **Groq es el único proveedor externo de Inteligencia Artificial utilizado por
> Capacita IA.** No hay ningún otro servicio de IA al que se hagan llamadas.
>
> **La única clave que necesitas es `GROQ_API_KEY`** (gratuita, https://console.groq.com/keys).
> Se lee exclusivamente de la variable de entorno; nunca se escribe en el código.

---

## Qué hace cada pieza de la capa de IA

| Componente | Dónde corre | De qué se encarga |
|------------|-------------|-------------------|
| **Groq** (`llama-3.3-70b-versatile`) | Servicio externo | LLM: chat/tutor, análisis (resumen, conceptos, capítulos, FAQ), generación de exámenes, corrección de respuestas abiertas, respuesta final del RAG |
| **Groq Whisper** (`whisper-large-v3`) | Servicio externo | Speech-to-Text de videos y audio, **con timestamps por segmento** |
| **SentenceTransformers** | Local, en el worker | Embeddings del RAG. No es un proveedor externo: el texto no sale de la infraestructura |
| **FAISS** | Local, en disco | Búsqueda vectorial. Tampoco es un servicio externo |
| **FFmpeg** | Local, en el worker | Extrae, comprime y trocea el audio antes de enviarlo a Groq |
| **PyMuPDF · python-docx · python-pptx** | Local | Extracción de texto de PDF, DOCX y PPTX |

El documento nunca se envía completo a Groq: se extrae y trocea en local, se indexa
en FAISS y solo viajan los fragmentos relevantes de cada consulta.

## Stack

| Capa | Tecnologías |
|------|-------------|
| Frontend | React 19 · Vite · TypeScript · Material UI · React Router · TanStack Query · Axios · React Hook Form · Zod |
| Backend | Django 5 · Django REST Framework · Python 3.13 · PostgreSQL 17 · Celery · Redis · JWT |
| Tiempo real | Django Channels + Daphne (**contenedor independiente**) |
| IA | Groq (LLM + Whisper) · LangGraph (agente tutor) · SentenceTransformers (embeddings locales) · FAISS · FFmpeg · PyMuPDF · python-docx · python-pptx |
| Infra | Docker Compose (dev y prod) · nginx · Gunicorn · Flower |
| Arquitectura | Clean Architecture · SOLID · multi-tenant |

## Requisitos

- Docker Desktop 24+ con Docker Compose v2
- 6 GB de RAM (ningún LLM corre en tu máquina; sí el modelo de embeddings, que es
  pequeño) y ~12 GB de disco para media, índices y el modelo de embeddings
- Una `GROQ_API_KEY` gratuita: https://console.groq.com/keys

### Elegir el modelo de Groq

| `GROQ_LLM_MODEL` | Cuándo usarlo |
|------------------|---------------|
| `llama-3.3-70b-versatile` (por defecto) | Mejor equilibrio calidad/velocidad; JSON estructurado fiable |
| `llama-3.1-8b-instant` | Máxima velocidad y menor costo; falla más al generar exámenes |
| `openai/gpt-oss-120b` | Mejor razonamiento; más lento y con cuota gratuita más ajustada |

> **Salida estructurada.** El adaptador pide *Structured Outputs* (`json_schema` estricto)
> y, si el modelo no los admite, degrada a modo JSON + validación Pydantic con reintento
> correctivo. Medido contra la API en agosto de 2026, **ningún modelo de chat del nivel
> gratuito admite `json_schema`**, así que el camino real es el segundo: el 400 se recibe
> una sola vez por proceso y queda recordado. Si un modelo gana soporte, se activa solo.

### El límite que de verdad manda: 12.000 tokens por minuto

El nivel gratuito de Groq da ~1.000 peticiones al día pero solo **12.000 tokens por
minuto**, y descuenta el prompt *más el máximo de salida reservado* aunque no se use.
Por eso `LLM_MAX_TOKENS`, `AI_ANALYSIS_MAX_CHARS` y `AI_EXAM_BATCH_SIZE` vienen ajustados
para que cada llamada cueste ~4.000 tokens: subirlos "por si acaso" provoca 429.

Cuando se toca el límite, el proveedor lee de la respuesta cuánto hay que esperar
(`retry-after` o `x-ratelimit-reset-tokens`) y reintenta cuando la cuota se repone, hasta
70 s. Si aun así no pasa, el material queda `AVAILABLE` con `partial_analysis`: el chat
RAG sigue funcionando porque los embeddings son locales y no dependen de Groq.

Ver la cuota restante en cualquier momento:

```bash
docker compose exec backend python manage.py ai_bench
```

## Arranque rápido

```bash
cp .env.example .env
# edita .env: pon tu GROQ_API_KEY
docker compose up -d
```

La primera vez que un worker calcula embeddings descarga el modelo local
(~470 MB) en un volumen compartido; las siguientes veces arranca al instante.
Seguir el avance:

```bash
docker compose logs -f celery-ingest
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
> Vienen en un bloque poco común (8088, 8010, 8011, 5442, 6389…) para no
> chocar con otros proyectos que ya estén corriendo en la máquina.

### Un contenedor aparece detenido: es correcto

`docker compose ps -a` muestra siempre **`migrate` como `Exited (0)`**. No es un
fallo: es una tarea de arranque que se ejecuta una vez y termina.

| Contenedor | Qué hace | Cuándo vuelve a correr |
|------------|----------|------------------------|
| `migrate` | Espera a PostgreSQL, aplica migraciones y siembra los datos demo (solo si la base está vacía) | En cada `docker compose up`; es idempotente |

Lo que importa es el **código de salida 0**. Si sale con otro código, ahí sí hay
un problema y conviene revisarlo:

```bash
docker compose ps -a                  # ver estado y código de salida
docker compose logs migrate           # detalle de las migraciones
```

El resto de los servicios debe quedar `Up` y, los que tienen sonda, `healthy`.

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
make ai-check      # diagnóstico de Groq y de los embeddings locales
make rebuild-indices  # reconstruir FAISS tras cambiar EMBEDDING_MODEL
make prod-up       # levantar en producción
```

Sin `make` (Windows/PowerShell):

```powershell
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
docker compose exec backend pytest src/tests -q
docker compose exec backend python manage.py ai_bench          # estado de Groq
docker compose exec celery-ai python manage.py rebuild_indices # reconstruir FAISS
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

## Configuración de la IA

Todo el dominio depende de puertos (`LLMPort`, `EmbeddingsPort`, `TranscriberPort`,
`VectorStorePort`), pero **no hay selección de proveedor**: Groq es el único servicio
externo. Cambiar de modelo es cambiar una variable, sin tocar código:

```dotenv
# Groq · único proveedor externo. La clave SOLO por variable de entorno.
GROQ_API_KEY=gsk_...
GROQ_LLM_MODEL=llama-3.3-70b-versatile
GROQ_WHISPER_MODEL=whisper-large-v3

# Embeddings locales (SentenceTransformers), sin llamadas externas
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu

# RAG
RAG_TOP_K=8
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=120
```

Cambiar el **LLM** o el modelo de **Whisper** no afecta a los índices. Cambiar el
**modelo de embeddings** sí, porque cambia la dimensión del vector y FAISS no puede
mezclar dimensiones distintas. El sistema lo detecta, lo registra en el log y responde
"sin contexto" en vez de fallar; para arreglarlo:

```bash
make rebuild-indices
# equivale a: docker compose exec celery-ai python manage.py rebuild_indices
```

El comando solo reconstruye los índices cuya dimensión ya no coincide. Con `--all`
reconstruye todos y con `--async` los delega en Celery. También existe el endpoint
`POST /api/v1/projects/{id}/rebuild-index` y el botón *Reconstruir índice* en la UI.

### Seguridad de la credencial

`GROQ_API_KEY` se lee **exclusivamente** de la variable de entorno, a través de
`settings.AI_SETTINGS["GROQ"]["API_KEY"]`. No aparece en el código, ni en el
Dockerfile, ni en los `docker-compose*.yml` (que la reciben del `.env`, no
versionado), ni en los tests, ni en los logs de error. El `.env.example` la lleva
vacía. Si falta, Django avisa al arrancar (`ai.W001`) y la primera llamada real
falla con un mensaje que dice exactamente qué configurar.

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
