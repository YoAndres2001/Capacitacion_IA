from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EnrollmentDetailView,
    LessonViewSet,
    MaterialViewSet,
    ModuleViewSet,
    MyTrainingDetailView,
    MyTrainingsView,
    NoteDetailView,
    TrainingViewSet,
    UploadChunkView,
    serve_protected_media,
)

router = DefaultRouter()
router.register("trainings", TrainingViewSet, basename="training")
router.register("modules", ModuleViewSet, basename="module")
router.register("lessons", LessonViewSet, basename="lesson")
router.register("materials", MaterialViewSet, basename="material")

urlpatterns = [
    path("me/trainings", MyTrainingsView.as_view(), name="my-trainings"),
    path("me/trainings/<uuid:training_id>", MyTrainingDetailView.as_view(), name="my-training-detail"),
    path("notes/<uuid:note_id>", NoteDetailView.as_view(), name="note-detail"),
    path("enrollments/<uuid:enrollment_id>", EnrollmentDetailView.as_view(), name="enrollment-detail"),
    path("materials/uploads/<uuid:upload_id>/chunk", UploadChunkView.as_view(), name="upload-chunk"),
    path(
        "materials/uploads/<uuid:upload_id>/complete",
        UploadChunkView.as_view(),
        name="upload-complete",
    ),
    # `path:` y no `str:` porque el token firmado incluye la ruta relativa del
    # archivo y, por tanto, barras.
    path("media/<path:token>", serve_protected_media, name="protected-media"),
    path("", include(router.urls)),
]
