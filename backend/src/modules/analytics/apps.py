from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    name = "src.modules.analytics"
    label = "analytics"
    verbose_name = "Analítica y reportes"
    default_auto_field = "django.db.models.BigAutoField"
