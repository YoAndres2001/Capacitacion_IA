import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';

const schema = z
  .object({
    new_password: z
      .string()
      .min(8, 'Debe tener al menos 8 caracteres.')
      .regex(/[A-Za-z]/, 'Debe incluir al menos una letra.')
      .regex(/\d/, 'Debe incluir al menos un número.'),
    confirm: z.string(),
  })
  .refine((data) => data.new_password === data.confirm, {
    message: 'Las contraseñas no coinciden.',
    path: ['confirm'],
  });

type FormValues = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState('');

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { new_password: '', confirm: '' },
  });

  const onSubmit = async (values: FormValues) => {
    setServerError('');
    try {
      await api.post(endpoints.auth.passwordResetConfirm, {
        token,
        new_password: values.new_password,
      });
      setDone(true);
    } catch (error) {
      setServerError(errorMessage(error));
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
      <Card sx={{ width: '100%', maxWidth: 430 }} elevation={3}>
        <CardContent sx={{ p: 4 }}>
          {done ? (
            <Stack spacing={2} alignItems="center" textAlign="center">
              <CheckCircle sx={{ fontSize: 52, color: 'success.main' }} />
              <Typography variant="h3">Contraseña actualizada</Typography>
              <Typography variant="body2" color="text.secondary">
                Ya puedes ingresar con tu nueva contraseña.
              </Typography>
              <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                Ir al inicio de sesión
              </Button>
            </Stack>
          ) : (
            <>
              <Typography variant="h2" gutterBottom>
                Nueva contraseña
              </Typography>

              {!token && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  El enlace no incluye un token válido. Solicita uno nuevo.
                </Alert>
              )}
              {serverError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {serverError}
                </Alert>
              )}

              <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
                <Stack spacing={2}>
                  <TextField
                    label="Nueva contraseña"
                    type="password"
                    autoComplete="new-password"
                    error={Boolean(errors.new_password)}
                    helperText={errors.new_password?.message}
                    {...register('new_password')}
                  />
                  <TextField
                    label="Repetir contraseña"
                    type="password"
                    autoComplete="new-password"
                    error={Boolean(errors.confirm)}
                    helperText={errors.confirm?.message}
                    {...register('confirm')}
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    size="large"
                    disabled={isSubmitting || !token}
                  >
                    {isSubmitting ? 'Guardando…' : 'Guardar contraseña'}
                  </Button>
                </Stack>
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
