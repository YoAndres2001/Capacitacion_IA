"""Vistas de administración de usuarios, grupos y empresa."""

from __future__ import annotations

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.shared.container import get_notifier
from src.shared.presentation.permissions import IsAdmin, IsSuperAdmin

from ..infrastructure.models import AuditLog, Company, User, UserGroup
from .auth_views import generate_temp_password
from .serializers import (
    CompanySerializer,
    GroupMembersSerializer,
    UserCreateSerializer,
    UserGroupSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=["Usuarios"], summary="Listar usuarios de mi empresa"),
    retrieve=extend_schema(tags=["Usuarios"], summary="Detalle de un usuario"),
    create=extend_schema(tags=["Usuarios"], summary="Crear usuario"),
    partial_update=extend_schema(tags=["Usuarios"], summary="Actualizar usuario"),
    destroy=extend_schema(tags=["Usuarios"], summary="Desactivar usuario"),
)
class UserViewSet(viewsets.ModelViewSet):
    """CRUD de usuarios. Siempre acotado a la empresa del solicitante (RN-01)."""

    permission_classes = [IsAdmin]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name", "job_title"]
    ordering_fields = ["created_at", "first_name", "email"]
    ordering = ["first_name"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = User.objects.select_related("company")
        user = self.request.user
        if user.role != User.Role.SUPERADMIN:
            qs = qs.filter(company_id=user.company_id)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserUpdateSerializer
        return UserSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        actor = self.request.user
        password = serializer.validated_data.pop("password", "") or generate_temp_password()

        user = serializer.save(company_id=actor.company_id)
        user.set_password(password)
        user.save(update_fields=["password"])

        AuditLog.objects.create(
            company_id=actor.company_id,
            user=actor,
            action=AuditLog.Action.USER_CREATED,
            entity_type="User",
            entity_id=user.id,
            changes={"email": user.email, "role": user.role},
        )

        get_notifier().send_email(
            to=[user.email],
            subject="Bienvenido a Capacita IA",
            template="user_invitation",
            context={
                "user_name": user.get_short_name(),
                "email": user.email,
                "temp_password": password,
                "company": actor.company.name if actor.company else "",
            },
        )

    def perform_update(self, serializer):
        previous_role = serializer.instance.role
        user = serializer.save()
        if user.role != previous_role:
            AuditLog.objects.create(
                company_id=self.request.user.company_id,
                user=self.request.user,
                action=AuditLog.Action.ROLE_CHANGED,
                entity_type="User",
                entity_id=user.id,
                changes={"from": previous_role, "to": user.role},
            )

    def perform_destroy(self, instance):
        """No se elimina: se desactiva, para conservar el histórico de aprendizaje."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        AuditLog.objects.create(
            company_id=self.request.user.company_id,
            user=self.request.user,
            action=AuditLog.Action.USER_DEACTIVATED,
            entity_type="User",
            entity_id=instance.id,
        )

    @extend_schema(tags=["Usuarios"], request=None, summary="Activar usuario")
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(UserSerializer(user).data)

    @extend_schema(tags=["Usuarios"], request=None, summary="Desactivar usuario")
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {"error": {"code": "SELF_DEACTIVATION", "message": "No puede desactivarse a sí mismo."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(user)
        return Response(UserSerializer(user).data)

    @extend_schema(tags=["Usuarios"], summary="Invitación masiva de usuarios")
    @action(detail=False, methods=["post"], url_path="bulk-invite")
    @transaction.atomic
    def bulk_invite(self, request):
        rows = request.data.get("users", [])
        default_role = request.data.get("default_role", User.Role.STUDENT)
        created, skipped = [], []

        for row in rows:
            email = (row.get("email") or "").strip().lower()
            if not email or User.objects.filter(email=email).exists():
                skipped.append({"email": email, "reason": "duplicado o inválido"})
                continue
            password = generate_temp_password()
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=row.get("first_name", email.split("@")[0]),
                last_name=row.get("last_name", ""),
                role=row.get("role", default_role),
                job_title=row.get("job_title", ""),
                company_id=request.user.company_id,
            )
            created.append(user)
            get_notifier().send_email(
                to=[email],
                subject="Bienvenido a Capacita IA",
                template="user_invitation",
                context={
                    "user_name": user.get_short_name(),
                    "email": email,
                    "temp_password": password,
                    "company": request.user.company.name if request.user.company else "",
                },
            )

        return Response(
            {
                "created": UserSerializer(created, many=True).data,
                "created_count": len(created),
                "skipped": skipped,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(tags=["Usuarios"], summary="Listar grupos"),
    create=extend_schema(tags=["Usuarios"], summary="Crear grupo"),
)
class UserGroupViewSet(viewsets.ModelViewSet):
    serializer_class = UserGroupSerializer
    permission_classes = [IsAdmin]
    search_fields = ["name"]

    def get_queryset(self):
        return UserGroup.objects.filter(company_id=self.request.user.company_id)

    def perform_create(self, serializer):
        serializer.save(company_id=self.request.user.company_id)

    @extend_schema(tags=["Usuarios"], summary="Listar/actualizar miembros del grupo")
    @action(detail=True, methods=["get", "post", "delete"])
    def members(self, request, pk=None):
        group = self.get_object()

        if request.method == "GET":
            return Response(UserSerializer(group.members.all(), many=True).data)

        serializer = GroupMembersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = User.objects.filter(
            id__in=serializer.validated_data["user_ids"],
            company_id=request.user.company_id,
        )

        if request.method == "POST":
            group.members.add(*users)
        else:
            group.members.remove(*users)

        return Response(UserSerializer(group.members.all(), many=True).data)


class CompanyView(APIView):
    """Datos de la empresa del usuario autenticado."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Usuarios"], responses=CompanySerializer, summary="Mi empresa")
    def get(self, request):
        if request.user.company_id is None:
            return Response({"detail": "El usuario no pertenece a una empresa."}, status=404)
        return Response(CompanySerializer(request.user.company).data)

    @extend_schema(tags=["Usuarios"], request=CompanySerializer, summary="Actualizar mi empresa")
    def patch(self, request):
        if not request.user.is_admin:
            return Response(
                {"error": {"code": "PERMISSION_DENIED", "message": "Se requiere rol de administrador."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CompanySerializer(request.user.company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema_view(list=extend_schema(tags=["Usuarios"], summary="Listar empresas (superadmin)"))
class CompanyViewSet(viewsets.ModelViewSet):
    """Gestión global de tenants. Solo superadministrador."""

    serializer_class = CompanySerializer
    permission_classes = [IsSuperAdmin]
    queryset = Company.objects.all()
    search_fields = ["name", "slug", "tax_id"]
