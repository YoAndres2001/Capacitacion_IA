import { zodResolver } from '@hookform/resolvers/zod';
import { Add, Apps, MenuBook, Storage } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Paginated, Project } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';

const schema = z.object({
  name: z.string().min(2, 'Mínimo 2 caracteres.').max(150),
  code: z.string().max(30).optional(),
  description: z.string().max(1000).optional(),
});

type FormValues = z.infer<typeof schema>;

export default function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: async () => (await api.get<Paginated<Project>>(endpoints.projects.list)).data,
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', code: '', description: '' },
  });

  const createProject = useMutation({
    mutationFn: (values: FormValues) => api.post<Project>(endpoints.projects.list, values),
    onSuccess: async ({ data }) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
      snackbar.success(`Proyecto «${data.name}» creado con su colección vectorial.`);
      setDialogOpen(false);
      form.reset();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (projects.isLoading) return <Loading label="Cargando proyectos…" />;
  if (projects.isError) return <ErrorState error={projects.error} onRetry={projects.refetch} />;

  const items = projects.data?.results ?? [];

  return (
    <Box>
      <PageHeader
        title="Proyectos"
        subtitle="Cada proyecto (ERP, WMS, CRM…) tiene su propio conocimiento aislado"
        actions={
          <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
            Nuevo proyecto
          </Button>
        }
      />

      {items.length === 0 ? (
        <EmptyState
          icon={<Apps />}
          title="Todavía no hay proyectos"
          description="Crea el primer proyecto para empezar a organizar el material de capacitación."
          action={
            <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
              Crear proyecto
            </Button>
          }
        />
      ) : (
        <Grid container spacing={2.5}>
          {items.map((project) => (
            <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={project.id}>
              <Card sx={{ height: '100%', borderTop: 4, borderColor: project.color }}>
                <CardActionArea
                  onClick={() => navigate(`/proyectos/${project.id}`)}
                  sx={{ height: '100%', alignItems: 'stretch' }}
                >
                  <CardContent sx={{ p: 2.5 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                      <Box>
                        <Typography variant="h4">{project.name}</Typography>
                        {project.code && (
                          <Typography variant="caption" color="text.secondary">
                            {project.code}
                          </Typography>
                        )}
                      </Box>
                      {project.status === 'ARCHIVED' && (
                        <Chip label="Archivado" size="small" color="warning" />
                      )}
                    </Stack>

                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        my: 2,
                        minHeight: 40,
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {project.description || 'Sin descripción.'}
                    </Typography>

                    <Stack direction="row" spacing={2}>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <MenuBook fontSize="small" color="action" />
                        <Typography variant="caption">
                          {project.training_count} capacitaciones
                        </Typography>
                      </Stack>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Storage fontSize="small" color="action" />
                        <Typography variant="caption">
                          {project.vector_collection?.vector_count ?? 0} vectores
                        </Typography>
                      </Stack>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <Box component="form" onSubmit={form.handleSubmit((values) => createProject.mutate(values))}>
          <DialogTitle>Nuevo proyecto</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                label="Nombre"
                autoFocus
                placeholder="ERP Sistemas Expertos"
                error={Boolean(form.formState.errors.name)}
                helperText={form.formState.errors.name?.message}
                {...form.register('name')}
              />
              <TextField label="Código" placeholder="ERP" {...form.register('code')} />
              <TextField
                label="Descripción"
                multiline
                rows={3}
                {...form.register('description')}
              />
              <Typography variant="caption" color="text.secondary">
                Al crear el proyecto se aprovisiona automáticamente su colección vectorial FAISS.
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createProject.isPending}>
              Crear
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
