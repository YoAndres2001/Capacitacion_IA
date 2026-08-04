# 03 · Historias de Usuario

Formato: `Como <rol> quiero <acción> para <beneficio>` + Criterios de Aceptación (Gherkin).

---

## Épica E1 · Acceso y cuentas

### HU-001 — Iniciar sesión
**Como** usuario registrado **quiero** iniciar sesión con mi email y contraseña **para** acceder a mis capacitaciones.

```gherkin
Dado que existe un usuario activo con email "ana@empresa.cl"
Cuando envío POST /api/v1/auth/login con credenciales válidas
Entonces recibo 200 con access_token, refresh_token y el perfil del usuario
Y el access_token expira en 30 minutos

Dado que envío una contraseña incorrecta 5 veces en 1 minuto
Cuando envío un sexto intento
Entonces recibo 429 Too Many Requests
```
**Puntos:** 3

### HU-002 — Recuperar contraseña
**Como** usuario **quiero** recuperar mi contraseña por correo **para** no perder el acceso.
```gherkin
Dado que solicito POST /api/v1/auth/password-reset con mi email
Entonces recibo 202 siempre (no se revela si el email existe)
Y si el email existe, se envía un enlace con token de un solo uso válido por 1 hora
Cuando uso el token dos veces
Entonces el segundo intento devuelve 400 token inválido
```
**Puntos:** 3

### HU-003 — Gestionar usuarios
**Como** administrador **quiero** crear, editar y desactivar usuarios de mi empresa **para** controlar quién accede.
```gherkin
Dado que soy ADMIN de la empresa "SE"
Cuando creo un usuario con rol STUDENT
Entonces el usuario queda asociado a mi empresa y recibe email de invitación
Y no puedo ver ni modificar usuarios de otra empresa (404)
```
**Puntos:** 5

### HU-004 — Editar mi perfil
**Como** usuario **quiero** editar mi nombre, avatar y preferencias **para** personalizar mi cuenta. **Puntos:** 2

---

## Épica E2 · Proyectos

### HU-010 — Crear proyecto
**Como** administrador **quiero** crear proyectos (ERP, WMS, CRM) **para** organizar el conocimiento por aplicación.
```gherkin
Cuando creo el proyecto "WMS" en mi empresa
Entonces se crea con slug único dentro de la empresa
Y se aprovisiona una colección vectorial FAISS vacía identificada por project_id
```
**Puntos:** 3

### HU-011 — Asignar responsables a un proyecto
**Como** administrador **quiero** asignar instructores a un proyecto **para** delegar la creación de contenido. **Puntos:** 3

---

## Épica E3 · Contenido

### HU-020 — Crear capacitación
**Como** instructor **quiero** crear una capacitación con módulos y lecciones **para** estructurar el aprendizaje.
```gherkin
Cuando creo la capacitación "Inventario Básico" en el proyecto ERP
Entonces queda en estado DRAFT y no es visible para estudiantes
Cuando la publico teniendo al menos una lección con material AVAILABLE
Entonces pasa a PUBLISHED y es asignable
```
**Puntos:** 5

### HU-021 — Subir video
**Como** instructor **quiero** subir un video de capacitación **para** que la IA lo procese.
```gherkin
Dado que subo "sesion-inventario.mp4" de 1.2 GB
Entonces la carga se hace por trozos y puedo ver el porcentaje
Y al finalizar el material queda en estado PENDING
Y en menos de 5 segundos pasa a PROCESSING
Y recibo actualizaciones de estado por WebSocket sin recargar la página
Cuando el archivo no es un video válido según su MIME real
Entonces recibo 400 con el detalle del error
```
**Puntos:** 8

### HU-022 — Subir documento
**Como** instructor **quiero** subir PDF, DOCX, PPTX o TXT **para** ampliar el material consultable. **Puntos:** 5

### HU-023 — Ver resultado del análisis IA
**Como** instructor **quiero** revisar transcripción, capítulos, resumen y conceptos **para** validar la calidad antes de publicar.
```gherkin
Dado un material en estado AVAILABLE
Entonces puedo ver la transcripción completa con timestamps
Y los capítulos detectados con inicio y fin
Y el resumen ejecutivo y los conceptos clave
Y puedo editar el título de un capítulo
```
**Puntos:** 5

### HU-024 — Reprocesar material
**Como** instructor **quiero** reprocesar un material **para** corregir un análisis deficiente o cambiar de modelo. **Puntos:** 3

---

## Épica E4 · Aprendizaje

### HU-030 — Ver mis cursos asignados
**Como** estudiante **quiero** ver mis cursos con su % de avance **para** saber qué me falta. **Puntos:** 3

### HU-031 — Reproducir video con transcripción
**Como** estudiante **quiero** ver el video con la transcripción sincronizada **para** seguir mejor la explicación.
```gherkin
Dado que reproduzco una lección de video
Entonces la línea de transcripción activa se resalta y hace autoscroll
Cuando hago clic en una línea de la transcripción
Entonces el video salta a ese segundo
Cuando salgo y vuelvo a entrar
Entonces el video se reanuda en la última posición guardada
```
**Puntos:** 8

### HU-032 — Completar lección
**Como** estudiante **quiero** que la lección se marque completada al verla **para** que mi avance se refleje solo.
```gherkin
Cuando alcanzo el 90% de reproducción de la lección
Entonces la lección se marca COMPLETED
Y el % de avance de la capacitación se recalcula
```
**Puntos:** 3

### HU-033 — Buscar dentro del curso
**Como** estudiante **quiero** buscar una palabra en todo el curso **para** ir directo al minuto donde se menciona. **Puntos:** 5

---

## Épica E5 · IA

### HU-040 — Chatear con la capacitación
**Como** estudiante **quiero** preguntar en lenguaje natural sobre el curso **para** resolver dudas al instante.
```gherkin
Dado que estoy en la capacitación "Inventario Básico"
Cuando pregunto "¿Qué explicó el instructor sobre inventario cíclico?"
Entonces recibo una respuesta construida solo con el contenido de esa capacitación
Y la respuesta incluye citas con el nombre del material y el timestamp
Cuando hago clic en una cita
Entonces el reproductor salta a ese minuto
Cuando pregunto algo que no está en el material
Entonces la IA responde que no encuentra esa información y no inventa
```
**Puntos:** 13

### HU-041 — Chat en streaming
**Como** estudiante **quiero** ver la respuesta escribiéndose en vivo **para** una experiencia fluida. **Puntos:** 5

### HU-042 — Pedir explicación adaptada
**Como** estudiante **quiero** decir "explícamelo como si fuera principiante" o "dame un ejemplo" **para** entenderlo a mi nivel. **Puntos:** 5

### HU-043 — Comparar materiales
**Como** estudiante **quiero** pedir al agente que compare dos videos o documentos **para** entender las diferencias entre versiones. **Puntos:** 8

### HU-044 — Ver historial de conversación
**Como** estudiante **quiero** conservar mis conversaciones por capacitación **para** retomarlas después. **Puntos:** 3

---

## Épica E6 · Evaluación

### HU-050 — Generar examen con IA
**Como** instructor **quiero** generar un examen automáticamente **para** no redactarlo a mano.
```gherkin
Dado que la capacitación tiene material AVAILABLE
Cuando solicito generar un examen de 10 preguntas mixtas de nivel intermedio
Entonces se crea un examen en estado DRAFT
Y cada pregunta tiene enunciado, tipo, nivel, puntaje, respuesta correcta, explicación y referencia a la fuente
Y puedo editar o eliminar preguntas antes de publicar
```
**Puntos:** 13

### HU-051 — Rendir examen
**Como** estudiante **quiero** rendir el examen **para** certificar lo aprendido.
```gherkin
Dado que mi avance en la capacitación es 85% y el mínimo es 80%
Cuando inicio el examen
Entonces se crea un intento IN_PROGRESS con hora de inicio
Y mis respuestas se guardan parcialmente
Cuando se acaba el tiempo o presiono Enviar
Entonces el intento pasa a SUBMITTED y luego a GRADED
```
**Puntos:** 8

### HU-052 — Recibir corrección con retroalimentación
**Como** estudiante **quiero** ver qué respondí mal, por qué y dónde repasarlo **para** mejorar.
```gherkin
Dado que entregué el examen
Entonces veo mi puntaje total y si aprobé
Y por cada pregunta incorrecta veo la respuesta correcta, la explicación del error
Y un enlace directo al minuto del video o la página del documento que debo repasar
```
**Puntos:** 8

### HU-053 — Revisar resultados como admin
**Como** administrador **quiero** ver resultados agregados y las preguntas más falladas **para** mejorar la capacitación. **Puntos:** 5

---

## Épica E7 · Analítica y administración

### HU-060 — Dashboard administrador
**Como** administrador **quiero** un panel con usuarios, cursos, materiales y avance **para** controlar la operación. **Puntos:** 5

### HU-061 — Asignar capacitaciones
**Como** administrador **quiero** asignar cursos a usuarios o grupos **para** distribuir la formación. **Puntos:** 5

### HU-062 — Ver utilización de IA
**Como** administrador **quiero** ver tokens y costo estimado por proyecto **para** controlar el gasto. **Puntos:** 5

---

## Resumen de esfuerzo

| Épica | Puntos |
|-------|--------|
| E1 Acceso | 13 |
| E2 Proyectos | 6 |
| E3 Contenido | 26 |
| E4 Aprendizaje | 19 |
| E5 IA | 34 |
| E6 Evaluación | 34 |
| E7 Analítica | 15 |
| **Total** | **147** |
