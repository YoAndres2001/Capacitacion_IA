/** Rutas: cursos en los que el estudiante está inscrito y su avance. */

import { ChevronRight, RouteOutlined, School } from '@mui/icons-material';
import {
  Avatar,
  Box,
  Button,
  Card,
  CardActionArea,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { MyTraining, Paginated } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/shared/components';
import { STATUS_LABEL, formatDate, progressValue } from '@/shared/utils/format';

export default function RoutesPage() {
  const navigate = useNavigate();

  const trainings = useQuery({
    queryKey: ['me', 'trainings'],
    queryFn: async () => (await api.get<Paginated<MyTraining>>(endpoints.me.trainings)).data,
  });

  if (trainings.isLoading) return <Loading label="Cargando tus rutas…" />;
  if (trainings.isError) return <ErrorState error={trainings.error} onRetry={trainings.refetch} />;

  const items = [...(trainings.data?.results ?? [])].sort(
    (a, b) => progressValue(b.progress) - progressValue(a.progress),
  );

  return (
    <Box>
      <PageHeader title="Mis rutas" subtitle="Los cursos que estás desarrollando y su avance" />

      {items.length === 0 ? (
        <EmptyState
          icon={<RouteOutlined />}
          title="Todavía no tienes rutas"
          description="Cuando tu educador te invite a un curso aparecerá aquí con su porcentaje de avance."
          action={
            <Button variant="contained" onClick={() => navigate('/academia')}>
              Explorar la academia
            </Button>
          }
        />
      ) : (
        <Stack spacing={1.5}>
          {items.map((item) => (
            <RouteRow
              key={item.id}
              training={item}
              onOpen={() => navigate(`/cursos/${item.training_id}`)}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function RouteRow({ training, onOpen }: { training: MyTraining; onOpen: () => void }) {
  const progress = progressValue(training.progress);
  const completed = training.status === 'COMPLETED';

  return (
    <Card variant="outlined">
      <CardActionArea onClick={onOpen} sx={{ p: 2 }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
        >
          <Avatar
            variant="rounded"
            sx={{ width: 52, height: 52, bgcolor: 'action.hover', color: 'primary.main' }}
          >
            <School />
          </Avatar>

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="h5" noWrap>
              {training.title}
            </Typography>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ mt: 0.5 }}
              flexWrap="wrap"
              useFlexGap
            >
              <Typography variant="caption" color="text.secondary">
                {training.project_name}
              </Typography>
              <Chip
                label={STATUS_LABEL[training.status] ?? training.status}
                size="small"
                color={completed ? 'success' : 'default'}
              />
              {training.due_date && (
                <Typography variant="caption" color="text.secondary">
                  Vence el {formatDate(training.due_date)}
                </Typography>
              )}
            </Stack>
          </Box>

          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            sx={{ width: { xs: '100%', sm: 240, md: 300 }, flexShrink: 0 }}
          >
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, progress))}
              color={completed ? 'success' : 'primary'}
              sx={{ flex: 1, height: 8, borderRadius: 4 }}
            />
            <Typography variant="body2" fontWeight={700} sx={{ minWidth: 44, textAlign: 'right' }}>
              {progress.toFixed(0)}%
            </Typography>
            <ChevronRight fontSize="small" color="disabled" />
          </Stack>
        </Stack>
      </CardActionArea>
    </Card>
  );
}
