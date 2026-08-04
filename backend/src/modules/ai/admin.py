from django.contrib import admin

from .infrastructure.models import (
    AIUsageLog,
    Chapter,
    ChatMessage,
    ChatSession,
    Chunk,
    Concept,
    Faq,
    Transcript,
)


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("material", "language", "model", "confidence")
    search_fields = ("full_text",)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "material", "order", "start_time", "end_time")
    list_filter = ("material__type",)


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("name", "material", "relevance")
    search_fields = ("name", "definition")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("material", "index", "token_count", "start_time", "page", "embedded")
    list_filter = ("embedded", "embedding_model")
    search_fields = ("content",)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "training", "last_message_at")
    list_filter = ("training",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "grounded", "model", "created_at")
    list_filter = ("role", "grounded", "needs_review")
    search_fields = ("content",)


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "purpose", "provider", "model",
        "prompt_tokens", "completion_tokens", "cost_usd", "success",
    )
    list_filter = ("purpose", "provider", "success")
    date_hierarchy = "created_at"


admin.site.register(Faq)
