/** Alta y edición manual de un examen: solo su configuración, no las preguntas. */

import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Exam } from '@/shared/api/types';
import { useSnackbar } from '@/shared/components/SnackbarProvider';

interface Props {
  open: boolean;
  /** Obligatorio al crear; al editar se toma el del examen. */
  trainingId?: string;
  /** `null` crea un examen nuevo. */
  exam?: Exam | null;
  onClose: () => void;
  onSaved?: (exam: Exam) => void;
}

const DEFAULTS = {
  title: '',
  description: '',
  passing_score: 70,
  max_attempts: 3,
  time_limit_minutes: 0,
  min_progress_required: 0,
  score_policy: 'BEST' as Exam['score_policy'],
  shuffle_questions: false,
};

export function ExamFormDialog({ open, trainingId, exam, onClose, onSaved }: Props) {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const editing = Boolean(exam);

  const [values, setValues] = useState(() =>
    exam
      ? {
          title: exam.title,
          description: exam.description,
          passing_score: exam.passing_score,
          max_attempts: exam.max_attempts,
          time_limit_minutes: exam.time_limit_minutes,
          min_progress_required: exam.min_progress_required,
          score_policy: exam.score_policy,
          shuffle_questions: exam.shuffle_questions,
        }
      : DEFAULTS,
  );

  const set = <K extends keyof typeof values>(key: K, value: (typeof values)[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  const save = useMutation({
    mutationFn: async () => {
      const payload = { ...values, title: values.title.trim() };
      const { data } = exam
        ? await api.patch<Exam>(endpoints.exams.detail(exam.id), payload)
        : await api.post<Exam>(endpoints.exams.list, { ...payload, training: trainingId });
      return data;
    },
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ['training', data.training, 'exams'] });
      if (exam) await queryClient.invalidateQueries({ queryKey: ['exam', exam.id] });
      snackbar.success(editing ? 'Examen actualizado.' : 'Examen creado en borrador.');
      onSaved?.(data);
      onClose();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{editing ? 'Editar examen' : 'Nueva evaluación manual'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ mt: 1 }}>
          <TextField
            label="Título"
            autoFocus
            placeholder="Evaluación final"
            value={values.title}
            onChange={(event) => set('title', event.target.value)}
          />
          <TextField
            label="Descripción"
            multiline
            rows={2}
            value={values.description}
            onChange={(event) => set('description', event.target.value)}
          />

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Nota mínima de aprobación (%)"
                type="number"
                value={values.passing_score}
                onChange={(event) => set('passing_score', Number(event.target.value))}
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Intentos permitidos"
                type="number"
                value={values.max_attempts}
                onChange={(event) => set('max_attempts', Number(event.target.value))}
                inputProps={{ min: 1, max: 10 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Tiempo límite (min, 0 = sin límite)"
                type="number"
                value={values.time_limit_minutes}
                onChange={(event) => set('time_limit_minutes', Number(event.target.value))}
                inputProps={{ min: 0, max: 480 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Avance mínimo del curso (%)"
                type="number"
                value={values.min_progress_required}
                onChange={(event) => set('min_progress_required', Number(event.target.value))}
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                label="Nota que cuenta"
                value={values.score_policy}
                onChange={(event) =>
                  set('score_policy', event.target.value as Exam['score_policy'])
                }
              >
                <MenuItem value="BEST">La mejor</MenuItem>
                <MenuItem value="LAST">La última</MenuItem>
                <MenuItem value="AVERAGE">El promedio</MenuItem>
              </TextField>
            </Grid>
          </Grid>

          <FormControlLabel
            control={
              <Switch
                checked={values.shuffle_questions}
                onChange={(event) => set('shuffle_questions', event.target.checked)}
              />
            }
            label="Barajar el orden de las preguntas en cada intento"
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={values.title.trim().length < 3 || save.isPending}
          onClick={() => save.mutate()}
        >
          {editing ? 'Guardar' : 'Crear'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
