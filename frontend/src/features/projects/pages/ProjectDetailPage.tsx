import { ArrowBack, Autorenew, MenuBook, Storage } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Paginated, Project, Training } from '@/shared/api/types';
import {
  ConfirmDialog,
  ErrorState,
  Loading,
  PageHeader,
  StatCard,
  StatusChip,
} from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { formatDateTime } from '@/shared/utils/format';

interface ProjectStats {
  trainings: number;
  published_trainings: number;
  materials: number;
  materials_available: number;
  materials_processing: number;
  materials_error: number;
  chunks: number;
  vectors: number;
  enrolled_users: number;
}

export default function ProjectDetailPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [confirmRebuild, setConfirmRebuild] = useState(false);

  const project = useQuery({
    queryKey: ['projects', projectId],
    queryFn: async () => (await api.get<Project>(endpoints.projects.detail(projectId))).data,
  });

  const stats = useQuery({
    queryKey: ['projects', projectId, 'stats'],
    queryFn: async () => (await api.get<ProjectStats>(endpoints.projects.stats(projectId))).data,
  });

  const trainings = useQuery({
    queryKey: ['trainings', { project: projectId }],
    queryFn: async () =>
      (await api.get<Paginated<Training>>(endpoints.trainings.list, { params: { project: projectId } }))
        .data,
  });

  const rebuild = useMutation({
    mutationFn: () => api.post(endpoints.projects.rebuildIndex(projectId)),
    onSuccess: async () => {
      snackbar.info('Reconstrucción del índice encolada. El chat sigue disponible mientras tanto.');
      setConfirmRebuild(false);
      await queryClient.invalidateQueries({ queryKey: ['projects', projectId] });
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (project.isLoading) return <Loading />;
  if (project.isError) return <ErrorState error={project.error} onRetry={project.refetch} />;

  const data = project.data!;
  const collection = data.vector_collection;

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton onClick={() => navigate('/proyectos')} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          Proyectos
        </Typography>
      </Stack>

      <PageHeader
        title={data.name}
        subtitle={data.description || 'Sin descripción'}
        actions={
          <>
            <Button
              variant="outlined"
              startIcon={<Autorenew />}
              onClick={() => setConfirmRebuild(true)}
            >
              Reconstruir índice
            </Button>
            <Button
              component={RouterLink}
              to="/capacitaciones"
              variant="contained"
              startIcon={<MenuBook />}
            >
              Capacitaciones
            </Button>
          </>
        }
      />

      {collection?.status === 'ERROR' && (
        <Alert severity="error" sx={{ mb: 3 }}>
          El índice vectorial presenta un error: {collection.error_detail || 'sin detalle'}. Puedes
          reconstruirlo desde PostgreSQL sin perder contenido.
        </Alert>
      )}

      {stats.data && (
        <Grid container spacing={2.5} sx={{ mb: 3 }}>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Capacitaciones"
              value={stats.data.trainings}
              hint={`${stats.data.published_trainings} publicadas`}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Materiales"
              value={stats.data.materials}
              hint={`${stats.data.materials_available} disponibles`}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard
              label="Fragmentos"
              value={stats.data.chunks.toLocaleString('es-CL')}
              hint={`${stats.data.vectors.toLocaleString('es-CL')} vectores`}
              icon={<Storage />}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="Usuarios inscritos" value={stats.data.enrolled_users} />
          </Grid>
        </Grid>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography variant="h4" gutterBottom>
                Colección vectorial
              </Typography>
              {collection ? (
                <Stack spacing={1.5} sx={{ mt: 2 }}>
                  <Row label="Estado" value={<StatusChip status={collection.status} />} />
                  <Divider />
                  <Row label="Proveedor" value={collection.provider || '—'} />
                  <Row label="Modelo" value={collection.embedding_model || '—'} />
                  <Row label="Dimensión" value={collection.dimension || '—'} />
                  <Row label="Tipo de índice" value={collection.index_type || '—'} />
                  <Row label="Vectores" value={collection.vector_count.toLocaleString('es-CL')} />
                  <Row label="Versión" value={collection.version} />
                  <Row label="Última reconstrucción" value={formatDateTime(collection.last_rebuilt_at)} />
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Aún no se ha aprovisionado el índice.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography variant="h4" gutterBottom>
                Capacitaciones del proyecto
              </Typography>
              {(trainings.data?.results.length ?? 0) === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                  Este proyecto todavía no tiene capacitaciones.
                </Typography>
              ) : (
                <Stack divider={<Divider />} sx={{ mt: 1 }}>
                  {trainings.data!.results.map((training) => (
                    <Stack
                      key={training.id}
                      direction={{ xs: 'column', sm: 'row' }}
                      alignItems={{ xs: 'flex-start', sm: 'center' }}
                      justifyContent="space-between"
                      spacing={1}
                      sx={{ py: 1.5 }}
                    >
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="subtitle2" noWrap>
                          {training.title}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {training.module_count} módulos · {training.lesson_count} lecciones ·{' '}
                          {training.enrollment_count} inscritos
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <StatusChip status={training.status} />
                        <Button
                          size="small"
                          component={RouterLink}
                          to={`/capacitaciones/${training.id}/editor`}
                        >
                          Abrir
                        </Button>
                      </Stack>
                    </Stack>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <ConfirmDialog
        open={confirmRebuild}
        title="Reconstruir índice vectorial"
        message={
          <Stack spacing={1}>
            <Typography variant="body2">
              Se regenerarán todos los embeddings del proyecto a partir de los fragmentos guardados
              en PostgreSQL.
            </Typography>
            <Typography variant="body2" color="text.secondary">
              El índice actual sigue respondiendo consultas hasta que la reconstrucción termina, así
              que el chat no se interrumpe.
            </Typography>
          </Stack>
        }
        confirmLabel="Reconstruir"
        loading={rebuild.isPending}
        onConfirm={() => rebuild.mutate()}
        onCancel={() => setConfirmRebuild(false)}
      />
    </Box>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Typography variant="body2" fontWeight={600}>
          {value}
        </Typography>
      ) : (
        value
      )}
    </Stack>
  );
}
