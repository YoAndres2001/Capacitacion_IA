from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttemptViewSet,
    ExamViewSet,
    MyAttemptsView,
    QuestionViewSet,
    TrainingExamsView,
)

router = DefaultRouter()
router.register("exams", ExamViewSet, basename="exam")
router.register("questions", QuestionViewSet, basename="question")
router.register("attempts", AttemptViewSet, basename="attempt")

urlpatterns = [
    path("me/attempts", MyAttemptsView.as_view(), name="my-attempts"),
    path(
        "trainings/<uuid:training_id>/exams",
        TrainingExamsView.as_view(),
        name="training-exams",
    ),
    path("", include(router.urls)),
]
