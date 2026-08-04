from django.contrib import admin

from .infrastructure.models import Answer, Attempt, Exam, Question, QuestionOption


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    show_change_link = True
    fields = ("type", "statement", "level", "points", "order", "explanation")


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title", "training", "status", "passing_score",
        "max_attempts", "generated_by_ai", "published_at",
    )
    list_filter = ("status", "generated_by_ai", "training__project")
    search_fields = ("title",)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("statement", "exam", "type", "level", "points", "generated_by_ai")
    list_filter = ("type", "level", "generated_by_ai")
    search_fields = ("statement",)
    inlines = [QuestionOptionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "number", "status", "score", "passed", "submitted_at")
    list_filter = ("status", "passed")
    search_fields = ("user__email", "exam__title")
    readonly_fields = ("score", "max_score", "passed", "graded_at")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "points_awarded", "grading_method")
    list_filter = ("is_correct", "grading_method", "needs_manual_review")
