import {
  Apps,
  AutoAwesome,
  CheckCircle,
  MenuBook,
  People,
  Psychology,
  Quiz,
  VideoLibrary,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { AIHealth, AnalyticsOverview } from '@/shared/api/types';
import { ErrorState, Loading, PageHeader, StatCard } from '@/shared/components';
import { STATUS_LABEL } from '@/shared/utils/format';

export default function AdminDashboard() {
  const overview = useQuery({
    queryKey: ['analytics', 'overview'],
    queryFn: async () => (await api.get<AnalyticsOverview>(endpoints.analytics.overview)).data,
  });

  const health = useQuery({
    queryKey: ['ai', 'health'],
    queryFn: async () => (await api.get<AIHealth>(endpoints.ai.health)).data,
    retry: false,
    staleTime: 60_000,
  });

  if (overview.isLoading) return <Loading label="Cargando panel…" />;
  if (overview.isError) return <ErrorState error={overview.error} onRetry={overview.refetch} />;

  const data = overview.data!;
  const processing =
    data.content.materials_by_status.find((row) =>
      ['PENDING', 'PROCESSING', 'ANALYZING'].includes(row.status),
    )?.count ?? 0;

  return (
    <Box>
      <PageHeader
        title="Panel de administración"
        subtitle="Estado general de la plataforma"
        actions={
          <Button component={RouterLink} to="/capacitaciones" variant="contained">
            Gestionar capacitaciones
          </Button>
        }
      />

      {health.data && !health.data.available && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          El proveedor de IA ({health.data.provider}) no responde. El procesamiento de material y el
          chat quedarán en espera hasta que se restablezca.
        </Alert>
      )}

      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <StatCard
            label="Usuarios activos"
            value={data.users.active}
            hint={`${data.users.total} en total`}
            icon={<People />}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <StatCard
            label="Capacitaciones publicadas"
            value={data.content.published_trainings}
            hint={`${data.content.trainings} creadas`}
            icon={<MenuBook />}
            color="secondary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <StatCard
            label="Materiales"
            value={data.content.materials}
            hint={processing > 0 ? `${processing} en proceso` : 'Todos procesados'}
            icon={<VideoLibrary />}
            color="info.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <StatCard
            label="Avance promedio"
            value={`${data.learning.average_progress.toFixed(0)}%`}
            hint={`${data.learning.completed} cursos completados`}
            icon={<CheckCircle />}
            color="success.main"
          />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography variant="h4" gutterBottom>
                Contenido y conocimiento
              </Typography>
              <Stack spacing={2} sx={{ mt: 2 }}>
                <Row icon={<Apps />} label="Proyectos" value={data.content.projects} />
                <Row icon={<MenuBook />} label="Capacitaciones" value={data.content.trainings} />
                <Row
                  icon={<Psychology />}
                  label="Fragmentos indexados (RAG)"
                  value={data.content.chunks.toLocaleString('es-CL')}
                />
                <Row icon={<Quiz />} label="Exámenes" value={data.assessment.exams} />
              </Stack>

              <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
                Materiales por estado
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {data.content.materials_by_status.map((row) => (
                  <Chip
                    key={row.status}
                    label={`${STATUS_LABEL[row.status] ?? row.status}: ${row.count}`}
                    size="small"
                    color={
                      row.status === 'AVAILABLE'
                        ? 'success'
                        : row.status === 'ERROR'
                          ? 'error'
                          : 'default'
                    }
                  />
                ))}
                {data.content.materials_by_status.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Aún no se ha cargado material.
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={3} sx={{ height: '100%' }}>
            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Typography variant="h4" gutterBottom>
                  Aprendizaje
                </Typography>
                <Stack spacing={2.5} sx={{ mt: 2 }}>
                  <Metric
                    label="Inscripciones"
                    value={data.learning.enrollments}
                    detail={`${data.learning.in_progress} en curso · ${data.learning.completed} completadas`}
                  />
                  <Box>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                      <Typography variant="body2">Aprobación de exámenes</Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {data.assessment.pass_rate.toFixed(0)}%
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={data.assessment.pass_rate}
                      color="success"
                      sx={{ height: 8, borderRadius: 4 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {data.assessment.graded} intentos corregidos de {data.assessment.attempts}
                    </Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
                  <AutoAwesome color="primary" />
                  <Typography variant="h4">Utilización de IA</Typography>
                  {health.data?.embeddings_local && (
                    <Chip label="Embeddings locales" color="success" size="small" />
                  )}
                </Stack>

                <Grid container spacing={2}>
                  <Grid size={6}>
                    <Metric label="Llamadas" value={data.ai.calls.toLocaleString('es-CL')} />
                  </Grid>
                  <Grid size={6}>
                    <Metric label="Tokens" value={data.ai.total_tokens.toLocaleString('es-CL')} />
                  </Grid>
                  <Grid size={6}>
                    <Metric label="Costo estimado" value={`US$ ${data.ai.cost_usd.toFixed(2)}`} />
                  </Grid>
                  <Grid size={6}>
                    <Metric
                      label="Sin contexto"
                      value={`${data.ai.no_context_rate.toFixed(1)}%`}
                      detail={`${data.ai.chat_answers} respuestas`}
                    />
                  </Grid>
                </Grid>

                {health.data && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Modelo: {health.data.llm_model} ({health.data.provider}) · Embeddings:{' '}
                    {health.data.embedding_model} ({health.data.embedding_provider})
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.5}>
      <Box sx={{ color: 'text.secondary', display: 'flex' }}>{icon}</Box>
      <Typography variant="body2" sx={{ flex: 1 }}>
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={700}>
        {value}
      </Typography>
    </Stack>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
}) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="h4">{value}</Typography>
      {detail && (
        <Typography variant="caption" color="text.secondary">
          {detail}
        </Typography>
      )}
    </Box>
  );
}
