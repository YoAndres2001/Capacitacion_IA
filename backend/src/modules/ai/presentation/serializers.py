from __future__ import annotations

from rest_framework import serializers

from ..infrastructure.models import (
    AIUsageLog,
    Chapter,
    ChatMessage,
    ChatSession,
    Chunk,
    Concept,
    Faq,
    MessageCitation,
    Transcript,
    TranscriptSegment,
)


class TranscriptSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSegment
        fields = ["index", "start_time", "end_time", "text"]


class TranscriptSerializer(serializers.ModelSerializer):
    segments = TranscriptSegmentSerializer(many=True, read_only=True)

    class Meta:
        model = Transcript
        fields = ["id", "language", "model", "confidence", "full_text", "segments"]


class ChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = [
            "id", "order", "title", "summary",
            "start_time", "end_time", "start_page", "end_page",
        ]
        read_only_fields = ["id", "order"]


class ConceptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Concept
        fields = ["id", "name", "definition", "relevance", "first_mention_time", "page"]


class FaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faq
        fields = ["id", "question", "answer", "order"]


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = [
            "id", "index", "content", "token_count", "start_time",
            "end_time", "page", "heading", "embedded", "embedding_model",
        ]


class CitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageCitation
        fields = ["id", "chunk", "material", "label", "start_time", "page", "score"]


class ChatMessageSerializer(serializers.ModelSerializer):
    citations = CitationSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = [
            "id", "role", "content", "grounded", "citations",
            "prompt_tokens", "completion_tokens", "latency_ms",
            "model", "feedback", "created_at",
        ]
        read_only_fields = fields


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "training", "title", "message_count", "last_message_at", "created_at"]
        read_only_fields = ["id", "last_message_at", "created_at"]


class AskSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000)
    level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "advanced"], default="intermediate", required=False
    )


class AgentRunSerializer(serializers.Serializer):
    instruction = serializers.CharField(max_length=2000)
    level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "advanced"], default="intermediate", required=False
    )
    session_id = serializers.UUIDField(required=False, allow_null=True)


class FeedbackSerializer(serializers.Serializer):
    feedback = serializers.ChoiceField(choices=[1, -1])


class AIUsageSerializer(serializers.ModelSerializer):
    total_tokens = serializers.IntegerField(read_only=True)

    class Meta:
        model = AIUsageLog
        fields = [
            "id", "purpose", "provider", "model", "prompt_tokens",
            "completion_tokens", "total_tokens", "cost_usd",
            "latency_ms", "success", "created_at",
        ]
