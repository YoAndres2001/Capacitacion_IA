/** Progreso: tiempo dedicado por día y cursos que el estudiante está viendo. */

import { Insights, MenuBook, PlayCircleOutline, Schedule } from '@mui/icons-material';
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
  useTheme,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { BarChart } from '@mui/x-charts/BarChart';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { MyActivity } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader, ProgressBar, StatCard } from '@/shared/components';
import { STATUS_LABEL, formatDurationLong, relativeTime } from '@/shared/utils/format';

const RANGES = [
  { value: 7, label: 'Últimos 7 días' },
  { value: 14, label: 'Últimas 2 semanas' },
  { value: 30, label: 'Últimos 30 días' },
];

export default function ProgressPage() {
  const theme = useTheme();
  const navigate = useNavigate();
  const [days, setDays] = useState(7);

  const activity = useQuery({
    queryKey: ['me', 'activity', days],
    queryFn: async () =>
      (await api.get<MyActivity>(endpoints.me.activity, { params: { days } })).data,
  });

  if (activity.isLoading) return <Loading label="Cargando tu progreso…" />;
  if (activity.isError) return <ErrorState error={activity.error} onRetry={activity.refetch} />;

  const data = activity.data!;
  const labels = data.daily.map((point) =>
    new Date(`${point.date}T00:00:00`).toLocaleDateString('es-CL', {
      day: 'numeric',
      month: 'short',
    }),
  );
  const minutes = data.daily.map((point) => Math.round(point.seconds / 60));
  const hasActivity = data.totals.seconds > 0;

  return (
    <Box>
      <PageHeader
        title="Mi progreso"
        subtitle="Tiempo dedicado a tus cursos y en qué estás avanzando"
        actions={
          <TextField
            select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            sx={{ minWidth: { sm: 190 }, width: { xs: '100%', sm: 'auto' } }}
          >
            {RANGES.map((range) => (
              <MenuItem key={range.value} value={range.value}>
                {range.label}
              </MenuItem>
            ))}
          </TextField>
        }
      />

      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, sm: 4 }}>
          <StatCard
            label="Tiempo de estudio"
            value={formatDurationLong(data.totals.seconds)}
            hint={RANGES.find((range) => range.value === days)?.label}
            icon={<Schedule />}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 4 }}>
          <StatCard
            label="Clases vistas"
            value={data.totals.lessons}
            icon={<PlayCircleOutline />}
            color="info.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <StatCard
            label="Cursos en avance"
            value={data.totals.trainings}
            icon={<MenuBook />}
            color="secondary.main"
          />
        </Grid>
      </Grid>

      <Paper sx={{ p: { xs: 2, sm: 2.5 }, mb: 4 }}>
        <Typography variant="h4" sx={{ mb: 0.5 }}>
          Tiempo por día
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Minutos dedicados a las clases entre el {labels[0]} y el {labels[labels.length - 1]}
        </Typography>
        {hasActivity ? (
          <BarChart
            height={280}
            xAxis={[{ scaleType: 'band', data: labels }]}
            yAxis={[{ label: 'min' }]}
            series={[{ data: minutes, label: 'Minutos', color: theme.palette.primary.main }]}
            margin={{ top: 30, right: 16, bottom: 40, left: 50 }}
            slotProps={{ legend: { hidden: true } }}
          />
        ) : (
          <Box sx={{ py: 5, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Todavía no registras tiempo de estudio en este período.
            </Typography>
          </Box>
        )}
      </Paper>

      <Typography variant="h3" sx={{ mb: 2 }}>
        Cursos que estás viendo
      </Typography>

      {data.trainings.length === 0 ? (
        <EmptyState
          icon={<Insights />}
          title="Aún no hay actividad registrada"
          description="Cuando comiences a ver clases aparecerá aquí el detalle por curso."
        />
      ) : (
        <Grid container spacing={2.5}>
          {data.trainings.map((item) => (
            <Grid size={{ xs: 12, sm: 6, xl: 4 }} key={item.training_id}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardActionArea
                  onClick={() => navigate(`/cursos/${item.training_id}`)}
                  sx={{ height: '100%' }}
                >
                  <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="flex-start"
                      spacing={1.5}
                      sx={{ mb: 1 }}
                    >
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="h5" noWrap>
                          {item.title}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {item.project_name} · última vez {relativeTime(item.last_viewed_at)}
                        </Typography>
                      </Box>
                      <Chip
                        label={STATUS_LABEL[item.status] ?? item.status}
                        size="small"
                        color={item.status === 'COMPLETED' ? 'success' : 'default'}
                      />
                    </Stack>

                    <ProgressBar
                      value={item.progress}
                      color={item.status === 'COMPLETED' ? 'success' : 'primary'}
                    />

                    <Stack direction="row" spacing={2} sx={{ mt: 1.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        {formatDurationLong(item.seconds)} de estudio
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.lessons_completed}/{item.lessons_viewed} clases completadas
                      </Typography>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
