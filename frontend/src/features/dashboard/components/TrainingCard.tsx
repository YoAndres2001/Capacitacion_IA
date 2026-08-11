/** Tarjeta de capacitación asignada, compartida por Inicio y Rutas. */

import { CheckCircle, PlayArrow } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import type { MyTraining } from '@/shared/api/types';
import { ProgressBar } from '@/shared/components';
import { LEVEL_LABEL, formatDurationLong, progressValue } from '@/shared/utils/format';

export function TrainingCard({
  training,
  onOpen,
}: {
  training: MyTraining;
  onOpen: () => void;
}) {
  const progress = progressValue(training.progress);
  const completed = training.status === 'COMPLETED';

  return (
    <Card sx={{ height: '100%' }}>
      <CardActionArea onClick={onOpen} sx={{ height: '100%', alignItems: 'stretch' }}>
        <CardContent sx={{ p: { xs: 2, sm: 2.5 }, height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
            <Chip label={training.project_name} size="small" variant="outlined" />
            <Chip label={LEVEL_LABEL[training.level] ?? training.level} size="small" />
          </Stack>

          <Typography variant="h4" gutterBottom>
            {training.title}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              mb: 2,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {training.description || 'Sin descripción.'}
          </Typography>

          <Box sx={{ mt: 'auto' }}>
            <ProgressBar value={progress} color={completed ? 'success' : 'primary'} />
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mt: 1.5 }}
            >
              <Typography variant="caption" color="text.secondary">
                {formatDurationLong(training.estimated_minutes * 60)}
              </Typography>
              <Button
                size="small"
                variant="contained"
                startIcon={completed ? <CheckCircle /> : <PlayArrow />}
                color={completed ? 'success' : 'primary'}
              >
                {completed ? 'Repasar' : progress > 0 ? 'Continuar' : 'Comenzar'}
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
