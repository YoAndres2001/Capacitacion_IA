/** Inicio del estudiante: objetivos pendientes, continuidad y evaluaciones. */

import { ArrowForward, AutoStories, CheckCircle, Quiz, School } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { TrainingCard } from '@/features/dashboard/components/TrainingCard';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Attempt, MyStats, MyTraining, Paginated } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, StatCard } from '@/shared/components';
import { formatDate, progressValue } from '@/shared/utils/format';

export default function StudentHomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const trainings = useQuery({
    queryKey: ['me', 'trainings'],
    queryFn: async () => (await api.get<Paginated<MyTraining>>(endpoints.me.trainings)).data,
  });

  const stats = useQuery({
    queryKey: ['me', 'stats'],
    queryFn: async () => (await api.get<MyStats>(endpoints.me.stats)).data,
  });

  const attempts = useQuery({
    queryKey: ['me', 'attempts'],
    queryFn: async () => (await api.get<Paginated<Attempt>>(endpoints.me.attempts)).data,
  });

  if (trainings.isLoading) return <Loading label="Cargando tu inicio…" />;
  if (trainings.isError) return <ErrorState error={trainings.error} onRetry={trainings.refetch} />;

  const items = trainings.data?.results ?? [];
  const pending = items.filter((item) => item.status !== 'COMPLETED');
  const started = pending.filter((item) => progressValue(item.progress) > 0);
  const completed = items.filter((item) => item.status === 'COMPLETED');
  const openCourse = (item: MyTraining) => navigate(`/cursos/${item.training_id}`);

  return (
    <Box>
      <Box sx={{ mb: 4 }}>
        <Typography variant="body2" color="text.secondary">
          Hola {user?.first_name}
        </Typography>
        <Typography variant="h1" sx={{ mt: 0.5 }}>
          {pending.length > 0 ? 'Tienes objetivos por completar' : 'Estás al día'}
        </Typography>
      </Box>

      {pending.length > 0 ? (
        <Box sx={{ mb: 5 }}>
          <SectionHeader
            title="Objetivos pendientes"
            actionLabel="Ver mis rutas"
            onAction={() => navigate('/rutas')}
          />
          <Grid container spacing={2.5}>
            {pending.slice(0, 6).map((item) => (
              <Grid size={{ xs: 12, sm: 6, lg: 4, xl: 3 }} key={item.id}>
                <TrainingCard training={item} onOpen={() => openCourse(item)} />
              </Grid>
            ))}
          </Grid>
        </Box>
      ) : (
        items.length === 0 && (
          <EmptyState
            icon={<School />}
            title="Aún no tienes capacitaciones asignadas"
            description="Para realizar un curso tu educador debe invitarte. Mientras tanto, revisa el catálogo disponible en Academia."
            action={
              <Button variant="contained" onClick={() => navigate('/academia')}>
                Ir a Academia
              </Button>
            }
          />
        )
      )}

      {started.length > 0 && (
        <Box sx={{ mb: 5 }}>
          <SectionHeader
            title="Continúa aprendiendo"
            actionLabel="Ver mi progreso"
            onAction={() => navigate('/progreso')}
          />
          <Grid container spacing={2.5}>
            {started.slice(0, 3).map((item) => (
              <Grid size={{ xs: 12, sm: 6, lg: 4, xl: 3 }} key={item.id}>
                <TrainingCard training={item} onOpen={() => openCourse(item)} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {stats.data && (
        <Grid container spacing={2.5} sx={{ mb: 5 }}>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Cursos asignados"
              value={stats.data.trainings.assigned}
              icon={<School />}
            />
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

      {completed.length > 0 && (
        <Box sx={{ mb: 5 }}>
          <SectionHeader title="Completadas" />
          <Grid container spacing={2.5}>
            {completed.slice(0, 3).map((item) => (
              <Grid size={{ xs: 12, sm: 6, lg: 4, xl: 3 }} key={item.id}>
                <TrainingCard training={item} onOpen={() => openCourse(item)} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {(attempts.data?.results?.length ?? 0) > 0 && (
        <Box>
          <SectionHeader title="Mis evaluaciones" />
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
                        Intento {attempt.number} ·{' '}
                        {formatDate(attempt.graded_at ?? attempt.started_at)}
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

function SectionHeader({
  title,
  actionLabel,
  onAction,
}: {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
      <Typography variant="h3">{title}</Typography>
      {actionLabel && onAction && (
        <Button size="small" endIcon={<ArrowForward />} onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </Stack>
  );
}
