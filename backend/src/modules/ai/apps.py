from django.apps import AppConfig


class AIConfig(AppConfig):
    name = "src.modules.ai"
    label = "ai"
    verbose_name = "Inteligencia Artificial"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Registra la comprobación de configuración de IA (GROQ_API_KEY).
        from . import checks  # noqa: F401
