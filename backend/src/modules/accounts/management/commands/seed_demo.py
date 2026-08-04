"""
Datos de demostración: empresa, usuarios, proyectos y una capacitación de ejemplo.

Idempotente: se puede ejecutar varias veces sin duplicar nada.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from src.modules.accounts.infrastructure.models import Company, User, UserGroup
from src.modules.projects.infrastructure.models import (
    Project,
    ProjectMember,
    VectorCollection,
)
from src.modules.trainings.infrastructure.models import (
    Enrollment,
    Lesson,
    Module,
    Training,
)

DEMO_PASSWORD = "Demo1234!"

DEMO_USERS = [
    ("admin@demo.cl", "Ana", "Reyes", User.Role.ADMIN, "Jefa de Capacitación"),
    ("instructor@demo.cl", "Bruno", "Salazar", User.Role.INSTRUCTOR, "Consultor Senior ERP"),
    ("estudiante@demo.cl", "Carla", "Muñoz", User.Role.STUDENT, "Analista de Bodega"),
    ("estudiante2@demo.cl", "Diego", "Fuentes", User.Role.STUDENT, "Jefe de Bodega"),
]

DEMO_PROJECTS = [
    ("ERP Sistemas Expertos", "ERP", "Sistema de gestión empresarial", "#1976d2", "account_balance"),
    ("WMS Bodegas", "WMS", "Gestión de almacenes y despacho", "#2e7d32", "warehouse"),
    ("CRM Comercial", "CRM", "Gestión de clientes y oportunidades", "#ed6c02", "handshake"),
    ("Portal Clientes", "PORTAL", "Autoservicio para clientes finales", "#9c27b0", "public"),
]

DEMO_TRAINING = {
    "title": "Inventario — Nivel Básico",
    "description": (
        "Introducción al módulo de inventario: recepción, inventario cíclico, "
        "ajustes y reportes. Incluye ejercicios prácticos."
    ),
    "modules": [
        (
            "Fundamentos",
            [
                ("Introducción al módulo de inventario", Lesson.Type.VIDEO),
                ("Conceptos y vocabulario", Lesson.Type.DOCUMENT),
            ],
        ),
        (
            "Operación diaria",
            [
                ("Recepción de mercadería", Lesson.Type.VIDEO),
                ("Inventario cíclico paso a paso", Lesson.Type.VIDEO),
                ("Ajustes y mermas", Lesson.Type.VIDEO),
            ],
        ),
        (
            "Reportes",
            [
                ("Reportes de stock y valorización", Lesson.Type.VIDEO),
                ("Manual de referencia", Lesson.Type.DOCUMENT),
            ],
        ),
    ],
}


class Command(BaseCommand):
    help = "Crea datos de demostración (idempotente)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="No hace nada si ya existen empresas.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if options["if_empty"] and Company.objects.exists():
            self.stdout.write("Ya existen datos; no se carga la demostración.")
            return

        company = self._company()
        users = self._users(company)
        projects = self._projects(company, users["instructor@demo.cl"])
        training = self._training(projects[0], users["instructor@demo.cl"])
        self._enroll(training, [users["estudiante@demo.cl"], users["estudiante2@demo.cl"]], users["admin@demo.cl"])

        self.stdout.write(self.style.SUCCESS("\n Datos de demostración listos.\n"))
        self.stdout.write(f"  Empresa:  {company.name}")
        self.stdout.write(f"  Proyectos: {', '.join(p.code for p in projects)}")
        self.stdout.write(f"  Capacitación: {training.title}\n")
        self.stdout.write("  Usuarios (contraseña: " + DEMO_PASSWORD + ")")
        for email, first, _last, role, _title in DEMO_USERS:
            self.stdout.write(f"    · {email:<24} {role:<12} {first}")
        self.stdout.write("")

    # ── Pasos ────────────────────────────────────────────────
    def _company(self) -> Company:
        company, created = Company.objects.get_or_create(
            slug="demo",
            defaults={"name": "Sistemas Expertos (Demo)", "tax_id": "76.123.456-7"},
        )
        self._report("Empresa", company.name, created)
        return company

    def _users(self, company: Company) -> dict[str, User]:
        result: dict[str, User] = {}
        for email, first_name, last_name, role, job_title in DEMO_USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(
                    email=email,
                    password=DEMO_PASSWORD,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    job_title=job_title,
                    company=company,
                )
                self._report("Usuario", email, True)
            result[email] = user

        group, created = UserGroup.objects.get_or_create(
            company=company, name="Operaciones Bodega", defaults={"description": "Equipo de bodega"}
        )
        group.members.add(result["estudiante@demo.cl"], result["estudiante2@demo.cl"])
        self._report("Grupo", group.name, created)

        # Superusuario para el admin de Django.
        if not User.objects.filter(email="super@demo.cl").exists():
            User.objects.create_superuser(
                email="super@demo.cl",
                password=DEMO_PASSWORD,
                first_name="Super",
                last_name="Admin",
                company=company,
            )
            self._report("Superusuario", "super@demo.cl", True)

        return result

    def _projects(self, company: Company, owner: User) -> list[Project]:
        projects: list[Project] = []
        for name, code, description, color, icon in DEMO_PROJECTS:
            project, created = Project.objects.get_or_create(
                company=company,
                slug=slugify(name),
                defaults={
                    "name": name,
                    "code": code,
                    "description": description,
                    "color": color,
                    "icon": icon,
                },
            )
            VectorCollection.objects.get_or_create(
                project=project, defaults={"index_path": f"{company.slug}/{project.id}"}
            )
            ProjectMember.objects.get_or_create(
                project=project, user=owner, defaults={"role": ProjectMember.Role.OWNER}
            )
            projects.append(project)
            self._report("Proyecto", name, created)
        return projects

    def _training(self, project: Project, instructor: User) -> Training:
        training, created = Training.objects.get_or_create(
            project=project,
            slug=slugify(DEMO_TRAINING["title"]),
            defaults={
                "title": DEMO_TRAINING["title"],
                "description": DEMO_TRAINING["description"],
                "level": Training.Level.BEGINNER,
                "estimated_minutes": 120,
                "created_by": instructor,
            },
        )
        self._report("Capacitación", training.title, created)

        if created or not training.modules.exists():
            for module_order, (module_title, lessons) in enumerate(DEMO_TRAINING["modules"]):
                module = Module.objects.create(
                    training=training, title=module_title, order=module_order
                )
                for lesson_order, (lesson_title, lesson_type) in enumerate(lessons):
                    Lesson.objects.create(
                        module=module,
                        title=lesson_title,
                        type=lesson_type,
                        order=lesson_order,
                        duration_seconds=900 if lesson_type == Lesson.Type.VIDEO else 0,
                    )
            self.stdout.write(
                "     La capacitación quedó en BORRADOR: suba material para poder publicarla."
            )
        return training

    def _enroll(self, training: Training, students: list[User], assigned_by: User) -> None:
        for student in students:
            _, created = Enrollment.objects.get_or_create(
                user=student, training=training, defaults={"assigned_by": assigned_by}
            )
            self._report("Inscripción", f"{student.email} → {training.title}", created)

    def _report(self, kind: str, name: str, created: bool) -> None:
        prefix = self.style.SUCCESS("  creado ") if created else "  existe "
        self.stdout.write(f"{prefix} {kind}: {name}")
