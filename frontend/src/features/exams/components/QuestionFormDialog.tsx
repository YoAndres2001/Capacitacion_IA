/**
 * Alta y edición manual de una pregunta.
 *
 * La validación replica `Question.has_valid_answer_key()` del backend: sin
 * clave de respuesta el examen no se puede publicar, y avisar aquí evita que
 * el error aparezca recién al pulsar «Publicar», con el examen ya armado.
 */

import { Add, Delete } from '@mui/icons-material';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Radio,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Question, QuestionType, TrainingLevel } from '@/shared/api/types';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { QUESTION_TYPE_LABEL } from '@/shared/utils/format';

const TYPES: QuestionType[] = [
  'SINGLE_CHOICE',
  'MULTIPLE_CHOICE',
  'TRUE_FALSE',
  'SHORT_ANSWER',
  'OPEN_ENDED',
];

const CLOSED_TYPES: QuestionType[] = ['SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'TRUE_FALSE'];

const TRUE_FALSE_OPTIONS = ['Verdadero', 'Falso'];

type OptionDraft = { text: string; is_correct: boolean };

interface Props {
  open: boolean;
  examId: string;
  /** `null` crea una pregunta nueva. */
  question?: Question | null;
  onClose: () => void;
}

function initialOptions(question: Question | null | undefined): OptionDraft[] {
  if (question?.options?.length) {
    return question.options.map((option) => ({
      text: option.text,
      is_correct: Boolean(option.is_correct),
    }));
  }
  return [
    { text: '', is_correct: false },
    { text: '', is_correct: false },
  ];
}

export function QuestionFormDialog({ open, examId, question, onClose }: Props) {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const editing = Boolean(question);

  const [type, setType] = useState<QuestionType>(question?.type ?? 'SINGLE_CHOICE');
  const [statement, setStatement] = useState(question?.statement ?? '');
  const [level, setLevel] = useState<TrainingLevel>(question?.level ?? 'INTERMEDIATE');
  const [points, setPoints] = useState(Number(question?.points ?? 1));
  const [explanation, setExplanation] = useState(question?.explanation ?? '');
  const [correctText, setCorrectText] = useState(question?.correct_text ?? '');
  const [options, setOptions] = useState<OptionDraft[]>(() => initialOptions(question));

  const isClosed = CLOSED_TYPES.includes(type);
  const isTrueFalse = type === 'TRUE_FALSE';
  // Verdadero/Falso no admite redactar alternativas: son siempre las mismas.
  const shownOptions: OptionDraft[] = isTrueFalse
    ? TRUE_FALSE_OPTIONS.map((text, index) => ({
        text,
        is_correct: options[index]?.is_correct ?? false,
      }))
    : options;

  const correctCount = shownOptions.filter((option) => option.is_correct).length;

  const error = (() => {
    if (statement.trim().length < 5) return 'Escribe el enunciado (mínimo 5 caracteres).';
    if (points <= 0) return 'Los puntos deben ser mayores que cero.';
    if (isClosed) {
      if (!isTrueFalse && shownOptions.some((option) => !option.text.trim()))
        return 'Todas las alternativas necesitan texto.';
      if (!isTrueFalse && shownOptions.length < 2) return 'Agrega al menos dos alternativas.';
      if (type === 'MULTIPLE_CHOICE' && correctCount < 1)
        return 'Marca al menos una alternativa correcta.';
      if (type !== 'MULTIPLE_CHOICE' && correctCount !== 1)
        return 'Marca exactamente una alternativa correcta.';
      return null;
    }
    if (!correctText.trim())
      return type === 'SHORT_ANSWER'
        ? 'Indica la respuesta esperada.'
        : 'Indica los criterios de corrección.';
    return null;
  })();

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        type,
        statement: statement.trim(),
        level,
        points,
        explanation: explanation.trim(),
        // El backend guarda la clave en un sitio u otro según el tipo; enviar
        // ambos vacíos evita arrastrar restos al cambiar el tipo en una edición.
        correct_text: isClosed ? '' : correctText.trim(),
        options: isClosed
          ? shownOptions.map((option) => ({
              text: option.text.trim(),
              is_correct: option.is_correct,
            }))
          : [],
      };
      return question
        ? api.patch(endpoints.questions.detail(question.id), payload)
        : api.post(endpoints.exams.questions(examId), payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['exam', examId] });
      snackbar.success(editing ? 'Pregunta actualizada.' : 'Pregunta agregada.');
      onClose();
    },
    onError: (mutationError) => snackbar.error(errorMessage(mutationError)),
  });

  const setOption = (index: number, patch: Partial<OptionDraft>) =>
    setOptions((current) =>
      current.map((option, position) => (position === index ? { ...option, ...patch } : option)),
    );

  /** En los tipos de una sola respuesta, marcar una desmarca el resto. */
  const markCorrect = (index: number) =>
    setOptions((current) =>
      current.map((option, position) => ({
        ...option,
        is_correct:
          type === 'MULTIPLE_CHOICE'
            ? position === index
              ? !option.is_correct
              : option.is_correct
            : position === index,
      })),
    );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{editing ? 'Editar pregunta' : 'Nueva pregunta'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ mt: 1 }}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                label="Tipo"
                value={type}
                onChange={(event) => setType(event.target.value as QuestionType)}
              >
                {TYPES.map((value) => (
                  <MenuItem key={value} value={value}>
                    {QUESTION_TYPE_LABEL[value]}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <TextField
                select
                label="Nivel"
                value={level}
                onChange={(event) => setLevel(event.target.value as TrainingLevel)}
              >
                <MenuItem value="BEGINNER">Principiante</MenuItem>
                <MenuItem value="INTERMEDIATE">Intermedio</MenuItem>
                <MenuItem value="ADVANCED">Avanzado</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <TextField
                label="Puntos"
                type="number"
                value={points}
                onChange={(event) => setPoints(Number(event.target.value))}
                inputProps={{ min: 0.5, step: 0.5 }}
              />
            </Grid>
          </Grid>

          <TextField
            label="Enunciado"
            multiline
            rows={3}
            value={statement}
            onChange={(event) => setStatement(event.target.value)}
          />

          {isClosed ? (
            <Stack spacing={1}>
              <Typography variant="subtitle2">
                Alternativas
                <Typography component="span" variant="caption" color="text.secondary">
                  {type === 'MULTIPLE_CHOICE'
                    ? ' · marca todas las correctas'
                    : ' · marca la correcta'}
                </Typography>
              </Typography>

              {shownOptions.map((option, index) => (
                <Stack key={index} direction="row" spacing={1} alignItems="center">
                  {type === 'MULTIPLE_CHOICE' ? (
                    <Checkbox
                      checked={option.is_correct}
                      onChange={() => markCorrect(index)}
                      inputProps={{ 'aria-label': `Alternativa ${index + 1} correcta` }}
                    />
                  ) : (
                    <Radio
                      checked={option.is_correct}
                      onChange={() => markCorrect(index)}
                      inputProps={{ 'aria-label': `Alternativa ${index + 1} correcta` }}
                    />
                  )}
                  <TextField
                    value={option.text}
                    disabled={isTrueFalse}
                    placeholder={`Alternativa ${index + 1}`}
                    onChange={(event) => setOption(index, { text: event.target.value })}
                    sx={{ flex: 1 }}
                  />
                  {!isTrueFalse && shownOptions.length > 2 && (
                    <IconButton
                      size="small"
                      color="error"
                      aria-label={`Quitar alternativa ${index + 1}`}
                      onClick={() =>
                        setOptions((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                    >
                      <Delete fontSize="small" />
                    </IconButton>
                  )}
                </Stack>
              ))}

              {!isTrueFalse && (
                <Button
                  size="small"
                  startIcon={<Add />}
                  sx={{ alignSelf: 'flex-start' }}
                  onClick={() =>
                    setOptions((current) => [...current, { text: '', is_correct: false }])
                  }
                >
                  Agregar alternativa
                </Button>
              )}
            </Stack>
          ) : (
            <TextField
              label={
                type === 'SHORT_ANSWER' ? 'Respuesta esperada' : 'Criterios de corrección'
              }
              multiline
              rows={type === 'SHORT_ANSWER' ? 2 : 3}
              value={correctText}
              onChange={(event) => setCorrectText(event.target.value)}
              helperText={
                type === 'SHORT_ANSWER'
                  ? 'La IA compara la respuesta del estudiante con este texto.'
                  : 'Qué debe contener una respuesta correcta; guía la corrección con IA.'
              }
            />
          )}

          <TextField
            label="Explicación (opcional)"
            multiline
            rows={2}
            value={explanation}
            onChange={(event) => setExplanation(event.target.value)}
            helperText="Se le muestra al estudiante junto con el resultado."
          />

          {error && <Alert severity="warning">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={error !== null || save.isPending}
          onClick={() => save.mutate()}
        >
          {editing ? 'Guardar' : 'Agregar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
