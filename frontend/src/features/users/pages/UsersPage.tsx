/** Administración de usuarios de la empresa (RF-008). */

import { zodResolver } from '@hookform/resolvers/zod';
import { Add, Block, CheckCircle, People } from '@mui/icons-material';
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
  IconButton,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Paginated, User } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { ROLE_LABEL, formatDate } from '@/shared/utils/format';

const schema = z.object({
  email: z.string().email('Correo inválido.'),
  first_name: z.string().min(1, 'El nombre es obligatorio.'),
  last_name: z.string().optional(),
  role: z.enum(['ADMIN', 'INSTRUCTOR', 'STUDENT']),
  job_title: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export default function UsersPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');

  const users = useQuery({
    queryKey: ['users', { search, role: roleFilter }],
    queryFn: async () =>
      (
        await api.get<Paginated<User>>(endpoints.users.list, {
          params: {
            ...(search && { search }),
            ...(roleFilter && { role: roleFilter }),
            page_size: 100,
          },
        })
      ).data,
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', first_name: '', last_name: '', role: 'STUDENT', job_title: '' },
  });

  const createUser = useMutation({
    mutationFn: (values: FormValues) => api.post<User>(endpoints.users.list, values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
      setDialogOpen(false);
      form.reset();
      snackbar.success('Usuario creado. Se envió la invitación con su contraseña temporal.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.post(active ? endpoints.users.deactivate(id) : endpoints.users.activate(id)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] });
      snackbar.info('Estado del usuario actualizado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (users.isLoading) return <Loading label="Cargando usuarios…" />;
  if (users.isError) return <ErrorState error={users.error} onRetry={users.refetch} />;

  const items = users.data?.results ?? [];

  return (
    <Box>
      <PageHeader
        title="Usuarios"
        subtitle="Administradores, instructores y estudiantes de tu empresa"
        actions={
          <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
            Nuevo usuario
          </Button>
        }
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3, maxWidth: 620 }}>
        <TextField
          label="Buscar"
          placeholder="Nombre, correo o cargo"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <TextField
          select
          label="Rol"
          value={roleFilter}
          onChange={(event) => setRoleFilter(event.target.value)}
        >
          <MenuItem value="">Todos</MenuItem>
          <MenuItem value="ADMIN">Administrador</MenuItem>
          <MenuItem value="INSTRUCTOR">Instructor</MenuItem>
          <MenuItem value="STUDENT">Estudiante</MenuItem>
        </TextField>
      </Stack>

      {items.length === 0 ? (
        <EmptyState
          icon={<People />}
          title="Sin usuarios que coincidan"
          description="Ajusta los filtros o crea un usuario nuevo."
        />
      ) : (
        <Card>
          <CardContent sx={{ p: 0 }}>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 720 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Usuario</TableCell>
                    <TableCell>Rol</TableCell>
                    <TableCell>Cargo</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell>Último acceso</TableCell>
                    <TableCell align="right">Acciones</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((user) => (
                    <TableRow key={user.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={600}>
                          {user.full_name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {user.email}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={ROLE_LABEL[user.role] ?? user.role}
                          size="small"
                          color={
                            user.role === 'ADMIN' || user.role === 'SUPERADMIN'
                              ? 'primary'
                              : user.role === 'INSTRUCTOR'
                                ? 'secondary'
                                : 'default'
                          }
                        />
                      </TableCell>
                      <TableCell>{user.job_title || '—'}</TableCell>
                      <TableCell>
                        <Chip
                          label={user.is_active ? 'Activo' : 'Inactivo'}
                          size="small"
                          color={user.is_active ? 'success' : 'default'}
                          variant={user.is_active ? 'filled' : 'outlined'}
                        />
                      </TableCell>
                      <TableCell>{formatDate(user.last_login)}</TableCell>
                      <TableCell align="right">
                        <Tooltip title={user.is_active ? 'Desactivar' : 'Activar'}>
                          <IconButton
                            size="small"
                            color={user.is_active ? 'error' : 'success'}
                            onClick={() =>
                              toggleActive.mutate({ id: user.id, active: user.is_active })
                            }
                          >
                            {user.is_active ? (
                              <Block fontSize="small" />
                            ) : (
                              <CheckCircle fontSize="small" />
                            )}
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </CardContent>
        </Card>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <Box component="form" onSubmit={form.handleSubmit((values) => createUser.mutate(values))}>
          <DialogTitle>Nuevo usuario</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                label="Correo electrónico"
                autoFocus
                error={Boolean(form.formState.errors.email)}
                helperText={form.formState.errors.email?.message}
                {...form.register('email')}
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Nombre"
                  error={Boolean(form.formState.errors.first_name)}
                  helperText={form.formState.errors.first_name?.message}
                  {...form.register('first_name')}
                />
                <TextField label="Apellido" {...form.register('last_name')} />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField select label="Rol" defaultValue="STUDENT" {...form.register('role')}>
                  <MenuItem value="STUDENT">Estudiante</MenuItem>
                  <MenuItem value="INSTRUCTOR">Instructor</MenuItem>
                  <MenuItem value="ADMIN">Administrador</MenuItem>
                </TextField>
                <TextField label="Cargo" {...form.register('job_title')} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Se generará una contraseña temporal y se enviará por correo junto con el enlace de
                acceso.
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={createUser.isPending}>
              Crear e invitar
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
