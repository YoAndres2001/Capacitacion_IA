# 02 · Requerimientos Funcionales y No Funcionales

## A. Requerimientos Funcionales (RF)

### M1 · Identidad y Acceso

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-001 | El sistema debe permitir registrar empresas (tenants) con slug único. | Must |
| RF-002 | El sistema debe autenticar mediante email + contraseña emitiendo `access` y `refresh` JWT. | Must |
| RF-003 | El `access token` expira en 30 min; el `refresh` en 7 días con rotación y blacklist. | Must |
| RF-004 | Debe soportar los roles: `SUPERADMIN`, `ADMIN`, `INSTRUCTOR`, `STUDENT`. | Must |
| RF-005 | Los permisos deben evaluarse por rol **y** por pertenencia al tenant y al proyecto. | Must |
| RF-006 | El usuario debe poder editar su perfil (nombre, avatar, cargo, idioma, zona horaria). | Should |
| RF-007 | Debe existir recuperación de contraseña por email con token de un solo uso y expiración de 1 h. | Must |
| RF-008 | El administrador debe poder crear, editar, activar/desactivar e invitar usuarios masivamente (CSV). | Should |
| RF-009 | Debe registrarse auditoría de login, logout, cambios de rol y accesos fallidos. | Must |

### M2 · Proyectos / Aplicaciones

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-010 | Una empresa puede tener N proyectos (ERP, WMS, CRM, Portal Clientes). | Must |
| RF-011 | Cada proyecto tiene su propia colección vectorial aislada. | Must |
| RF-012 | Un proyecto puede tener administradores/instructores asignados. | Should |
| RF-013 | Debe permitir archivar un proyecto sin eliminar su contenido. | Should |

### M3 · Contenido

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-020 | Crear capacitaciones dentro de un proyecto con título, descripción, nivel, duración estimada, portada. | Must |
| RF-021 | Estructurar la capacitación en módulos ordenables y lecciones ordenables (drag & drop). | Must |
| RF-022 | Subir videos (MP4, MOV, MKV, WEBM) hasta 4 GB mediante carga por trozos (chunked upload). | Must |
| RF-023 | Subir documentos PDF, DOCX, PPTX, TXT y MD hasta 100 MB. | Must |
| RF-024 | Mostrar el estado de procesamiento del material en tiempo real. | Must |
| RF-025 | Permitir reprocesar un material y regenerar embeddings. | Must |
| RF-026 | Permitir publicar/despublicar una capacitación. | Must |
| RF-027 | Permitir adjuntar recursos descargables a una lección. | Could |

### M4 · Aprendizaje

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-030 | Asignar capacitaciones a usuarios individualmente o por grupo. | Must |
| RF-031 | Reproductor con control de velocidad, marcadores de capítulo y transcripción sincronizada. | Must |
| RF-032 | Guardar posición del video cada 10 s y al salir; reanudar donde quedó. | Must |
| RF-033 | Marcar lección como completada automáticamente al alcanzar el 90 % de reproducción. | Must |
| RF-034 | Calcular el % de avance de la capacitación por usuario. | Must |
| RF-035 | Permitir notas personales por lección con timestamp. | Could |
| RF-036 | Permitir buscar dentro del curso (texto de transcripciones y documentos). | Should |

### M5 · Inteligencia Artificial

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-040 | Extraer audio del video y transcribirlo con Whisper generando segmentos con `start`/`end`. | Must |
| RF-041 | Extraer texto de documentos preservando página/diapositiva de origen. | Must |
| RF-042 | Dividir el contenido en capítulos/temas con títulos y rangos de tiempo. | Must |
| RF-043 | Generar resumen ejecutivo y resumen por capítulo. | Must |
| RF-044 | Extraer conceptos clave con definición y ubicación en el material. | Must |
| RF-045 | Generar preguntas frecuentes (FAQ) del material. | Should |
| RF-046 | Generar embeddings y almacenarlos en FAISS con metadatos (proyecto, capacitación, material, timestamp, página). | Must |
| RF-047 | El proveedor de LLM y de embeddings debe ser intercambiable por configuración (Ollama, OpenAI, otro) sin cambiar código de negocio. | Must |
| RF-048 | Chat por capacitación con RAG, historial y citas verificables. | Must |
| RF-049 | El chat debe transmitir la respuesta token a token por WebSocket. | Should |
| RF-050 | Agente IA con herramientas: buscar, resumir, explicar, comparar materiales, crear ejercicios, generar evaluación, explicar paso a paso, adaptar nivel. | Must |
| RF-051 | Registrar todo consumo de IA (tokens in/out, modelo, latencia, costo). | Must |
| RF-052 | Reconstruir el índice FAISS de un proyecto bajo demanda. | Must |

### M6 · Evaluación

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-060 | Generar exámenes automáticamente desde el material de una capacitación. | Must |
| RF-061 | Soportar tipos: selección múltiple (una y varias correctas), verdadero/falso, respuesta corta, pregunta abierta. | Must |
| RF-062 | Cada pregunta debe tener nivel, puntaje, respuesta correcta, explicación y referencia a la fuente. | Must |
| RF-063 | El examen generado nace en `DRAFT` y requiere aprobación humana. | Must |
| RF-064 | El usuario rinde el examen con temporizador opcional y guardado parcial. | Must |
| RF-065 | Corrección automática: determinística para cerradas, LLM con rúbrica para abiertas. | Must |
| RF-066 | La retroalimentación debe explicar el error y sugerir la sección exacta a repasar. | Must |
| RF-067 | Control de intentos, nota mínima de aprobación y política de puntaje (mejor/último/promedio). | Must |
| RF-068 | El administrador puede editar preguntas generadas por la IA. | Must |

### M7 · Analítica

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-070 | Dashboard admin: usuarios activos, cursos publicados, materiales por estado, avance global. | Must |
| RF-071 | Reporte de progreso por usuario, por capacitación y por proyecto. | Must |
| RF-072 | Reporte de resultados de exámenes con distribución de notas y preguntas más falladas. | Should |
| RF-073 | Panel de uso de IA: tokens, costo, top preguntas, tasa de "sin información". | Should |
| RF-074 | Exportación a CSV/XLSX de los reportes. | Could |

### M8 · Plataforma

| ID | Requerimiento | Prioridad |
|----|---------------|-----------|
| RF-080 | WebSocket para: estado de procesamiento, streaming del chat y notificaciones. | Must |
| RF-081 | El WebSocket debe ejecutarse en un contenedor independiente del backend HTTP. | Must |
| RF-082 | API documentada en OpenAPI 3 con Swagger UI y Redoc. | Must |
| RF-083 | Bitácora de auditoría de acciones sensibles. | Must |

---

## B. Requerimientos No Funcionales (RNF)

### Rendimiento
| ID | Requerimiento | Métrica |
|----|---------------|---------|
| RNF-01 | Latencia de endpoints CRUD | p95 < 300 ms |
| RNF-02 | Primer token del chat RAG | p95 < 2,5 s |
| RNF-03 | Búsqueda vectorial sobre 1M de vectores | < 150 ms |
| RNF-04 | Ingesta de video | ≤ 1× duración con GPU, ≤ 3× en CPU |
| RNF-05 | Carga inicial del frontend | LCP < 2,5 s, bundle inicial < 400 kB gz |

### Escalabilidad
| ID | Requerimiento |
|----|---------------|
| RNF-10 | Backend stateless: escalado horizontal por réplicas detrás de nginx. |
| RNF-11 | Workers Celery escalables por cola (`ingest`, `ai`, `default`, `beat`). |
| RNF-12 | Preparado para múltiples empresas, múltiples proyectos, miles de usuarios y millones de embeddings. |
| RNF-13 | El índice FAISS por proyecto se persiste en volumen compartido; migrable a pgvector/Qdrant cambiando un adaptador. |

### Seguridad
| ID | Requerimiento |
|----|---------------|
| RNF-20 | JWT firmado HS256 (dev) / RS256 (prod), rotación de refresh y blacklist. |
| RNF-21 | Autorización por rol + tenant + pertenencia a proyecto en cada endpoint. |
| RNF-22 | Rate limiting: 5/min login, 30/min chat IA, 1000/h general por usuario. |
| RNF-23 | Validación de archivos: extensión, MIME real (`python-magic`), tamaño y nombre saneado. |
| RNF-24 | Protección XSS (escape + CSP), CSRF (para sesión de admin), SQL Injection (ORM, sin SQL crudo con interpolación). |
| RNF-25 | Contraseñas con Argon2. Secretos por variables de entorno, nunca en el repositorio. |
| RNF-26 | HTTPS obligatorio en producción, HSTS, cookies `Secure`+`HttpOnly`+`SameSite`. |
| RNF-27 | Media privada: acceso a videos mediante URL firmada con expiración. |
| RNF-28 | Logs estructurados JSON con `request_id`, sin datos sensibles. |

### Disponibilidad y Operación
| ID | Requerimiento |
|----|---------------|
| RNF-30 | Healthchecks `/health/live` y `/health/ready` en todos los servicios. |
| RNF-31 | Reintentos con backoff exponencial en tareas Celery (máx. 3). |
| RNF-32 | Migraciones versionadas y reversibles. |
| RNF-33 | Backup diario de PostgreSQL y del volumen de índices FAISS. |

### Mantenibilidad
| ID | Requerimiento |
|----|---------------|
| RNF-40 | Clean Architecture: `domain` sin dependencias de framework. |
| RNF-41 | Principios SOLID; casos de uso con una sola responsabilidad. |
| RNF-42 | Cobertura de tests ≥ 70 % en `domain` y `application`. |
| RNF-43 | Lint y formato obligatorios: `ruff` + `black` + `mypy` (backend), `eslint` + `prettier` + `tsc` (frontend). |
| RNF-44 | Tipado estricto en TypeScript (`strict: true`). |

### Usabilidad y Accesibilidad
| ID | Requerimiento |
|----|---------------|
| RNF-50 | Interfaz responsive (móvil, tablet, desktop). |
| RNF-51 | Español como idioma por defecto, preparado para i18n. |
| RNF-52 | Contraste AA, navegación por teclado, `aria-label` en controles del reproductor. |
| RNF-53 | Modo claro y oscuro. |

### Restricciones
| ID | Restricción |
|----|-------------|
| RNF-60 | **NO utilizar Fable.** |
| RNF-61 | Los WebSockets **NO** se ejecutan en el contenedor principal de Django (contenedor `websocket` con Channels + Daphne). |
| RNF-62 | Toda la plataforma se ejecuta con Docker Compose (dev y prod). |
| RNF-63 | El proveedor de IA por defecto debe ser **gratuito** (Ollama local), con OpenAI como alternativa opcional. |
