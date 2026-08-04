/** Generación de un examen con IA (CU-13). El resultado nace en borrador. */

import { AutoAwesome } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import { useSnackbar } from '@/shared/components/SnackbarProvider';

const TYPES = [
  { key: 'SINGLE_CHOICE', label: 'Selección única' },
  { key: 'TRUE_FALSE', label: 'Verdadero / Falso' },
  { key: 'SHORT_ANSWER', label: 'Respuesta corta' },
  { key: 'OPEN_ENDED', label: 'Pregunta abierta' },
] as const;

interface Props {
  open: boolean;
  trainingId: string;
  onClose: () => void;
  onGenerated: () => void;
}

export function ExamGeneratorDialog({ open, trainingId, onClose, onGenerated }: Props) {
  const snackbar = useSnackbar();
  const [title, setTitle] = useState('');
  const [level, setLevel] = useState('INTERMEDIATE');
  const [passingScore, setPassingScore] = useState(70);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [timeLimit, setTimeLimit] = useState(0);
  const [distribution, setDistribution] = useState<Record<string, number>>({
    SINGLE_CHOICE: 5,
    TRUE_FALSE: 2,
    SHORT_ANSWER: 2,
    OPEN_ENDED: 1,
  });

  const total = Object.values(distribution).reduce((sum, value) => sum + value, 0);

  const generate = useMutation({
    mutationFn: () =>
      api.post(endpoints.trainings.generateExam(trainingId), {
        title: title || undefined,
        num_questions: total,
        level,
        distribution,
        passing_score: passingScore,
        max_attempts: maxAttempts,
        time_limit_minutes: timeLimit,
      }),
    onSuccess: () => {
      snackbar.success(
        'Generación en curso. El examen aparecerá en borrador cuando la IA termine.',
      );
      onGenerated();
      onClose();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoAwesome color="primary" />
          Generar evaluación con IA
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2.5 }}>
          Las preguntas se construyen exclusivamente con el material procesado del curso, cubriendo
          todos sus capítulos. El examen queda en <strong>borrador</strong> para que lo revises
          antes de publicarlo.
        </Alert>

        <Stack spacing={2.5}>
          <TextField
            label="Título del examen"
            placeholder="Evaluación final"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Distribución de preguntas ({total} en total)
            </Typography>
            <Stack spacing={1.5} sx={{ mt: 1 }}>
              {TYPES.map((type) => (
                <Stack key={type.key} direction="row" alignItems="center" spacing={2}>
                  <Typography variant="body2" sx={{ minWidth: 150 }}>
                    {type.label}
                  </Typography>
                  <Slider
                    value={distribution[type.key] ?? 0}
                    onChange={(_, value) =>
                      setDistribution((previous) => ({ ...previous, [type.key]: value as number }))
                    }
                    min={0}
                    max={15}
                    step={1}
                    marks
                    valueLabelDisplay="auto"
                    sx={{ flex: 1 }}
                  />
                  <Typography variant="body2" fontWeight={700} sx={{ minWidth: 24 }}>
                    {distribution[type.key] ?? 0}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </Box>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                label="Nivel"
                value={level}
                onChange={(event) => setLevel(event.target.value)}
              >
                <MenuItem value="BEGINNER">Principiante</MenuItem>
                <MenuItem value="INTERMEDIATE">Intermedio</MenuItem>
                <MenuItem value="ADVANCED">Avanzado</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Nota mínima de aprobación (%)"
                type="number"
                value={passingScore}
                onChange={(event) => setPassingScore(Number(event.target.value))}
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Intentos permitidos"
                type="number"
                value={maxAttempts}
                onChange={(event) => setMaxAttempts(Number(event.target.value))}
                inputProps={{ min: 1, max: 10 }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label="Tiempo límite (min, 0 = sin límite)"
                type="number"
                value={timeLimit}
                onChange={(event) => setTimeLimit(Number(event.target.value))}
                inputProps={{ min: 0, max: 480 }}
              />
            </Grid>
          </Grid>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          startIcon={<AutoAwesome />}
          disabled={total < 3 || total > 40 || generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? 'Generando…' : `Generar ${total} preguntas`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
