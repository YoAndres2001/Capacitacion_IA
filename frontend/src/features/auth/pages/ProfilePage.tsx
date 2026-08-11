import { zodResolver } from '@hookform/resolvers/zod';
import { Avatar, Box, Button, Card, CardContent, Divider, Stack, TextField, Typography } from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import { useAuth } from '@/features/auth/AuthContext';
import { PageHeader } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { ROLE_LABEL } from '@/shared/utils/format';

const profileSchema = z.object({
  first_name: z.string().min(1, 'El nombre es obligatorio.'),
  last_name: z.string(),
  job_title: z.string(),
  phone: z.string(),
});

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Ingresa tu contraseña actual.'),
    new_password: z.string().min(8, 'Debe tener al menos 8 caracteres.'),
    confirm: z.string(),
  })
  .refine((data) => data.new_password === data.confirm, {
    message: 'Las contraseñas no coinciden.',
    path: ['confirm'],
  });

type ProfileValues = z.infer<typeof profileSchema>;
type PasswordValues = z.infer<typeof passwordSchema>;

export default function ProfilePage() {
  const { user, refreshProfile } = useAuth();
  const snackbar = useSnackbar();

  const profileForm = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    values: {
      first_name: user?.first_name ?? '',
      last_name: user?.last_name ?? '',
      job_title: user?.job_title ?? '',
      phone: user?.phone ?? '',
    },
  });

  const passwordForm = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirm: '' },
  });

  const updateProfile = useMutation({
    mutationFn: (values: ProfileValues) => api.patch(endpoints.auth.me, values),
    onSuccess: async () => {
      await refreshProfile();
      snackbar.success('Perfil actualizado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const changePassword = useMutation({
    mutationFn: (values: PasswordValues) =>
      api.post(endpoints.auth.changePassword, {
        current_password: values.current_password,
        new_password: values.new_password,
      }),
    onSuccess: () => {
      passwordForm.reset();
      snackbar.success('Contraseña actualizada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  return (
    <Box>
      <PageHeader title="Mi perfil" subtitle="Datos personales y seguridad de la cuenta" />

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 4 }}>
              <Avatar
                sx={{ width: 88, height: 88, mx: 'auto', mb: 2, bgcolor: 'primary.main', fontSize: 34 }}
              >
                {user?.first_name?.[0]?.toUpperCase()}
              </Avatar>
              <Typography variant="h4">{user?.full_name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {user?.email}
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Stack spacing={0.5}>
                <Typography variant="body2">
                  <strong>Rol:</strong> {ROLE_LABEL[user?.role ?? ''] ?? user?.role}
                </Typography>
                <Typography variant="body2">
                  <strong>Empresa:</strong> {user?.company?.name ?? '—'}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Stack spacing={3}>
            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Typography variant="h4" gutterBottom>
                  Datos personales
                </Typography>
                <Box
                  component="form"
                  onSubmit={profileForm.handleSubmit((values) => updateProfile.mutate(values))}
                >
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Nombre"
                        error={Boolean(profileForm.formState.errors.first_name)}
                        helperText={profileForm.formState.errors.first_name?.message}
                        {...profileForm.register('first_name')}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField label="Apellido" {...profileForm.register('last_name')} />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField label="Cargo" {...profileForm.register('job_title')} />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField label="Teléfono" {...profileForm.register('phone')} />
                    </Grid>
                    <Grid size={12}>
                      <Button type="submit" variant="contained" disabled={updateProfile.isPending}>
                        Guardar cambios
                      </Button>
                    </Grid>
                  </Grid>
                </Box>
              </CardContent>
            </Card>

            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Typography variant="h4" gutterBottom>
                  Cambiar contraseña
                </Typography>
                <Box
                  component="form"
                  onSubmit={passwordForm.handleSubmit((values) => changePassword.mutate(values))}
                >
                  <Grid container spacing={2}>
                    <Grid size={12}>
                      <TextField
                        label="Contraseña actual"
                        type="password"
                        autoComplete="current-password"
                        error={Boolean(passwordForm.formState.errors.current_password)}
                        helperText={passwordForm.formState.errors.current_password?.message}
                        {...passwordForm.register('current_password')}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Nueva contraseña"
                        type="password"
                        autoComplete="new-password"
                        error={Boolean(passwordForm.formState.errors.new_password)}
                        helperText={passwordForm.formState.errors.new_password?.message}
                        {...passwordForm.register('new_password')}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Repetir contraseña"
                        type="password"
                        autoComplete="new-password"
                        error={Boolean(passwordForm.formState.errors.confirm)}
                        helperText={passwordForm.formState.errors.confirm?.message}
                        {...passwordForm.register('confirm')}
                      />
                    </Grid>
                    <Grid size={12}>
                      <Button type="submit" variant="contained" disabled={changePassword.isPending}>
                        Actualizar contraseña
                      </Button>
                    </Grid>
                  </Grid>
                </Box>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}
