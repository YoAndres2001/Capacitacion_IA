"""Analítica y reportes (módulo de solo lectura)."""

from __future__ import annotations

import csv

from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.modules.accounts.infrastructure.models import User
from src.modules.ai.infrastructure.models import AIUsageLog, ChatMessage, Chunk
from src.modules.assessments.infrastructure.models import Attempt, Exam
from src.modules.projects.infrastructure.models import Project
from src.modules.trainings.infrastructure.models import Enrollment, Material, Training
from src.shared.presentation.permissions import IsAdmin


class OverviewView(APIView):
    """RF-070 · KPIs del dashboard del administrador."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Analítica"], summary="Resumen general")
    def get(self, request):
        company_id = request.user.company_id

        users = User.objects.filter(company_id=company_id)
        projects = Project.objects.filter(company_id=company_id)
        trainings = Training.objects.filter(project__company_id=company_id)
        materials = Material.objects.filter(project__company_id=company_id)
        enrollments = Enrollment.objects.filter(training__project__company_id=company_id)
        attempts = Attempt.objects.filter(exam__training__project__company_id=company_id)

        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)

        return Response(
            {
                "users": {
                    "total": users.count(),
                    "active": users.filter(is_active=True).count(),
                    "by_role": list(users.values("role").annotate(count=Count("id"))),
                    "recently_active": users.filter(last_login__gte=thirty_days_ago).count(),
                },
                "content": {
                    "projects": projects.count(),
                    "trainings": trainings.count(),
                    "published_trainings": trainings.filter(
                        status=Training.Status.PUBLISHED
                    ).count(),
                    "materials": materials.count(),
                    "materials_by_status": list(
                        materials.values("status").annotate(count=Count("id"))
                    ),
                    "chunks": Chunk.objects.filter(project__company_id=company_id).count(),
                },
                "learning": {
                    "enrollments": enrollments.count(),
                    "completed": enrollments.filter(
                        status=Enrollment.Status.COMPLETED
                    ).count(),
                    "in_progress": enrollments.filter(
                        status=Enrollment.Status.IN_PROGRESS
                    ).count(),
                    "average_progress": round(
                        float(enrollments.aggregate(avg=Avg("progress"))["avg"] or 0), 2
                    ),
                },
                "assessment": {
                    "exams": Exam.objects.filter(
                        training__project__company_id=company_id
                    ).count(),
                    "attempts": attempts.count(),
                    "graded": attempts.filter(status=Attempt.Status.GRADED).count(),
                    "pass_rate": _pass_rate(attempts),
                },
                "ai": _ai_summary(company_id),
            }
        )


class ProgressReportView(APIView):
    """RF-071 · Progreso por usuario / capacitación / proyecto."""

    permission_classes = [IsAdmin]

    @extend_schema(
        tags=["Analítica"],
        parameters=[
            OpenApiParameter("project", str),
            OpenApiParameter("training", str),
            OpenApiParameter("user", str),
        ],
        summary="Reporte de progreso",
    )
    def get(self, request):
        rows = _progress_queryset(request)
        return Response(
            [
                {
                    "enrollment_id": str(row.id),
                    "user_id": str(row.user_id),
                    "user_name": row.user.get_full_name(),
                    "user_email": row.user.email,
                    "training_id": str(row.training_id),
                    "training_title": row.training.title,
                    "project_name": row.training.project.name,
                    "status": row.status,
                    "progress": float(row.progress),
                    "assigned_at": row.assigned_at,
                    "completed_at": row.completed_at,
                    "due_date": row.due_date,
                }
                for row in rows[:2000]
            ]
        )


class ExamResultsReportView(APIView):
    """RF-072 · Resultados de evaluaciones agregados."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Analítica"], summary="Resultados de exámenes")
    def get(self, request):
        attempts = Attempt.objects.filter(
            exam__training__project__company_id=request.user.company_id,
            status=Attempt.Status.GRADED,
        ).select_related("exam__training")

        if training_id := request.query_params.get("training"):
            attempts = attempts.filter(exam__training_id=training_id)

        by_exam = (
            attempts.values("exam_id", "exam__title", "exam__training__title")
            .annotate(
                attempts=Count("id"),
                passed=Count("id", filter=Q(passed=True)),
                average=Avg("score"),
            )
            .order_by("-attempts")
        )

        return Response(
            {
                "summary": {
                    "attempts": attempts.count(),
                    "pass_rate": _pass_rate(attempts),
                    "average_score": round(
                        float(attempts.aggregate(avg=Avg("score"))["avg"] or 0), 2
                    ),
                },
                "by_exam": [
                    {
                        "exam_id": str(row["exam_id"]),
                        "exam_title": row["exam__title"],
                        "training_title": row["exam__training__title"],
                        "attempts": row["attempts"],
                        "passed": row["passed"],
                        "pass_rate": round(row["passed"] / row["attempts"] * 100, 1)
                        if row["attempts"]
                        else 0.0,
                        "average_score": round(float(row["average"] or 0), 2),
                    }
                    for row in by_exam
                ],
            }
        )


class AIUsageReportView(APIView):
    """RF-073 · Utilización de IA."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Analítica"], summary="Uso de IA por período")
    def get(self, request):
        return Response(_ai_summary(request.user.company_id, detailed=True))


class ExportView(APIView):
    """RF-074 · Exportación CSV."""

    permission_classes = [IsAdmin]

    @extend_schema(
        tags=["Analítica"],
        parameters=[OpenApiParameter("report", str), OpenApiParameter("format", str)],
        summary="Exportar reporte",
    )
    def get(self, request):
        report = request.query_params.get("report", "progress")

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report}.csv"'
        response.write("﻿")  # BOM para que Excel reconozca UTF-8

        writer = csv.writer(response, delimiter=";")

        if report == "progress":
            writer.writerow(
                ["Usuario", "Correo", "Proyecto", "Capacitación", "Estado", "Avance %", "Completado"]
            )
            for row in _progress_queryset(request)[:10_000]:
                writer.writerow(
                    [
                        row.user.get_full_name(),
                        row.user.email,
                        row.training.project.name,
                        row.training.title,
                        row.get_status_display(),
                        f"{float(row.progress):.1f}",
                        row.completed_at.strftime("%Y-%m-%d") if row.completed_at else "",
                    ]
                )
        elif report == "attempts":
            writer.writerow(
                ["Usuario", "Examen", "Capacitación", "Intento", "Puntaje", "%", "Aprobado", "Fecha"]
            )
            attempts = (
                Attempt.objects.filter(
                    exam__training__project__company_id=request.user.company_id,
                    status=Attempt.Status.GRADED,
                )
                .select_related("user", "exam__training")
                .order_by("-graded_at")[:10_000]
            )
            for attempt in attempts:
                writer.writerow(
                    [
                        attempt.user.get_full_name(),
                        attempt.exam.title,
                        attempt.exam.training.title,
                        attempt.number,
                        f"{float(attempt.score or 0):.2f}",
                        f"{attempt.percentage:.1f}",
                        "Sí" if attempt.passed else "No",
                        attempt.graded_at.strftime("%Y-%m-%d %H:%M") if attempt.graded_at else "",
                    ]
                )
        else:
            writer.writerow(["Reporte no reconocido"])

        return response


class MyStatsView(APIView):
    """Estadísticas personales del estudiante."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Analítica"], summary="Mis estadísticas")
    def get(self, request):
        enrollments = Enrollment.objects.filter(user=request.user)
        attempts = Attempt.objects.filter(user=request.user, status=Attempt.Status.GRADED)

        return Response(
            {
                "trainings": {
                    "assigned": enrollments.count(),
                    "completed": enrollments.filter(
                        status=Enrollment.Status.COMPLETED
                    ).count(),
                    "in_progress": enrollments.filter(
                        status=Enrollment.Status.IN_PROGRESS
                    ).count(),
                    "average_progress": round(
                        float(enrollments.aggregate(avg=Avg("progress"))["avg"] or 0), 1
                    ),
                },
                "exams": {
                    "taken": attempts.count(),
                    "passed": attempts.filter(passed=True).count(),
                    "average_score": round(
                        float(attempts.aggregate(avg=Avg("score"))["avg"] or 0), 1
                    ),
                },
                "ai": {
                    "questions_asked": ChatMessage.objects.filter(
                        session__user=request.user, role=ChatMessage.Role.USER
                    ).count()
                },
            }
        )


# ── Utilidades ───────────────────────────────────────────────
def _pass_rate(attempts) -> float:
    graded = attempts.filter(status=Attempt.Status.GRADED)
    total = graded.count()
    if not total:
        return 0.0
    return round(graded.filter(passed=True).count() / total * 100, 2)


def _progress_queryset(request):
    queryset = Enrollment.objects.filter(
        training__project__company_id=request.user.company_id
    ).select_related("user", "training__project")

    if project_id := request.query_params.get("project"):
        queryset = queryset.filter(training__project_id=project_id)
    if training_id := request.query_params.get("training"):
        queryset = queryset.filter(training_id=training_id)
    if user_id := request.query_params.get("user"):
        queryset = queryset.filter(user_id=user_id)

    return queryset.order_by("user__first_name", "training__title")


def _ai_summary(company_id, *, detailed: bool = False) -> dict:
    from django.db.models import Sum

    usage = AIUsageLog.objects.filter(company_id=company_id)
    totals = usage.aggregate(
        calls=Count("id"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
        cost=Sum("cost_usd"),
    )

    answers = ChatMessage.objects.filter(
        session__training__project__company_id=company_id, role=ChatMessage.Role.ASSISTANT
    )
    total_answers = answers.count()

    summary = {
        "calls": totals["calls"] or 0,
        "total_tokens": (totals["prompt_tokens"] or 0) + (totals["completion_tokens"] or 0),
        "cost_usd": float(totals["cost"] or 0),
        "chat_answers": total_answers,
        "no_context_rate": round(
            answers.filter(grounded=False).count() / total_answers * 100, 2
        )
        if total_answers
        else 0.0,
    }

    if detailed:
        summary["by_purpose"] = [
            {
                **row,
                "cost_usd": float(row["cost_usd"] or 0),
            }
            for row in usage.values("purpose", "provider", "model")
            .annotate(
                calls=Count("id"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                cost_usd=Sum("cost_usd"),
            )
            .order_by("-calls")
        ]
        summary["top_questions"] = list(
            ChatMessage.objects.filter(
                session__training__project__company_id=company_id,
                role=ChatMessage.Role.USER,
            )
            .values("content")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        )

    return summary
