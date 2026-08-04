/** Rendición de un examen: temporizador, guardado parcial y entrega (CU-14). */

import { AccessTime, ArrowBack, Send } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { AttemptDetail, Question } from '@/shared/api/types';
import { ConfirmDialog, ErrorState, Loading } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { QUESTION_TYPE_LABEL } from '@/shared/utils/format';

const AUTOSAVE_MS = 15_000;

interface AnswerState {
  selected: string[];
  text: string;
}

export default function TakeExamPage() {
  const { examId = '' } = useParams();
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const answersRef = useRef(answers);
  answersRef.current = answers;

  // Iniciar (o reanudar) el intento.
  const attempt = useQuery({
    queryKey: ['attempt', 'start', examId],
    queryFn: async () => (await api.post<AttemptDetail>(endpoints.exams.attempts(examId))).data,
    retry: false,
    refetchOnMount: false,
    staleTime: Infinity,
  });

  const attemptId = attempt.data?.id ?? '';

  // Restaurar respuestas guardadas del intento reanudado.
  useEffect(() => {
    if (!attempt.data?.answers) return;
    const restored: Record<string, AnswerState> = {};
    for (const saved of attempt.data.answers) {
      restored[saved.question] = {
        selected: saved.selected_option_ids ?? [],
        text: saved.text_answer ?? '',
      };
    }
    setAnswers(restored);
  }, [attempt.data]);

  const save = useMutation({
    mutationFn: (payload: Record<string, AnswerState>) =>
      api.patch(endpoints.attempts.answers(attemptId), {
        answers: Object.entries(payload).map(([questionId, value]) => ({
          question_id: questionId,
          selected_option_ids: value.selected,
          text_answer: value.text,
        })),
      }),
  });

  const submit = useMutation({
    mutationFn: async () => {
      await save.mutateAsync(answersRef.current);
      return api.post(endpoints.attempts.submit(attemptId));
    },
    onSuccess: () => {
      snackbar.success('Examen entregado. La IA lo está corrigiendo.');
      navigate(`/intentos/${attemptId}`);
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  // Autoguardado periódico.
  useEffect(() => {
    if (!attemptId) return;
    const timer = window.setInterval(() => {
      if (Object.keys(answersRef.current).length > 0) save.mutate(answersRef.current);
    }, AUTOSAVE_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId]);

  // Temporizador.
  useEffect(() => {
    const limit = attempt.data?.time_limit_minutes ?? 0;
    if (!limit || !attempt.data) return;

    const started = new Date(attempt.data.started_at).getTime();
    const deadline = started + limit * 60_000;

    const tick = () => {
      const left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
      setRemaining(left);
      if (left === 0) submit.mutate();
    };

    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt.data]);

  const setAnswer = useCallback((questionId: string, value: Partial<AnswerState>) => {
    setAnswers((previous) => {
      const current = previous[questionId] ?? { selected: [], text: '' };
      return { ...previous, [questionId]: { ...current, ...value } };
    });
  }, []);

  if (attempt.isLoading) return <Loading label="Preparando el examen…" />;
  if (attempt.isError) {
    return (
      <Box sx={{ maxWidth: 640, mx: 'auto', mt: 4 }}>
        <ErrorState error={attempt.error} />
        <Button startIcon={<ArrowBack />} sx={{ mt: 2 }} onClick={() => navigate(-1)}>
          Volver
        </Button>
      </Box>
    );
  }

  const data = attempt.data!;
  const questions = data.questions;
  const answered = questions.filter((question) => isAnswered(answers[question.id])).length;

  return (
    <Box sx={{ maxWidth: 880, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h2">{data.exam_title}</Typography>
          <Typography variant="body2" color="text.secondary">
            Intento {data.number} · {questions.length} preguntas
          </Typography>
        </Box>
        {remaining !== null && (
          <Chip
            icon={<AccessTime />}
            label={formatRemaining(remaining)}
            color={remaining < 300 ? 'error' : 'default'}
            sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}
          />
        )}
      </Stack>

      <Paper sx={{ p: 2, mb: 3, position: 'sticky', top: 72, zIndex: 2 }}>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.75 }}>
          <Typography variant="caption">
            {answered} de {questions.length} respondidas
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {save.isPending ? 'Guardando…' : 'Guardado automático activo'}
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={(answered / Math.max(1, questions.length)) * 100}
          sx={{ height: 6, borderRadius: 3 }}
        />
      </Paper>

      <Stack spacing={2.5}>
        {questions.map((question, index) => (
          <QuestionInput
            key={question.id}
            question={question}
            index={index}
            value={answers[question.id]}
            onChange={(value) => setAnswer(question.id, value)}
          />
        ))}
      </Stack>

      <Alert severity="info" sx={{ mt: 3 }}>
        Al entregar, la IA corregirá el examen y te indicará qué sección repasar en cada pregunta
        incorrecta.
      </Alert>

      <Stack direction="row" justifyContent="flex-end" spacing={1.5} sx={{ mt: 3, mb: 6 }}>
        <Button onClick={() => navigate(-1)}>Salir sin entregar</Button>
        <Button
          variant="contained"
          size="large"
          startIcon={<Send />}
          onClick={() => setConfirmSubmit(true)}
          disabled={submit.isPending}
        >
          Entregar examen
        </Button>
      </Stack>

      <ConfirmDialog
        open={confirmSubmit}
        title="Entregar examen"
        message={
          answered < questions.length
            ? `Tienes ${questions.length - answered} pregunta(s) sin responder. ¿Entregar de todos modos?`
            : '¿Entregar el examen para su corrección?'
        }
        confirmLabel="Entregar"
        loading={submit.isPending}
        onConfirm={() => submit.mutate()}
        onCancel={() => setConfirmSubmit(false)}
      />
    </Box>
  );
}

function QuestionInput({
  question,
  index,
  value,
  onChange,
}: {
  question: Question;
  index: number;
  value?: AnswerState;
  onChange: (value: Partial<AnswerState>) => void;
}) {
  const selected = value?.selected ?? [];

  return (
    <Card variant="outlined">
      <CardContent sx={{ p: 2.5 }}>
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center">
          <Chip label={index + 1} size="small" />
          <Chip label={QUESTION_TYPE_LABEL[question.type]} size="small" variant="outlined" />
          <Chip label={`${question.points} pts`} size="small" variant="outlined" />
        </Stack>

        <Typography variant="subtitle1" sx={{ mb: 2 }}>
          {question.statement}
        </Typography>

        {(question.type === 'SINGLE_CHOICE' || question.type === 'TRUE_FALSE') && (
          <RadioGroup
            value={selected[0] ?? ''}
            onChange={(event) => onChange({ selected: [event.target.value] })}
          >
            {question.options.map((option) => (
              <FormControlLabel
                key={option.id}
                value={option.id}
                control={<Radio />}
                label={option.text}
              />
            ))}
          </RadioGroup>
        )}

        {question.type === 'MULTIPLE_CHOICE' && (
          <Stack>
            {question.options.map((option) => (
              <FormControlLabel
                key={option.id}
                control={
                  <Checkbox
                    checked={selected.includes(option.id)}
                    onChange={(event) =>
                      onChange({
                        selected: event.target.checked
                          ? [...selected, option.id]
                          : selected.filter((id) => id !== option.id),
                      })
                    }
                  />
                }
                label={option.text}
              />
            ))}
          </Stack>
        )}

        {question.type === 'SHORT_ANSWER' && (
          <TextField
            label="Tu respuesta"
            value={value?.text ?? ''}
            onChange={(event) => onChange({ text: event.target.value })}
            placeholder="Respuesta breve"
          />
        )}

        {question.type === 'OPEN_ENDED' && (
          <TextField
            label="Tu respuesta"
            multiline
            rows={5}
            value={value?.text ?? ''}
            onChange={(event) => onChange({ text: event.target.value })}
            placeholder="Desarrolla tu respuesta…"
          />
        )}
      </CardContent>
    </Card>
  );
}

function isAnswered(answer?: AnswerState): boolean {
  if (!answer) return false;
  return answer.selected.length > 0 || answer.text.trim().length > 0;
}

function formatRemaining(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}
