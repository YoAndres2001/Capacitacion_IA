"""Vistas del módulo de evaluaciones."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.modules.accounts.infrastructure.models import AuditLog
from src.modules.trainings.infrastructure.models import Enrollment, Training
from src.shared.container import get_llm
from src.shared.domain.exceptions import (
    ExamLocked,
    InsufficientProgress,
    MaxAttemptsReached,
    NotEnrolled,
    NotFoundError,
    PermissionDeniedError,
)
from src.shared.presentation.permissions import IsInstructor

from ..infrastructure.exam_generator import assert_enough_content
from ..infrastructure.models import Answer, Attempt, Exam, Question
from ..infrastructure.tasks import generate_exam, grade_attempt
from .serializers import (
    AttemptDetailSerializer,
    AttemptResultSerializer,
    AttemptSerializer,
    ExamDetailSerializer,
    ExamGenerateSerializer,
    ExamResultsSerializer,
    ExamSerializer,
    QuestionSerializer,
    SaveAnswersSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Evaluaciones"], summary="Listar exámenes"),
    retrieve=extend_schema(tags=["Evaluaciones"], summary="Detalle del examen"),
    create=extend_schema(tags=["Evaluaciones"], summary="Crear examen manualmente"),
)
class ExamViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["training", "status"]
    search_fields = ["title"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    throttle_scope: str | None = None

    def get_queryset(self):
        queryset = Exam.objects.filter(
            training__project__company_id=self.request.user.company_id
        ).select_related("training")
        if not self.request.user.can_manage_content:
            # El estudiante solo ve exámenes publicados de cursos donde está inscrito.
            queryset = queryset.filter(
                status=Exam.Status.PUBLISHED,
                training__enrollments__user=self.request.user,
            ).distinct()
        return queryset

    def get_serializer_class(self):
        return ExamDetailSerializer if self.action == "retrieve" else ExamSerializer

    def get_permissions(self):
        if self.action in {"create", "partial_update", "destroy", "publish", "archive", "questions"}:
            return [IsInstructor()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        exam = self.get_object()
        if not exam.can_edit_questions() and "questions" in self.request.data:
            raise ExamLocked
        serializer.save()

    @extend_schema(tags=["Evaluaciones"], request=None, summary="Publicar examen")
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.publish()  # valida preguntas, puntos y claves de respuesta

        AuditLog.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            action=AuditLog.Action.EXAM_PUBLISHED,
            entity_type="Exam",
            entity_id=exam.id,
            changes={"title": exam.title, "questions": exam.questions.count()},
        )
        return Response(ExamSerializer(exam).data)

    @extend_schema(tags=["Evaluaciones"], request=None, summary="Archivar examen")
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        exam = self.get_object()
        exam.archive()
        return Response(ExamSerializer(exam).data)

    @extend_schema(tags=["Evaluaciones"], summary="Preguntas del examen (instructor)")
    @action(detail=True, methods=["get", "post"])
    def questions(self, request, pk=None):
        exam = self.get_object()

        if request.method == "GET":
            return Response(
                QuestionSerializer(exam.questions.prefetch_related("options"), many=True).data
            )

        if not exam.can_edit_questions():
            raise ExamLocked

        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.save(exam=exam, order=exam.questions.count())
        return Response(QuestionSerializer(question).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Evaluaciones"], request=None, summary="Iniciar un intento (CU-14)")
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def attempts(self, request, pk=None):
        exam = self.get_object()

        if exam.status != Exam.Status.PUBLISHED:
            raise NotFoundError("El examen no está disponible.")

        enrollment = Enrollment.objects.filter(
            user=request.user, training_id=exam.training_id
        ).first()
        if enrollment is None:
            raise NotEnrolled

        # RN-07 · avance mínimo
        if float(enrollment.progress) < exam.min_progress_required:
            raise InsufficientProgress(
                f"Debe completar al menos el {exam.min_progress_required}% de la capacitación "
                f"(avance actual: {float(enrollment.progress):.0f}%).",
                details={
                    "progress": float(enrollment.progress),
                    "required": exam.min_progress_required,
                },
            )

        # Un intento en curso se reanuda en lugar de crear otro.
        running = Attempt.objects.filter(
            exam=exam, user=request.user, status=Attempt.Status.IN_PROGRESS
        ).first()
        if running is not None:
            if running.is_expired():
                running.submit()
                grade_attempt.delay(str(running.id))
            else:
                return Response(AttemptDetailSerializer(running).data)

        # RN-09 · límite de intentos
        used = Attempt.objects.filter(exam=exam, user=request.user).count()
        if used >= exam.max_attempts:
            raise MaxAttemptsReached(
                f"Ya utilizó sus {exam.max_attempts} intentos.",
                details={"used": used, "max": exam.max_attempts},
            )

        attempt = Attempt.objects.create(
            exam=exam, user=request.user, number=used + 1, max_score=exam.total_points
        )
        return Response(
            AttemptDetailSerializer(attempt).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        tags=["Evaluaciones"],
        request=ExamGenerateSerializer,
        summary="Generar examen con IA (CU-13)",
    )
    @action(
        detail=False, methods=["post"], url_path=r"generate/(?P<training_id>[^/.]+)",
        permission_classes=[IsInstructor], throttle_scope="ai_generate",
    )
    def generate(self, request, training_id=None):
        training = Training.objects.filter(
            id=training_id, project__company_id=request.user.company_id
        ).first()
        if training is None:
            raise NotFoundError("La capacitación no existe.")

        serializer = ExamGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        options = dict(serializer.validated_data)
        options["created_by"] = str(request.user.id)
        options["title"] = options.get("title") or f"Evaluación · {training.title}"

        # Se comprueba ANTES de encolar. El desenlace de la tarea viaja por
        # WebSocket, y una que falla en milisegundos emite el aviso antes de que
        # el navegador alcance a suscribirse: el usuario se queda con una barra
        # de progreso viva para siempre. Lo que ya se sabe aquí se responde aquí.
        assert_enough_content(training, int(options.get("num_questions", 10)))

        task = generate_exam.delay(str(training.id), options)
        return Response(
            {"task_id": task.id, "status": "GENERATING", "training_id": str(training.id)},
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        tags=["Evaluaciones"], responses=ExamResultsSerializer, summary="Resultados agregados"
    )
    @action(detail=True, methods=["get"], permission_classes=[IsInstructor])
    def results(self, request, pk=None):
        exam = self.get_object()
        attempts = Attempt.objects.filter(exam=exam)
        graded = attempts.filter(status=Attempt.Status.GRADED)

        total_graded = graded.count()
        passed = graded.filter(passed=True).count()

        distribution = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
        for attempt in graded:
            percentage = attempt.percentage
            if percentage < 60:
                distribution["0-59"] += 1
            elif percentage < 70:
                distribution["60-69"] += 1
            elif percentage < 80:
                distribution["70-79"] += 1
            elif percentage < 90:
                distribution["80-89"] += 1
            else:
                distribution["90-100"] += 1

        hardest = (
            Answer.objects.filter(attempt__exam=exam)
            .values("question_id", "question__statement")
            .annotate(
                total=Count("id"),
                wrong=Count("id", filter=Q(is_correct=False)),
            )
            .filter(total__gt=0)
            .order_by("-wrong")[:10]
        )

        data = {
            "attempts": attempts.count(),
            "graded": total_graded,
            "passed": passed,
            "pass_rate": round(passed / total_graded * 100, 2) if total_graded else 0.0,
            "average_score": round(
                float(graded.aggregate(avg=Avg("score"))["avg"] or 0), 2
            ),
            "distribution": distribution,
            "hardest_questions": [
                {
                    "question_id": str(row["question_id"]),
                    "statement": row["question__statement"][:160],
                    "attempts": row["total"],
                    "wrong": row["wrong"],
                    "error_rate": round(row["wrong"] / row["total"] * 100, 1),
                }
                for row in hardest
            ],
        }
        return Response(ExamResultsSerializer(data).data)


class QuestionViewSet(viewsets.ModelViewSet):
    """Edición humana de las preguntas generadas por la IA (RF-068)."""

    serializer_class = QuestionSerializer
    permission_classes = [IsInstructor]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Question.objects.filter(
            exam__training__project__company_id=self.request.user.company_id
        ).prefetch_related("options")

    def perform_update(self, serializer):
        if not serializer.instance.exam.can_edit_questions():
            raise ExamLocked
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.exam.can_edit_questions():
            raise ExamLocked
        instance.delete()


class AttemptViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Attempt.objects.select_related("exam__training").prefetch_related("answers")
        if self.request.user.can_manage_content:
            return queryset.filter(
                exam__training__project__company_id=self.request.user.company_id
            )
        return queryset.filter(user=self.request.user)

    def get_serializer_class(self):
        return AttemptDetailSerializer if self.action == "retrieve" else AttemptSerializer

    @extend_schema(
        tags=["Evaluaciones"], request=SaveAnswersSerializer, summary="Guardado parcial"
    )
    @action(detail=True, methods=["patch"])
    def answers(self, request, pk=None):
        attempt = self._own_attempt(request, pk)

        if attempt.status != Attempt.Status.IN_PROGRESS:
            return Response(
                {"error": {"code": "ATTEMPT_CLOSED", "message": "El intento ya fue entregado."}},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = SaveAnswersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question_ids = set(
            str(value) for value in attempt.exam.questions.values_list("id", flat=True)
        )

        with transaction.atomic():
            for entry in serializer.validated_data["answers"]:
                question_id = str(entry["question_id"])
                if question_id not in question_ids:
                    continue
                Answer.objects.update_or_create(
                    attempt=attempt,
                    question_id=question_id,
                    defaults={
                        "selected_option_ids": [str(v) for v in entry.get("selected_option_ids", [])],
                        "text_answer": entry.get("text_answer", ""),
                    },
                )

        return Response({"saved": len(serializer.validated_data["answers"])})

    @extend_schema(tags=["Evaluaciones"], request=None, summary="Entregar y corregir (CU-15)")
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        attempt = self._own_attempt(request, pk)

        if attempt.status != Attempt.Status.IN_PROGRESS:
            return Response(
                {"error": {"code": "ATTEMPT_CLOSED", "message": "El intento ya fue entregado."}},
                status=status.HTTP_409_CONFLICT,
            )

        attempt.submit()
        grade_attempt.delay(str(attempt.id))

        return Response(
            {"attempt_id": str(attempt.id), "status": attempt.status},
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        tags=["Evaluaciones"], responses=AttemptResultSerializer, summary="Resultado con feedback"
    )
    @action(detail=True, methods=["get"])
    def result(self, request, pk=None):
        attempt = self.get_object()
        if attempt.user_id != request.user.id and not request.user.can_manage_content:
            raise PermissionDeniedError

        if attempt.status not in {Attempt.Status.GRADED, Attempt.Status.GRADING}:
            return Response(
                {
                    "error": {
                        "code": "NOT_GRADED",
                        "message": "El intento aún no ha sido corregido.",
                        "details": {"status": attempt.status},
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(AttemptResultSerializer(attempt).data)

    def _own_attempt(self, request, pk) -> Attempt:
        attempt = self.get_object()
        if attempt.user_id != request.user.id:
            raise PermissionDeniedError("Este intento pertenece a otro usuario.")
        return attempt


@extend_schema_view(get=extend_schema(tags=["Evaluaciones"], summary="Mis intentos"))
class MyAttemptsView(ListAPIView):
    serializer_class = AttemptSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["exam", "status", "passed"]

    def get_queryset(self):
        return (
            Attempt.objects.filter(user=self.request.user)
            .select_related("exam__training")
            .order_by("-started_at")
        )


class TrainingExamsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Evaluaciones"], responses=ExamSerializer(many=True), summary="Exámenes del curso"
    )
    def get(self, request, training_id):
        queryset = Exam.objects.filter(
            training_id=training_id, training__project__company_id=request.user.company_id
        )
        if not request.user.can_manage_content:
            queryset = queryset.filter(status=Exam.Status.PUBLISHED)
        return Response(ExamSerializer(queryset, many=True).data)
