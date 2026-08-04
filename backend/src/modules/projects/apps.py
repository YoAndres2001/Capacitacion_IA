from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = "src.modules.projects"
    label = "projects"
    verbose_name = "Proyectos y aplicaciones"
    default_auto_field = "django.db.models.BigAutoField"
