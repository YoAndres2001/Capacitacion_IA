from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "src.modules.accounts"
    label = "accounts"
    verbose_name = "Usuarios y empresas"
    default_auto_field = "django.db.models.BigAutoField"
