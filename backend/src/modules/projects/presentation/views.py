"""CU-05 · Gestión de proyectos y su colección vectorial."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from src.modules.accounts.infrastructure.models import AuditLog
from src.shared.presentation.permissions import IsAdmin, IsInstructorOrReadOnly

from ..infrastructure.models import Project, ProjectMember, VectorCollection
from .serializers import (
    ProjectMemberSerializer,
    ProjectSerializer,
    ProjectStatsSerializer,
    VectorCollectionSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Proyectos"], summary="Listar proyectos"),
    retrieve=extend_schema(tags=["Proyectos"], summary="Detalle del proyecto"),
    create=extend_schema(tags=["Proyectos"], summary="Crear proyecto"),
    partial_update=extend_schema(tags=["Proyectos"], summary="Actualizar proyecto"),
    destroy=extend_schema(tags=["Proyectos"], summary="Archivar proyecto"),
)
class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsInstructorOrReadOnly]
    filterset_fields = ["status"]
    search_fields = ["name", "code", "description"]
    ordering_fields = ["name", "created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return (
            Project.objects.filter(company_id=self.request.user.company_id)
            .select_related("vector_collection")
            .annotate(
                training_count=Count("trainings", distinct=True),
                material_count=Count("materials", distinct=True),
            )
        )

    @transaction.atomic
    def perform_create(self, serializer):
        project = serializer.save(company_id=self.request.user.company_id)

        # Aprovisiona la colección vectorial del proyecto (RN-02).
        company_slug = self.request.user.company.slug if self.request.user.company else "default"
        VectorCollection.objects.create(
            project=project,
            index_path=f"{company_slug}/{project.id}",
            status=VectorCollection.Status.PENDING,
        )

        ProjectMember.objects.get_or_create(
            project=project, user=self.request.user, defaults={"role": ProjectMember.Role.OWNER}
        )

        AuditLog.objects.create(
            company_id=self.request.user.company_id,
            user=self.request.user,
            action=AuditLog.Action.CONTENT_CREATED,
            entity_type="Project",
            entity_id=project.id,
            changes={"name": project.name},
        )

    def perform_destroy(self, instance):
        """Archiva en lugar de borrar: el conocimiento y el histórico se conservan."""
        instance.status = Project.Status.ARCHIVED
        instance.save(update_fields=["status"])
        AuditLog.objects.create(
            company_id=self.request.user.company_id,
            user=self.request.user,
            action=AuditLog.Action.CONTENT_DELETED,
            entity_type="Project",
            entity_id=instance.id,
        )

    @extend_schema(tags=["Proyectos"], responses=ProjectStatsSerializer, summary="Estadísticas")
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        from src.modules.ai.infrastructure.models import Chunk
        from src.modules.trainings.infrastructure.models import Enrollment, Material, Training

        project = self.get_object()

        trainings = Training.objects.filter(project=project)
        materials = Material.objects.filter(project=project)

        data = {
            "trainings": trainings.count(),
            "published_trainings": trainings.filter(status=Training.Status.PUBLISHED).count(),
            "materials": materials.count(),
            "materials_available": materials.filter(status=Material.Status.AVAILABLE).count(),
            "materials_processing": materials.filter(
                status__in=[Material.Status.PENDING, Material.Status.PROCESSING, Material.Status.ANALYZING]
            ).count(),
            "materials_error": materials.filter(status=Material.Status.ERROR).count(),
            "chunks": Chunk.objects.filter(project=project).count(),
            "vectors": getattr(getattr(project, "vector_collection", None), "vector_count", 0),
            "enrolled_users": Enrollment.objects.filter(training__project=project)
            .values("user_id")
            .distinct()
            .count(),
        }
        return Response(ProjectStatsSerializer(data).data)

    @extend_schema(
        tags=["Proyectos"],
        responses=VectorCollectionSerializer,
        summary="Estado de la colección vectorial",
    )
    @action(detail=True, methods=["get"], url_path="vector-collection")
    def vector_collection(self, request, pk=None):
        project = self.get_object()
        collection, _ = VectorCollection.objects.get_or_create(
            project=project,
            defaults={"index_path": f"{request.user.company.slug}/{project.id}"},
        )
        return Response(VectorCollectionSerializer(collection).data)

    @extend_schema(
        tags=["Proyectos"], request=None, summary="Reconstruir el índice vectorial (CU-18)"
    )
    @action(detail=True, methods=["post"], url_path="rebuild-index", permission_classes=[IsAdmin])
    def rebuild_index(self, request, pk=None):
        from src.modules.ai.infrastructure.tasks import rebuild_project_index

        project = self.get_object()
        task = rebuild_project_index.delay(str(project.id))

        AuditLog.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            action=AuditLog.Action.INDEX_REBUILT,
            entity_type="Project",
            entity_id=project.id,
        )
        return Response(
            {"task_id": task.id, "status": "REBUILDING"}, status=status.HTTP_202_ACCEPTED
        )

    @extend_schema(tags=["Proyectos"], summary="Responsables del proyecto")
    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        project = self.get_object()

        if request.method == "GET":
            members = ProjectMember.objects.filter(project=project).select_related("user")
            return Response(ProjectMemberSerializer(members, many=True).data)

        serializer = ProjectMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if user.company_id != request.user.company_id:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": "Usuario no encontrado."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        member, _ = ProjectMember.objects.update_or_create(
            project=project, user=user, defaults={"role": serializer.validated_data["role"]}
        )
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Proyectos"], summary="Quitar un responsable")
    @action(detail=True, methods=["delete"], url_path=r"members/(?P<member_id>[^/.]+)")
    def remove_member(self, request, pk=None, member_id=None):
        project = self.get_object()
        ProjectMember.objects.filter(project=project, id=member_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
