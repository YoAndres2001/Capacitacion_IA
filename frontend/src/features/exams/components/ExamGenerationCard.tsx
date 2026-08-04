/** Tarjeta de avance mientras la IA redacta un examen (CU-13). */

import { AutoAwesome, ErrorOutline } from '@mui/icons-material';
import { Alert, Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { ProgressBar } from '@/shared/components';
import type { ExamGeneration } from '../hooks/useExamGeneration';

const STEP_LABEL: Record<string, string> = {
  queued: 'En cola, esperando al worker de IA',
  material: 'Seleccionando el material del curso',
  questions: 'Redactando preguntas',
  done: 'Guardando el examen',
};

interface Props {
  generation: ExamGeneration;
  onDismiss: () => void;
}

export function ExamGenerationCard({ generation, onDismiss }: Props) {
  const elapsed = useElapsed(generation.startedAt, !generation.failed);

  if (generation.failed) {
    return (
      <Alert
        severity="error"
        icon={<ErrorOutline />}
        sx={{ mb: 2 }}
        action={
          <Button color="inherit" size="small" onClick={onDismiss}>
            Entendido
          </Button>
        }
      >
        <Typography variant="subtitle2">No se pudo generar el examen</Typography>
        <Typography variant="body2">{generation.message}</Typography>
      </Alert>
    );
  }

  return (
    <Card variant="outlined" sx={{ mb: 2, borderColor: 'primary.main' }}>
      <CardContent sx={{ py: 2.5, '&:last-child': { pb: 2.5 } }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <AutoAwesome color="primary" fontSize="small" />
          <Typography variant="subtitle1">Generando evaluación con IA</Typography>
          <Box sx={{ flex: 1 }} />
          {/* El cronómetro es la señal de que la tarea sigue viva: los avisos de
              avance llegan solo al cerrar cada lote, con minutos de diferencia. */}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {elapsed} transcurridos
          </Typography>
        </Stack>

        <ProgressBar
          value={generation.progress}
          label={STEP_LABEL[generation.step] ?? 'Procesando'}
        />

        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          spacing={2}
          sx={{ mt: 1.5 }}
        >
          <Typography variant="caption" color="text.secondary">
            {generation.questions} de {generation.total} preguntas redactadas. En CPU el modelo
            tarda varios minutos por lote; puedes cerrar esta página y volver más tarde.
          </Typography>
          {/* Salida de emergencia: si el worker muriera sin avisar, sin esto el
              botón de generar quedaría bloqueado hasta que caduque el registro. */}
          <Button size="small" color="inherit" onClick={onDismiss} sx={{ flexShrink: 0 }}>
            Dejar de seguir
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

/** Cronómetro `mm:ss` desde el inicio de la generación. */
function useElapsed(startedAt: number, running: boolean): string {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
