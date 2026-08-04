from __future__ import annotations

from rest_framework import serializers

from ..infrastructure.models import Answer, Attempt, Exam, Question, QuestionOption


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ["id", "text", "is_correct", "order", "feedback"]


class QuestionOptionPublicSerializer(serializers.ModelSerializer):
    """Versión para el estudiante: **sin** la clave de respuesta."""

    class Meta:
        model = QuestionOption
        fields = ["id", "text", "order"]


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)
    source_material_title = serializers.CharField(
        source="source_material.original_filename", read_only=True, default=""
    )

    class Meta:
        model = Question
        fields = [
            "id", "exam", "type", "statement", "level", "points", "order",
            "explanation", "correct_text", "rubric", "options",
            "source_material", "source_material_title", "source_start_time",
            "source_page", "generated_by_ai",
        ]
        read_only_fields = ["id", "generated_by_ai"]
        extra_kwargs = {"exam": {"required": False}}

    def create(self, validated_data: dict) -> Question:
        options = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        QuestionOption.objects.bulk_create(
            [
                QuestionOption(question=question, order=index, **option)
                for index, option in enumerate(options)
            ]
        )
        return question

    def update(self, instance: Question, validated_data: dict) -> Question:
        options = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if options is not None:
            instance.options.all().delete()
            QuestionOption.objects.bulk_create(
                [
                    QuestionOption(question=instance, order=index, **option)
                    for index, option in enumerate(options)
                ]
            )
        return instance


class QuestionPublicSerializer(serializers.ModelSerializer):
    """Lo que ve el estudiante mientras rinde: sin respuestas ni explicaciones."""

    options = QuestionOptionPublicSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ["id", "type", "statement", "level", "points", "order", "options"]


class ExamSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="questions.count", read_only=True)
    total_points = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    training_title = serializers.CharField(source="training.title", read_only=True)
    can_edit_questions = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            "id", "training", "training_title", "title", "description", "status",
            "passing_score", "max_attempts", "time_limit_minutes",
            "min_progress_required", "score_policy", "shuffle_questions",
            "generated_by_ai", "generation_model", "question_count",
            "total_points", "can_edit_questions", "published_at", "created_at",
        ]
        read_only_fields = [
            "id", "generated_by_ai", "generation_model", "published_at", "created_at"
        ]

    def get_can_edit_questions(self, obj: Exam) -> bool:
        return obj.can_edit_questions()


class ExamDetailSerializer(ExamSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta(ExamSerializer.Meta):
        fields = [*ExamSerializer.Meta.fields, "questions"]


class ExamGenerateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    num_questions = serializers.IntegerField(min_value=3, max_value=40, default=10)
    level = serializers.ChoiceField(
        choices=Question.Level.choices, default=Question.Level.INTERMEDIATE
    )
    distribution = serializers.DictField(
        child=serializers.IntegerField(min_value=0), required=False
    )
    passing_score = serializers.IntegerField(min_value=0, max_value=100, default=70)
    max_attempts = serializers.IntegerField(min_value=1, max_value=10, default=3)
    time_limit_minutes = serializers.IntegerField(min_value=0, max_value=480, default=0)

    def validate_distribution(self, value: dict) -> dict:
        valid = set(Question.Type.values)
        invalid = set(value) - valid
        if invalid:
            raise serializers.ValidationError(
                f"Tipos no válidos: {', '.join(sorted(invalid))}. Válidos: {', '.join(sorted(valid))}."
            )
        return value


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = [
            "id", "question", "selected_option_ids", "text_answer",
            "points_awarded", "is_correct", "feedback", "review_hint",
            "grading_method", "needs_manual_review",
        ]
        read_only_fields = [
            "id", "points_awarded", "is_correct", "feedback",
            "review_hint", "grading_method", "needs_manual_review",
        ]


class AnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_option_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    text_answer = serializers.CharField(required=False, allow_blank=True, default="")


class SaveAnswersSerializer(serializers.Serializer):
    answers = AnswerInputSerializer(many=True)


class AttemptSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    training_id = serializers.UUIDField(source="exam.training_id", read_only=True)
    percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = Attempt
        fields = [
            "id", "exam", "exam_title", "training_id", "number", "status",
            "score", "max_score", "percentage", "passed", "ai_feedback",
            "started_at", "submitted_at", "graded_at",
        ]
        read_only_fields = fields


class AttemptDetailSerializer(AttemptSerializer):
    """Durante el intento se entregan las preguntas SIN la clave de respuesta."""

    questions = serializers.SerializerMethodField()
    answers = AnswerSerializer(many=True, read_only=True)
    time_limit_minutes = serializers.IntegerField(source="exam.time_limit_minutes", read_only=True)

    class Meta(AttemptSerializer.Meta):
        fields = [*AttemptSerializer.Meta.fields, "questions", "answers", "time_limit_minutes"]

    def get_questions(self, obj: Attempt):
        questions = obj.exam.questions.prefetch_related("options")
        return QuestionPublicSerializer(questions, many=True).data


class AttemptResultSerializer(AttemptSerializer):
    """Tras la corrección: respuestas correctas, explicación y qué repasar."""

    results = serializers.SerializerMethodField()

    class Meta(AttemptSerializer.Meta):
        fields = [*AttemptSerializer.Meta.fields, "results"]

    def get_results(self, obj: Attempt):
        answers = {
            str(answer.question_id): answer
            for answer in obj.answers.select_related("question")
        }
        output = []
        for question in obj.exam.questions.prefetch_related("options"):
            answer = answers.get(str(question.id))
            output.append(
                {
                    "question_id": str(question.id),
                    "statement": question.statement,
                    "type": question.type,
                    "points": float(question.points),
                    "points_awarded": float(answer.points_awarded) if answer else 0.0,
                    "is_correct": bool(answer and answer.is_correct),
                    "your_answer": {
                        "selected_option_ids": answer.selected_option_ids if answer else [],
                        "text": answer.text_answer if answer else "",
                    },
                    "correct_options": [
                        {"id": str(option.id), "text": option.text}
                        for option in question.options.all()
                        if option.is_correct
                    ],
                    "correct_text": question.correct_text,
                    "explanation": question.explanation,
                    "feedback": answer.feedback if answer else "No respondida.",
                    "review_hint": answer.review_hint if answer else question.review_hint(),
                    "source": {
                        "material_id": str(question.source_material_id)
                        if question.source_material_id
                        else None,
                        "start_time": question.source_start_time,
                        "page": question.source_page,
                    },
                }
            )
        return output


class ExamResultsSerializer(serializers.Serializer):
    """Agregados para el administrador (RF-072)."""

    attempts = serializers.IntegerField()
    graded = serializers.IntegerField()
    passed = serializers.IntegerField()
    pass_rate = serializers.FloatField()
    average_score = serializers.FloatField()
    distribution = serializers.DictField(child=serializers.IntegerField())
    hardest_questions = serializers.ListField(child=serializers.DictField())
