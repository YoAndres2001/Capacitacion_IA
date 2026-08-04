from django.urls import path

from .views import (
    AIUsageReportView,
    ExamResultsReportView,
    ExportView,
    MyStatsView,
    OverviewView,
    ProgressReportView,
)

urlpatterns = [
    path("overview", OverviewView.as_view(), name="analytics-overview"),
    path("progress", ProgressReportView.as_view(), name="analytics-progress"),
    path("exam-results", ExamResultsReportView.as_view(), name="analytics-exam-results"),
    path("ai-usage", AIUsageReportView.as_view(), name="analytics-ai-usage"),
    path("export", ExportView.as_view(), name="analytics-export"),
    path("me", MyStatsView.as_view(), name="analytics-me"),
]
