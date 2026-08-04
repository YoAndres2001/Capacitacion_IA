import { zodResolver } from '@hookform/resolvers/zod';
import { Add, Edit, MenuBook, Publish, Quiz } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Paginated, Project, Training } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { LEVEL_LABEL } from '@/shared/utils/format';

const schema = z.object({
  project: z.string().uuid('Selecciona un proyecto.'),
  title: z.string().min(3, 'Mínimo 3 caracteres.').max(200),
  description: z.string().max(2000).optional(),
  level: z.enum(['BEGINNER', 'INTERMEDIATE', 'ADVANCED']),
  estimated_minutes: z.coerce.number().int().min(0).max(6000),
});

type FormValues = z.infer<typeof schema>;

export default function TrainingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [projectFilter, setProjectFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: async () => (await api.get<Paginated<Project>>(endpoints.projects.list)).data,
  });

  const trainings = useQuery({
    queryKey: ['trainings', { project: projectFilter, status: statusFilter }],
    queryFn: async () =>
      (
        await api.get<Paginated<Training>>(endpoints.trainings.list, {
          params: {
            ...(projectFilter && { project: projectFilter }),
            ...(statusFilter && { status: statusFilter }),
          },
        })
      ).data,
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      project: '',
      title: '',
      description: '',
      level: 'BEGINNER',
      estimated_minutes: 60,
    },
  });

  const createTraining = useMutation({
    mutationFn: (values: FormValues) => api.post<Training>(endpoints.trainings.list, values),
    onSuccess: async ({ data }) => {
      await queryClient.invalidateQueries({ queryKey: ['trainings'] });
      setDialogOpen(false);
      form.reset();
      snackbar.success('Capacitación creada. Ahora agrega módulos y material.');
      navigate(`/capacitaciones/${data.id}/editor`);
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const publish = useMutation({
    mutationFn: (id: string) => api.post(endpoints.trainings.publish(id)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['trainings'] });
      snackbar.success('Capacitación publicada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (trainings.isLoading) return <Loading label="Cargando capacitaciones…" />;
  if (trainings.isError) return <ErrorState error={trainings.error} onRetry={trainings.refetch} />;

  const items = trainings.data?.results ?? [];
  const projectOptions = projects.data?.results ?? [];

  return (
    <Box>
      <PageHeader
        title="Capacitaciones"
        subtitle="Cursos con video, documentos, chat IA y evaluaciones"
        actions={
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setDialogOpen(true)}
            disabled={projectOptions.length === 0}
          >
            Nueva capacitación
          </Button>
        }
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3, maxWidth: 620 }}>
        <TextField
          select
          label="Proyecto"
          value={projectFilter}
          onChange={(event) => setProjectFilter(event.target.value)}
        >
          <MenuItem value="">Todos</MenuItem>
          {projectOptions.map((project) => (
            <MenuItem key={project.id} value={project.id}>
              {project.name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Estado"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <MenuItem value="">Todos</MenuItem>
          <MenuItem value="DRAFT">Borrador</MenuItem>
          <MenuItem value="PUBLISHED">Publicada</MenuItem>
          <MenuItem value="ARCHIVED">Archivada</MenuItem>
        </TextField>
      </Stack>

      {projectOptions.length === 0 ? (
        <EmptyState
          icon={<MenuBook />}
          title="Primero crea un proyecto"
          description="Las capacitaciones pertenecen a un proyecto (ERP, WMS, CRM…)."
          action={
            <Button component={RouterLink} to="/proyectos" variant="contained">
              Ir a proyectos
            </Button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<MenuBook />}
          title="No hay capacitaciones con estos filtros"
          description="Crea una nueva capacitación o ajusta los filtros."
          action={
            <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
              Nueva capacitación
            </Button>
          }
        />
      ) : (
        <Grid container spacing={2.5}>
          {items.map((training) => (
            <Grid size={{ xs: 12, md: 6, xl: 4 }} key={training.id}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ p: 2.5, display: 'flex', flexDirection: 'column', height: '100%' }}>
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                    <Chip label={training.project_name} size="small" variant="outlined" />
                    <StatusChip status={training.status} />
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

                  <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                    <Chip label={LEVEL_LABEL[training.level]} size="small" />
                    <Chip label={`${training.module_count} módulos`} size="small" variant="outlined" />
                    <Chip label={`${training.lesson_count} lecciones`} size="small" variant="outlined" />
                    <Chip
                      label={`${training.enrollment_count} inscritos`}
                      size="small"
                      variant="outlined"
                    />
                  </Stack>

                  <Stack direction="row" spacing={1} sx={{ mt: 'auto' }}>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<Edit />}
                      component={RouterLink}
                      to={`/capacitaciones/${training.id}/editor`}
                    >
                      Editar
                    </Button>
                    {training.status === 'DRAFT' && (
                      <Tooltip
                        title={
                          training.can_be_published
                            ? 'Publicar la capacitación'
                            : 'Necesita al menos una lección con material disponible'
                        }
                      >
                        <span>
                          <Button
                            size="small"
                            variant="contained"
                            startIcon={<Publish />}
                            disabled={!training.can_be_published || publish.isPending}
                            onClick={() => publish.mutate(training.id)}
                          >
                            Publicar
                          </Button>
                        </span>
                      </Tooltip>
                    )}
                    {training.status === 'PUBLISHED' && (
                      <Button
                        size="small"
                        startIcon={<Quiz />}
                        component={RouterLink}
                        to={`/capacitaciones/${training.id}/editor?tab=exams`}
                      >
                        Evaluaciones
                      </Button>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <Box component="form" onSubmit={form.handleSubmit((values) => createTraining.mutate(values))}>
          <DialogTitle>Nueva capacitación</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                select
                label="Proyecto"
                error={Boolean(form.formState.errors.project)}
                helperText={form.formState.errors.project?.message}
                {...form.register('project')}
                defaultValue=""
              >
                {projectOptions.map((project) => (
                  <MenuItem key={project.id} value={project.id}>
                    {project.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Título"
                placeholder="Inventario — Nivel Básico"
                error={Boolean(form.formState.errors.title)}
                helperText={form.formState.errors.title?.message}
                {...form.register('title')}
              />
              <TextField label="Descripción" multiline rows={3} {...form.register('description')} />
              <Stack direction="row" spacing={2}>
                <TextField select label="Nivel" defaultValue="BEGINNER" {...form.register('level')}>
                  <MenuItem value="BEGINNER">Principiante</MenuItem>
                  <MenuItem value="INTERMEDIATE">Intermedio</MenuItem>
                  <MenuItem value="ADVANCED">Avanzado</MenuItem>
                </TextField>
                <TextField
                  label="Duración estimada (min)"
                  type="number"
                  {...form.register('estimated_minutes')}
                />
              </Stack>
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createTraining.isPending}>
              Crear
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
