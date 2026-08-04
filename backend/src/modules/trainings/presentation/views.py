"""Vistas del módulo Trainings: contenido, materiales, inscripciones y progreso."""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.modules.accounts.infrastructure.models import AuditLog, User, UserGroup
from src.shared.container import get_event_publisher, get_storage
from src.shared.domain.exceptions import (
    MaterialNotQueryable,
    NotEnrolled,
    NotFoundError,
)
from src.shared.presentation.permissions import IsInstructor, IsInstructorOrReadOnly

from ..application.use_cases.upload_material import (
    UploadMaterialInput,
    UploadMaterialUseCase,
)
from ..domain.material_state import MaterialStateMachine
from ..domain.progress import ProgressCalculator
from ..infrastructure.models import (
    Enrollment,
    Lesson,
    LessonProgress,
    Material,
    Module,
    Note,
    ProcessingJob,
    Training,
    UploadSession,
)
from ..infrastructure.validators import sanitize_filename, validate_declared
from .serializers import (
    AssignEnrollmentSerializer,
    CourseSearchResultSerializer,
    EnrollmentSerializer,
    LessonProgressSerializer,
    LessonSerializer,
    MaterialSerializer,
    ModuleSerializer,
    MyTrainingSerializer,
    NoteSerializer,
    ProcessingJobSerializer,
    ProgressUpdateSerializer,
    ReorderSerializer,
    TrainingDetailSerializer,
    TrainingSerializer,
    UploadSessionCreateSerializer,
    UploadSessionSerializer,
)


def _company_trainings(user):
    return Training.objects.filter(project__company_id=user.company_id)


# ═════════════════════════════════════════════════════════════
#  Capacitaciones
# ═════════════════════════════════════════════════════════════
@extend_schema_view(
    list=extend_schema(tags=["Capacitaciones"], summary="Listar capacitaciones"),
    retrieve=extend_schema(tags=["Capacitaciones"], summary="Detalle"),
    create=extend_schema(tags=["Capacitaciones"], summary="Crear capacitación"),
)
class TrainingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsInstructorOrReadOnly]
    filterset_fields = ["project", "status", "level"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "title", "published_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = (
            _company_trainings(self.request.user)
            .select_related("project", "created_by")
            .annotate(
                module_count=Count("modules", distinct=True),
                lesson_count=Count("modules__lessons", distinct=True),
                enrollment_count=Count("enrollments", distinct=True),
            )
        )
        # Los estudiantes solo ven capacitaciones publicadas.
        if not self.request.user.can_manage_content:
            qs = qs.filter(status=Training.Status.PUBLISHED)
        return qs

    def get_serializer_class(self):
        if self.action in {"retrieve", "tree"}:
            return TrainingDetailSerializer
        return TrainingSerializer

    def perform_create(self, serializer):
        training = serializer.save(created_by=self.request.user)
        AuditLog.objects.create(
            company_id=self.request.user.company_id,
            user=self.request.user,
            action=AuditLog.Action.CONTENT_CREATED,
            entity_type="Training",
            entity_id=training.id,
            changes={"title": training.title},
        )

    @extend_schema(tags=["Capacitaciones"], summary="Árbol completo de contenido")
    @action(detail=True, methods=["get"], url_path="detail")
    def tree(self, request, pk=None):
        training = self.get_object()
        full = (
            Training.objects.filter(pk=training.pk)
            .prefetch_related("modules__lessons__materials")
            .first()
        )
        return Response(TrainingDetailSerializer(full).data)

    @extend_schema(tags=["Capacitaciones"], request=None, summary="Publicar (valida RN-05)")
    @action(detail=True, methods=["post"], permission_classes=[IsInstructor])
    def publish(self, request, pk=None):
        training = self.get_object()
        training.publish()  # lanza TrainingNotPublishable si no cumple la regla
        return Response(TrainingSerializer(training).data)

    @extend_schema(tags=["Capacitaciones"], request=None, summary="Despublicar")
    @action(detail=True, methods=["post"], permission_classes=[IsInstructor])
    def unpublish(self, request, pk=None):
        training = self.get_object()
        training.unpublish()
        return Response(TrainingSerializer(training).data)

    @extend_schema(tags=["Capacitaciones"], request=None, summary="Duplicar la estructura")
    @action(detail=True, methods=["post"], permission_classes=[IsInstructor])
    @transaction.atomic
    def duplicate(self, request, pk=None):
        source = self.get_object()
        copy = Training.objects.create(
            project=source.project,
            title=f"{source.title} (copia)",
            slug=f"{source.slug}-copia-{uuid.uuid4().hex[:6]}",
            description=source.description,
            level=source.level,
            estimated_minutes=source.estimated_minutes,
            chat_enabled=source.chat_enabled,
            cross_material_search=source.cross_material_search,
            created_by=request.user,
        )
        for module in source.modules.all():
            new_module = Module.objects.create(
                training=copy, title=module.title, description=module.description, order=module.order
            )
            for lesson in module.lessons.all():
                Lesson.objects.create(
                    module=new_module,
                    title=lesson.title,
                    description=lesson.description,
                    type=lesson.type,
                    order=lesson.order,
                    duration_seconds=lesson.duration_seconds,
                    is_mandatory=lesson.is_mandatory,
                    content=lesson.content,
                )
        # Los materiales NO se copian: se vuelven a subir o se enlazan manualmente.
        return Response(TrainingSerializer(copy).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Capacitaciones"],
        parameters=[OpenApiParameter("q", str, description="Texto a buscar")],
        responses=CourseSearchResultSerializer(many=True),
        summary="Buscar dentro del curso (RF-036)",
    )
    @action(detail=True, methods=["get"])
    def search(self, request, pk=None):
        from src.modules.ai.infrastructure.search import search_course

        training = self.get_object()
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response([])
        return Response(CourseSearchResultSerializer(search_course(training, query), many=True).data)

    # ── Módulos anidados ─────────────────────────────────────
    @extend_schema(tags=["Capacitaciones"], summary="Listar/crear módulos")
    @action(detail=True, methods=["get", "post"])
    def modules(self, request, pk=None):
        training = self.get_object()

        if request.method == "GET":
            modules = training.modules.prefetch_related("lessons__materials")
            return Response(ModuleSerializer(modules, many=True).data)

        serializer = ModuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data.get("order") or training.modules.count()
        module = serializer.save(training=training, order=order)
        return Response(ModuleSerializer(module).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Capacitaciones"], request=ReorderSerializer, summary="Reordenar módulos")
    @action(detail=True, methods=["post"], url_path="modules/reorder")
    def reorder_modules(self, request, pk=None):
        training = self.get_object()
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            for index, module_id in enumerate(serializer.validated_data["order"]):
                Module.objects.filter(id=module_id, training=training).update(order=index)
        return Response(ModuleSerializer(training.modules.all(), many=True).data)

    # ── Inscripciones ────────────────────────────────────────
    @extend_schema(
        tags=["Aprendizaje"], request=AssignEnrollmentSerializer, summary="Asignar / listar inscritos"
    )
    @action(detail=True, methods=["get", "post"])
    def enrollments(self, request, pk=None):
        training = self.get_object()

        if request.method == "GET":
            if not request.user.can_manage_content:
                return Response(status=status.HTTP_403_FORBIDDEN)
            records = training.enrollments.select_related("user", "training__project")
            return Response(EnrollmentSerializer(records, many=True).data)

        serializer = AssignEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = set(serializer.validated_data["user_ids"])
        for group_id in serializer.validated_data["group_ids"]:
            group = UserGroup.objects.filter(
                id=group_id, company_id=request.user.company_id
            ).first()
            if group:
                user_ids.update(str(u.id) for u in group.members.all())

        users = User.objects.filter(id__in=user_ids, company_id=request.user.company_id)
        created = []
        for user in users:
            enrollment, was_created = Enrollment.objects.get_or_create(
                user=user,
                training=training,
                defaults={
                    "assigned_by": request.user,
                    "due_date": serializer.validated_data.get("due_date"),
                },
            )
            if was_created:
                created.append(enrollment)

        return Response(
            {
                "assigned": EnrollmentSerializer(created, many=True).data,
                "assigned_count": len(created),
                "already_assigned": len(users) - len(created),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    partial_update=extend_schema(tags=["Capacitaciones"], summary="Actualizar módulo"),
    destroy=extend_schema(tags=["Capacitaciones"], summary="Eliminar módulo"),
)
class ModuleViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Los módulos se crean desde su capacitación (`POST /trainings/{id}/modules/`),
    no en la ruta de lista: sin `training` quedarían huérfanos. Por eso se
    componen los mixins en vez de usar `ModelViewSet`.

    `post` debe figurar en `http_method_names` para que funcionen las @action
    anidadas (crear lección, reordenar); el enrutador no expone `POST /modules/`
    porque no existe el método `create`.
    """

    serializer_class = ModuleSerializer
    permission_classes = [IsInstructor]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Module.objects.filter(
            training__project__company_id=self.request.user.company_id
        ).prefetch_related("lessons__materials")

    @extend_schema(tags=["Capacitaciones"], summary="Listar/crear lecciones del módulo")
    @action(detail=True, methods=["get", "post"])
    def lessons(self, request, pk=None):
        module = self.get_object()

        if request.method == "GET":
            return Response(LessonSerializer(module.lessons.all(), many=True).data)

        serializer = LessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data.get("order") or module.lessons.count()
        lesson = serializer.save(module=module, order=order)
        return Response(LessonSerializer(lesson).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Capacitaciones"], request=ReorderSerializer, summary="Reordenar lecciones")
    @action(detail=True, methods=["post"], url_path="lessons/reorder")
    def reorder_lessons(self, request, pk=None):
        module = self.get_object()
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            for index, lesson_id in enumerate(serializer.validated_data["order"]):
                Lesson.objects.filter(id=lesson_id, module=module).update(order=index)
        return Response(LessonSerializer(module.lessons.all(), many=True).data)


# ═════════════════════════════════════════════════════════════
#  Lecciones · progreso, notas y carga de material
# ═════════════════════════════════════════════════════════════
class LessonViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Las lecciones se crean desde su módulo (`POST /modules/{id}/lessons/`).
    `POST /lessons/` no existe: una lección sin módulo no tiene sentido.
    """

    serializer_class = LessonSerializer
    permission_classes = [IsInstructorOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    # Declarado a nivel de clase para que las @action puedan sobrescribirlo.
    throttle_scope: str | None = None

    def get_queryset(self):
        return Lesson.objects.filter(
            module__training__project__company_id=self.request.user.company_id
        ).select_related("module__training__project").prefetch_related("materials")

    # ── Progreso (RF-032, RF-033) ────────────────────────────
    @extend_schema(
        tags=["Aprendizaje"],
        request=ProgressUpdateSerializer,
        responses=LessonProgressSerializer,
        summary="Guardar posición de reproducción",
    )
    @action(detail=True, methods=["patch"], permission_classes=[IsAuthenticated])
    def progress(self, request, pk=None):
        lesson = self.get_object()
        enrollment = self._enrollment_for(request.user, lesson)

        serializer = ProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
        record.position_seconds = serializer.validated_data["position_seconds"]
        record.watched_seconds = max(
            record.watched_seconds,
            serializer.validated_data.get("watched_seconds", record.position_seconds),
        )
        record.last_viewed_at = timezone.now()

        auto_complete = ProgressCalculator.should_complete_lesson(
            record.watched_seconds, lesson.duration_seconds
        )
        if auto_complete and not record.completed:
            record.completed = True
            record.completed_at = timezone.now()

        record.save()
        enrollment.recalculate_progress()

        return Response(LessonProgressSerializer(record).data)

    @extend_schema(tags=["Aprendizaje"], request=None, summary="Marcar lección completada")
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        lesson = self.get_object()
        enrollment = self._enrollment_for(request.user, lesson)

        record, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
        record.mark_completed()
        enrollment.recalculate_progress()

        return Response(
            {
                "lesson_progress": LessonProgressSerializer(record).data,
                "training_progress": float(enrollment.progress),
                "training_status": enrollment.status,
            }
        )

    @extend_schema(tags=["Aprendizaje"], summary="Notas personales de la lección")
    @action(detail=True, methods=["get", "post"], permission_classes=[IsAuthenticated])
    def notes(self, request, pk=None):
        lesson = self.get_object()

        if request.method == "GET":
            records = Note.objects.filter(user=request.user, lesson=lesson)
            return Response(NoteSerializer(records, many=True).data)

        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.save(user=request.user, lesson=lesson)
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)

    # ── Carga de material ────────────────────────────────────
    @extend_schema(
        tags=["Materiales"],
        request=UploadSessionCreateSerializer,
        responses=UploadSessionSerializer,
        summary="Iniciar carga por trozos (archivos grandes)",
    )
    @action(
        detail=True, methods=["post"], url_path="materials/upload-session",
        permission_classes=[IsInstructor], throttle_scope="upload",
    )
    def upload_session(self, request, pk=None):
        lesson = self.get_object()
        serializer = UploadSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        filename = sanitize_filename(serializer.validated_data["filename"])
        size_bytes = serializer.validated_data["size_bytes"]
        validate_declared(filename, size_bytes)  # extensión y tamaño

        session = UploadSession.objects.create(
            lesson=lesson,
            user=request.user,
            filename=filename,
            mime_type=serializer.validated_data.get("mime_type", ""),
            size_bytes=size_bytes,
            chunk_size=settings.STORAGE_SETTINGS["UPLOAD_CHUNK_SIZE_MB"] * 1024 * 1024,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        return Response(UploadSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Materiales"],
        responses=MaterialSerializer,
        summary="Carga directa (multipart) para archivos pequeños",
    )
    @action(
        detail=True, methods=["post"], url_path="materials",
        permission_classes=[IsInstructor], throttle_scope="upload",
    )
    def upload_material(self, request, pk=None):
        lesson = self.get_object()
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Debe adjuntar un archivo."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = sanitize_filename(uploaded.name)
        validate_declared(filename, uploaded.size)

        tmp_dir = Path(settings.STORAGE_SETTINGS["TMP_DIR"])
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{uuid.uuid4().hex}_{filename}"
        with tmp_path.open("wb") as handle:
            for chunk in uploaded.chunks():
                handle.write(chunk)

        result = UploadMaterialUseCase(
            storage=get_storage(), publisher=get_event_publisher()
        ).execute(
            UploadMaterialInput(
                lesson_id=lesson.id,
                temp_path=tmp_path,
                original_filename=filename,
                user_id=request.user.id,
            )
        )

        AuditLog.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            action=AuditLog.Action.MATERIAL_UPLOADED,
            entity_type="Material",
            entity_id=result.material.id,
            changes={"filename": filename, "lesson": str(lesson.id)},
        )
        return Response(MaterialSerializer(result.material).data, status=status.HTTP_201_CREATED)

    # ── Interno ──────────────────────────────────────────────
    @staticmethod
    def _enrollment_for(user, lesson: Lesson) -> Enrollment:
        enrollment = Enrollment.objects.filter(
            user=user, training_id=lesson.module.training_id
        ).first()
        if enrollment is None:
            raise NotEnrolled
        return enrollment


# ═════════════════════════════════════════════════════════════
#  Carga por trozos
# ═════════════════════════════════════════════════════════════
class UploadChunkView(APIView):
    """PUT de un trozo del archivo; los trozos se guardan en disco temporal."""

    permission_classes = [IsInstructor]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Materiales"], summary="Enviar un trozo del archivo")
    def put(self, request, upload_id):
        session = self._session(request, upload_id)
        try:
            index = int(request.query_params.get("index", ""))
        except ValueError:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Índice de trozo inválido."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.FILES.get("chunk") or request.data.get("chunk")
        if payload is None:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Falta el contenido del trozo."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chunk_dir = Path(settings.STORAGE_SETTINGS["TMP_DIR"]) / "uploads" / str(session.id)
        chunk_dir.mkdir(parents=True, exist_ok=True)
        with (chunk_dir / f"{index:06d}.part").open("wb") as handle:
            for block in payload.chunks():
                handle.write(block)

        received = set(session.received_chunks or [])
        received.add(index)
        session.received_chunks = sorted(received)
        session.save(update_fields=["received_chunks", "updated_at"])

        return Response(
            {
                "received": len(session.received_chunks),
                "total": session.total_chunks,
                "progress": round(len(session.received_chunks) / session.total_chunks * 100, 1),
            }
        )

    @extend_schema(tags=["Materiales"], summary="Completar la carga y crear el material")
    def post(self, request, upload_id):
        session = self._session(request, upload_id)
        chunk_dir = Path(settings.STORAGE_SETTINGS["TMP_DIR"]) / "uploads" / str(session.id)

        missing = set(range(session.total_chunks)) - set(session.received_chunks or [])
        if missing:
            return Response(
                {
                    "error": {
                        "code": "INCOMPLETE_UPLOAD",
                        "message": "Faltan trozos por recibir.",
                        "details": {"missing": sorted(missing)[:50]},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        assembled = chunk_dir / session.filename
        with assembled.open("wb") as target:
            for index in range(session.total_chunks):
                part = chunk_dir / f"{index:06d}.part"
                with part.open("rb") as source:
                    target.write(source.read())
                part.unlink(missing_ok=True)

        result = UploadMaterialUseCase(
            storage=get_storage(), publisher=get_event_publisher()
        ).execute(
            UploadMaterialInput(
                lesson_id=session.lesson_id,
                temp_path=assembled,
                original_filename=session.filename,
                user_id=request.user.id,
            )
        )

        session.completed = True
        session.save(update_fields=["completed", "updated_at"])

        AuditLog.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            action=AuditLog.Action.MATERIAL_UPLOADED,
            entity_type="Material",
            entity_id=result.material.id,
            changes={"filename": session.filename, "chunked": True},
        )
        return Response(MaterialSerializer(result.material).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _session(request, upload_id) -> UploadSession:
        session = UploadSession.objects.filter(id=upload_id, user=request.user).first()
        if session is None or session.is_expired:
            raise NotFound("La sesión de carga no existe o expiró.")
        return session


# ═════════════════════════════════════════════════════════════
#  Materiales
# ═════════════════════════════════════════════════════════════
@extend_schema_view(
    retrieve=extend_schema(tags=["Materiales"], summary="Detalle del material"),
    destroy=extend_schema(tags=["Materiales"], summary="Eliminar material"),
)
class MaterialViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Los materiales se crean subiendo el archivo a una lección
    (`POST /lessons/{id}/materials/`), nunca por la ruta de lista.
    """

    serializer_class = MaterialSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return Material.objects.filter(
            project__company_id=self.request.user.company_id
        ).select_related("lesson__module__training", "project")

    def perform_destroy(self, instance):
        """CU-17: cancela el procesamiento, borra lógicamente y limpia los chunks."""
        from src.modules.ai.infrastructure.models import Chunk
        from src.modules.projects.infrastructure.models import VectorCollection

        self._cancel_running_ingestion(instance)

        Chunk.objects.filter(material=instance).delete()
        VectorCollection.objects.filter(project_id=instance.project_id).update(
            status=VectorCollection.Status.PENDING
        )
        instance.delete()

        AuditLog.objects.create(
            company_id=self.request.user.company_id,
            user=self.request.user,
            action=AuditLog.Action.CONTENT_DELETED,
            entity_type="Material",
            entity_id=instance.id,
        )

    @staticmethod
    def _cancel_running_ingestion(material) -> None:
        """
        Revoca la tarea de ingesta en curso.

        Un worker puede estar transcribiendo un video de una hora: dejarlo
        correr tras el borrado desperdicia el slot y retrasa las subidas
        siguientes. La tarea además comprueba por su cuenta si el material
        desapareció, así que la revocación es la vía rápida, no la única.
        """
        from config.celery import app as celery_app

        running = material.processing_jobs.filter(
            status=ProcessingJob.Status.RUNNING
        ).exclude(celery_task_id="")

        for job in running:
            try:
                celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
            except Exception:  # pragma: no cover - el broker puede no responder
                pass
            job.finish(success=False, error="Cancelada: el material fue eliminado.")

    @extend_schema(tags=["Materiales"], summary="Estado de procesamiento")
    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        material = self.get_object()
        job = material.processing_jobs.first()
        return Response(
            {
                "status": material.status,
                "step": job.step if job else "",
                "progress": job.progress if job else (100 if material.is_queryable else 0),
                "error_code": material.error_code,
                "error_detail": material.error_detail,
                "partial_analysis": material.partial_analysis,
            }
        )

    @extend_schema(tags=["Materiales"], responses=ProcessingJobSerializer(many=True), summary="Historial de procesamiento")
    @action(detail=True, methods=["get"])
    def jobs(self, request, pk=None):
        material = self.get_object()
        return Response(ProcessingJobSerializer(material.processing_jobs.all()[:20], many=True).data)

    @extend_schema(tags=["Materiales"], request=None, summary="Reprocesar (RF-025)")
    @action(detail=True, methods=["post"], permission_classes=[IsInstructor])
    def reprocess(self, request, pk=None):
        from src.modules.ai.infrastructure.tasks import ingest_material

        material = self.get_object()
        if not MaterialStateMachine.can_be_reprocessed(material.status):
            return Response(
                {
                    "error": {
                        "code": "MATERIAL_BUSY",
                        "message": "El material ya se está procesando.",
                        "details": {"status": material.status},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )
        task = ingest_material.delay(str(material.id), force=True)
        return Response({"task_id": task.id, "status": "PENDING"}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(tags=["Materiales"], summary="URL firmada para reproducir el video")
    @action(detail=True, methods=["get"])
    def stream(self, request, pk=None):
        material = self.get_object()
        self._assert_access(request.user, material)

        storage = get_storage()
        if not storage.exists(material.file):
            raise NotFound("El archivo no está disponible.")

        return Response(
            {
                "url": storage.url(material.file),
                "mime_type": material.mime_type,
                "duration_seconds": material.duration_seconds,
                "thumbnail": storage.url(material.thumbnail) if material.thumbnail else None,
            }
        )

    @extend_schema(tags=["Materiales"], summary="Transcripción con timestamps")
    @action(detail=True, methods=["get"])
    def transcript(self, request, pk=None):
        from src.modules.ai.presentation.serializers import TranscriptSerializer

        material = self._queryable(request, pk)
        transcript = getattr(material, "transcript", None)
        if transcript is None:
            return Response({"detail": "Este material no tiene transcripción."}, status=404)
        return Response(TranscriptSerializer(transcript).data)

    @extend_schema(tags=["Materiales"], summary="Capítulos detectados")
    @action(detail=True, methods=["get"])
    def chapters(self, request, pk=None):
        from src.modules.ai.presentation.serializers import ChapterSerializer

        material = self._queryable(request, pk)
        return Response(ChapterSerializer(material.chapters.all(), many=True).data)

    @extend_schema(tags=["Materiales"], summary="Conceptos clave")
    @action(detail=True, methods=["get"])
    def concepts(self, request, pk=None):
        from src.modules.ai.presentation.serializers import ConceptSerializer

        material = self._queryable(request, pk)
        return Response(ConceptSerializer(material.concepts.all(), many=True).data)

    @extend_schema(tags=["Materiales"], summary="Preguntas frecuentes generadas")
    @action(detail=True, methods=["get"])
    def faqs(self, request, pk=None):
        from src.modules.ai.presentation.serializers import FaqSerializer

        material = self._queryable(request, pk)
        return Response(FaqSerializer(material.faqs.all(), many=True).data)

    # ── Interno ──────────────────────────────────────────────
    def _queryable(self, request, pk) -> Material:
        material = self.get_object()
        self._assert_access(request.user, material)
        if not material.is_queryable:
            raise MaterialNotQueryable(details={"status": material.status})
        return material

    @staticmethod
    def _assert_access(user, material: Material) -> None:
        if user.can_manage_content:
            return
        enrolled = Enrollment.objects.filter(
            user=user, training_id=material.lesson.module.training_id
        ).exists()
        if not enrolled:
            raise NotEnrolled


# ═════════════════════════════════════════════════════════════
#  Vista del estudiante
# ═════════════════════════════════════════════════════════════
@extend_schema_view(get=extend_schema(tags=["Aprendizaje"], summary="Mis capacitaciones"))
class MyTrainingsView(ListAPIView):
    serializer_class = MyTrainingSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status"]

    def get_queryset(self):
        return (
            Enrollment.objects.filter(user=self.request.user)
            .select_related("training__project")
            .order_by("-assigned_at")
        )


class MyTrainingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Aprendizaje"], summary="Detalle de mi capacitación con progreso")
    def get(self, request, training_id):
        enrollment = (
            Enrollment.objects.filter(user=request.user, training_id=training_id)
            .select_related("training__project")
            .first()
        )
        if enrollment is None:
            raise NotEnrolled

        training = (
            Training.objects.filter(pk=training_id)
            .prefetch_related("modules__lessons__materials")
            .first()
        )
        progress_map = {
            str(record.lesson_id): LessonProgressSerializer(record).data
            for record in LessonProgress.objects.filter(enrollment=enrollment)
        }

        data = TrainingDetailSerializer(training).data
        data["enrollment"] = MyTrainingSerializer(enrollment).data
        data["lesson_progress"] = progress_map
        return Response(data)


class NoteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Aprendizaje"], summary="Editar nota")
    def patch(self, request, note_id):
        note = Note.objects.filter(id=note_id, user=request.user).first()
        if note is None:
            raise NotFound("Nota no encontrada.")
        serializer = NoteSerializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Aprendizaje"], summary="Eliminar nota")
    def delete(self, request, note_id):
        Note.objects.filter(id=note_id, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EnrollmentDetailView(APIView):
    permission_classes = [IsInstructor]

    @extend_schema(tags=["Aprendizaje"], summary="Quitar la asignación")
    def delete(self, request, enrollment_id):
        Enrollment.objects.filter(
            id=enrollment_id, training__project__company_id=request.user.company_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ═════════════════════════════════════════════════════════════
#  Media protegida
# ═════════════════════════════════════════════════════════════
@extend_schema(tags=["Materiales"], summary="Servir media protegida (URL firmada)")
@api_view(["GET"])
@permission_classes([AllowAny])  # la autorización va en la firma del token
def serve_protected_media(request, token: str):
    """
    Entrega el archivo validando la firma temporal.

    En producción se delega a nginx con `X-Accel-Redirect`, de modo que ningún
    worker de Python queda ocupado sirviendo un video de 2 GB.
    """
    storage = get_storage()
    try:
        relative = storage.verify_signed(token)
    except Exception:
        raise NotFound("Enlace inválido o expirado.")

    if not storage.exists(relative):
        raise NotFound("Archivo no encontrado.")

    if settings.DEBUG:
        return FileResponse(storage.open(relative))

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{relative}"
    response["Content-Type"] = ""
    return response
