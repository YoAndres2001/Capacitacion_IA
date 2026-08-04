"""Vistas de autenticación (`/api/v1/auth/...`)."""

from __future__ import annotations

import secrets

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from src.shared.container import get_notifier

from ..application.use_cases.authenticate_user import (
    AuthenticateInput,
    AuthenticateUserUseCase,
)
from ..application.use_cases.manage_password import (
    ChangePasswordInput,
    ChangePasswordUseCase,
    ConfirmPasswordResetUseCase,
    ConfirmResetInput,
    RequestPasswordResetUseCase,
    RequestResetInput,
)
from ..infrastructure.models import AuditLog
from .serializers import (
    CapacitaTokenObtainPairSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
)


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LoginView(APIView):
    """CU-01 · Emite el par de tokens JWT."""

    permission_classes = [AllowAny]
    throttle_scope = "login"

    @extend_schema(
        tags=["Auth"],
        request=LoginSerializer,
        responses={200: OpenApiResponse(description="access, refresh y perfil del usuario")},
        summary="Iniciar sesión",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthenticateUserUseCase().execute(
            AuthenticateInput(
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        )

        refresh = CapacitaTokenObtainPairSerializer.get_token(result.user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": ProfileSerializer(result.user).data,
            }
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Auth"], summary="Renovar el access token")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Invalida el refresh token (blacklist)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Auth"], summary="Cerrar sesión", request=None)
    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:  # token ya inválido: el resultado es el mismo
                pass

        AuditLog.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            action=AuditLog.Action.LOGOUT,
            entity_type="User",
            entity_id=request.user.id,
            ip_address=_client_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Perfil del usuario autenticado."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Auth"], responses=ProfileSerializer, summary="Mi perfil")
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    @extend_schema(
        tags=["Auth"], request=ProfileSerializer, responses=ProfileSerializer,
        summary="Actualizar mi perfil",
    )
    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordResetRequestView(APIView):
    """RF-007 · Solicita el enlace de recuperación. Siempre responde 202."""

    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(
        tags=["Auth"],
        request=PasswordResetRequestSerializer,
        responses={202: OpenApiResponse(description="Solicitud recibida")},
        summary="Solicitar recuperación de contraseña",
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        RequestPasswordResetUseCase(notifier=get_notifier()).execute(
            RequestResetInput(
                email=serializer.validated_data["email"], ip_address=_client_ip(request)
            )
        )
        # Respuesta constante: no revela si el correo existe.
        return Response(
            {"detail": "Si el correo está registrado, recibirá un enlace de recuperación."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(
        tags=["Auth"],
        request=PasswordResetConfirmSerializer,
        responses={204: None},
        summary="Confirmar nueva contraseña",
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ConfirmPasswordResetUseCase().execute(
            ConfirmResetInput(
                token=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"], request=ChangePasswordSerializer, responses={204: None},
        summary="Cambiar mi contraseña",
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ChangePasswordUseCase().execute(
            ChangePasswordInput(
                user=request.user,
                current_password=serializer.validated_data["current_password"],
                new_password=serializer.validated_data["new_password"],
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def generate_temp_password() -> str:
    """Contraseña temporal para usuarios creados por el administrador."""
    return secrets.token_urlsafe(12)
