"""Serializadores del módulo Accounts."""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from ..infrastructure.models import Company, User, UserGroup


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "slug", "tax_id", "logo", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class CompanyBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "slug"]


class UserSerializer(serializers.ModelSerializer):
    company = CompanyBriefSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name", "role",
            "company", "job_title", "avatar", "phone", "language", "timezone",
            "is_active", "last_login", "created_at",
        ]
        read_only_fields = ["id", "last_login", "created_at", "company"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "job_title",
            "phone", "language", "timezone", "is_active", "password",
        ]
        read_only_fields = ["id"]

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return value

    def validate_role(self, value: str) -> str:
        actor = self.context["request"].user
        if value == User.Role.SUPERADMIN and actor.role != User.Role.SUPERADMIN:
            raise serializers.ValidationError(
                "Solo un superadministrador puede crear superadministradores."
            )
        return value

    def validate_password(self, value: str) -> str:
        if value:
            try:
                validate_password(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "role", "job_title", "phone",
            "language", "timezone", "is_active",
        ]

    def validate_role(self, value: str) -> str:
        actor = self.context["request"].user
        if not actor.is_admin:
            raise serializers.ValidationError("No puede modificar el rol.")
        if value == User.Role.SUPERADMIN and actor.role != User.Role.SUPERADMIN:
            raise serializers.ValidationError(
                "Solo un superadministrador puede otorgar ese rol."
            )
        return value


class ProfileSerializer(serializers.ModelSerializer):
    """Perfil propio: el usuario no puede cambiarse el rol ni activarse."""

    company = CompanyBriefSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name", "role",
            "company", "job_title", "avatar", "phone", "language", "timezone",
            "permissions", "last_login",
        ]
        read_only_fields = ["id", "email", "role", "company", "last_login"]

    def get_permissions(self, obj: User) -> dict[str, bool]:
        return {
            "manage_users": obj.is_admin,
            "manage_content": obj.can_manage_content,
            "view_analytics": obj.is_admin,
            "generate_exams": obj.can_manage_content,
        }


class UserGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = UserGroup
        fields = ["id", "name", "description", "member_count", "created_at"]
        read_only_fields = ["id", "created_at"]


class GroupMembersSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


# ── Autenticación ────────────────────────────────────────────


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class CapacitaTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Añade al JWT los claims necesarios para autorizar sin consultar la BD."""

    username_field = "email"

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        token["company_id"] = str(user.company_id) if user.company_id else None
        token["name"] = user.get_full_name()
        return token


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class BulkInviteSerializer(serializers.Serializer):
    """Carga masiva: una fila por usuario."""

    users = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=500)
    default_role = serializers.ChoiceField(
        choices=User.Role.choices, default=User.Role.STUDENT
    )
