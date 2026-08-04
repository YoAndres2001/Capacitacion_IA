import { AutoStories, CheckCircle, PlayArrow, Quiz, School } from '@mui/icons-material';
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
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Attempt, MyStats, MyTraining, Paginated } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader, ProgressBar, StatCard } from '@/shared/components';
import { LEVEL_LABEL, formatDate, formatDurationLong, progressValue } from '@/shared/utils/format';

export default function StudentDashboard() {
  const navigate = useNavigate();

  const trainings = useQuery({
    queryKey: ['me', 'trainings'],
    queryFn: async () =>
      (await api.get<Paginated<MyTraining>>(endpoints.me.trainings)).data,
  });

  const stats = useQuery({
    queryKey: ['me', 'stats'],
    queryFn: async () => (await api.get<MyStats>(endpoints.me.stats)).data,
  });

  const attempts = useQuery({
    queryKey: ['me', 'attempts'],
    queryFn: async () => (await api.get<Paginated<Attempt>>(endpoints.me.attempts)).data,
  });

  if (trainings.isLoading) return <Loading label="Cargando tus cursos…" />;
  if (trainings.isError) return <ErrorState error={trainings.error} onRetry={trainings.refetch} />;

  const items = trainings.data?.results ?? [];
  const pending = items.filter((item) => item.status !== 'COMPLETED');
  const completed = items.filter((item) => item.status === 'COMPLETED');

  return (
    <Box>
      <PageHeader title="Mis capacitaciones" subtitle="Continúa donde quedaste" />

      {stats.data && (
        <Grid container spacing={2.5} sx={{ mb: 4 }}>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="Cursos asignados" value={stats.data.trainings.assigned} icon={<School />} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Completados"
              value={stats.data.trainings.completed}
              icon={<CheckCircle />}
              color="success.main"
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Exámenes aprobados"
              value={`${stats.data.exams.passed}/${stats.data.exams.taken}`}
              icon={<Quiz />}
              color="secondary.main"
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Preguntas a la IA"
              value={stats.data.ai.questions_asked}
              icon={<AutoStories />}
              color="info.main"
            />
          </Grid>
        </Grid>
      )}

      {items.length === 0 ? (
        <EmptyState
          icon={<School />}
          title="Aún no tienes capacitaciones asignadas"
          description="Cuando tu administrador te asigne un curso aparecerá aquí."
        />
      ) : (
        <>
          {pending.length > 0 && (
            <>
              <Typography variant="h3" sx={{ mb: 2 }}>
                En curso
              </Typography>
              <Grid container spacing={2.5} sx={{ mb: 4 }}>
                {pending.map((item) => (
                  <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={item.id}>
                    <TrainingCard training={item} onOpen={() => navigate(`/cursos/${item.training_id}`)} />
                  </Grid>
                ))}
              </Grid>
            </>
          )}

          {completed.length > 0 && (
            <>
              <Typography variant="h3" sx={{ mb: 2 }}>
                Completadas
              </Typography>
              <Grid container spacing={2.5}>
                {completed.map((item) => (
                  <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={item.id}>
                    <TrainingCard training={item} onOpen={() => navigate(`/cursos/${item.training_id}`)} />
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </>
      )}

      {(attempts.data?.results?.length ?? 0) > 0 && (
        <Box sx={{ mt: 5 }}>
          <Typography variant="h3" sx={{ mb: 2 }}>
            Mis evaluaciones
          </Typography>
          <Stack spacing={1.5}>
            {attempts.data!.results.slice(0, 6).map((attempt) => (
              <Card key={attempt.id} variant="outlined">
                <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    alignItems={{ sm: 'center' }}
                    justifyContent="space-between"
                    spacing={1.5}
                  >
                    <Box>
                      <Typography variant="subtitle2">{attempt.exam_title}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Intento {attempt.number} · {formatDate(attempt.graded_at ?? attempt.started_at)}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1.5} alignItems="center">
                      {attempt.status === 'GRADED' ? (
                        <>
                          <Chip
                            label={attempt.passed ? 'Aprobado' : 'Reprobado'}
                            color={attempt.passed ? 'success' : 'error'}
                            size="small"
                          />
                          <Typography variant="body2" fontWeight={700}>
                            {attempt.percentage.toFixed(0)}%
                          </Typography>
                          <Button size="small" onClick={() => navigate(`/intentos/${attempt.id}`)}>
                            Ver detalle
                          </Button>
                        </>
                      ) : (
                        <Chip label="En corrección" size="small" />
                      )}
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}

function TrainingCard({ training, onOpen }: { training: MyTraining; onOpen: () => void }) {
  const progress = progressValue(training.progress);
  const completed = training.status === 'COMPLETED';

  return (
    <Card sx={{ height: '100%' }}>
      <CardActionArea onClick={onOpen} sx={{ height: '100%', alignItems: 'stretch' }}>
        <CardContent sx={{ p: 2.5, height: '100%', display: 'flex', flexDirection: 'column' }}>
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
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 1.5 }}>
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
