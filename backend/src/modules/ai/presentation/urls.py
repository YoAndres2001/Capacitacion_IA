from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgentRunView, AIHealthView, AIUsageView, ChatSessionViewSet, TrainingChatSessionsView

router = DefaultRouter()
router.register("chat-sessions", ChatSessionViewSet, basename="chat-session")

urlpatterns = [
    path(
        "trainings/<uuid:training_id>/chat-sessions",
        TrainingChatSessionsView.as_view(),
        name="training-chat-sessions",
    ),
    path("trainings/<uuid:training_id>/agent/run", AgentRunView.as_view(), name="agent-run"),
    path("ai/usage", AIUsageView.as_view(), name="ai-usage"),
    path("ai/health", AIHealthView.as_view(), name="ai-health"),
    path("", include(router.urls)),
]
