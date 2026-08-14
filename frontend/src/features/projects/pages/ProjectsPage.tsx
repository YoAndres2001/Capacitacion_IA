import { zodResolver } from '@hookform/resolvers/zod';
import {
  Add,
  Apps,
  Archive,
  Edit,
  MenuBook,
  MoreVert,
  Storage,
  Unarchive,
} from '@mui/icons-material';
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
  IconButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
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
import { ConfirmDialog, EmptyState, ErrorState, Loading, PageHeader } from '@/shared/components';
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
  // Proyecto en edición; `null` significa que el diálogo crea uno nuevo.
  const [editing, setEditing] = useState<Project | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; project: Project } | null>(null);
  const [toArchive, setToArchive] = useState<Project | null>(null);

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
      closeDialog();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const updateProject = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Partial<Project> }) =>
      api.patch<Project>(endpoints.projects.detail(id), values),
    onSuccess: async ({ data }) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
      await queryClient.invalidateQueries({ queryKey: ['project', data.id] });
      snackbar.success(`Proyecto «${data.name}» actualizado.`);
      closeDialog();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  // El backend archiva en lugar de borrar: el conocimiento indexado se conserva.
  const archiveProject = useMutation({
    mutationFn: (id: string) => api.delete(endpoints.projects.detail(id)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
      setToArchive(null);
      snackbar.success('Proyecto archivado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  function closeDialog() {
    setDialogOpen(false);
    setEditing(null);
    form.reset({ name: '', code: '', description: '' });
  }

  function openCreate() {
    setEditing(null);
    form.reset({ name: '', code: '', description: '' });
    setDialogOpen(true);
  }

  function openEdit(project: Project) {
    setEditing(project);
    form.reset({
      name: project.name,
      code: project.code ?? '',
      description: project.description ?? '',
    });
    setDialogOpen(true);
  }

  if (projects.isLoading) return <Loading label="Cargando proyectos…" />;
  if (projects.isError) return <ErrorState error={projects.error} onRetry={projects.refetch} />;

  const items = projects.data?.results ?? [];

  return (
    <Box>
      <PageHeader
        title="Proyectos"
        subtitle="Cada proyecto (ERP, WMS, CRM…) tiene su propio conocimiento aislado"
        actions={
          <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
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
            <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
              Crear proyecto
            </Button>
          }
        />
      ) : (
        <Grid container spacing={2.5}>
          {items.map((project) => (
            <Grid size={{ xs: 12, sm: 6, lg: 4, xl: 3 }} key={project.id}>
              <Card
                sx={{
                  height: '100%',
                  borderTop: 4,
                  borderColor: project.color,
                  position: 'relative',
                }}
              >
                <IconButton
                  size="small"
                  aria-label={`Acciones de ${project.name}`}
                  onClick={(event) => setMenu({ anchor: event.currentTarget, project })}
                  sx={{ position: 'absolute', top: 8, right: 8, zIndex: 1 }}
                >
                  <MoreVert fontSize="small" />
                </IconButton>
                <CardActionArea
                  onClick={() => navigate(`/proyectos/${project.id}`)}
                  sx={{ height: '100%', alignItems: 'stretch' }}
                >
                  <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="flex-start"
                      sx={{ pr: 4 }}
                    >
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

      <Menu
        open={menu !== null}
        anchorEl={menu?.anchor ?? null}
        onClose={() => setMenu(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem
          onClick={() => {
            if (menu) openEdit(menu.project);
            setMenu(null);
          }}
        >
          <ListItemIcon>
            <Edit fontSize="small" />
          </ListItemIcon>
          <ListItemText>Editar</ListItemText>
        </MenuItem>
        {menu?.project.status === 'ARCHIVED' ? (
          <MenuItem
            onClick={() => {
              if (menu) updateProject.mutate({ id: menu.project.id, values: { status: 'ACTIVE' } });
              setMenu(null);
            }}
          >
            <ListItemIcon>
              <Unarchive fontSize="small" />
            </ListItemIcon>
            <ListItemText>Restaurar</ListItemText>
          </MenuItem>
        ) : (
          <MenuItem
            onClick={() => {
              setToArchive(menu?.project ?? null);
              setMenu(null);
            }}
          >
            <ListItemIcon>
              <Archive fontSize="small" color="error" />
            </ListItemIcon>
            <ListItemText slotProps={{ primary: { color: 'error' } }}>Archivar</ListItemText>
          </MenuItem>
        )}
      </Menu>

      <ConfirmDialog
        open={toArchive !== null}
        title="Archivar proyecto"
        message={`«${toArchive?.name ?? ''}» dejará de estar activo. Sus capacitaciones y su conocimiento indexado se conservan, y puedes restaurarlo más adelante.`}
        confirmLabel="Archivar"
        destructive
        loading={archiveProject.isPending}
        onConfirm={() => toArchive && archiveProject.mutate(toArchive.id)}
        onCancel={() => setToArchive(null)}
      />

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <Box
          component="form"
          onSubmit={form.handleSubmit((values) =>
            editing
              ? updateProject.mutate({ id: editing.id, values })
              : createProject.mutate(values),
          )}
        >
          <DialogTitle>{editing ? 'Editar proyecto' : 'Nuevo proyecto'}</DialogTitle>
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
              {!editing && (
                <Typography variant="caption" color="text.secondary">
                  Al crear el proyecto se aprovisiona automáticamente su colección vectorial FAISS.
                </Typography>
              )}
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={closeDialog}>Cancelar</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createProject.isPending || updateProject.isPending}
            >
              {editing ? 'Guardar' : 'Crear'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
