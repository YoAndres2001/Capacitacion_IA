import { zodResolver } from '@hookform/resolvers/zod';
import { MarkEmailRead } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Link,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link as RouterLink } from 'react-router-dom';
import { z } from 'zod';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';

const schema = z.object({
  email: z.string().email('Formato de correo inválido.'),
});

type FormValues = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const [serverError, setServerError] = useState('');

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } });

  const onSubmit = async (values: FormValues) => {
    setServerError('');
    try {
      await api.post(endpoints.auth.passwordReset, values);
      setSent(true);
    } catch (error) {
      setServerError(errorMessage(error));
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
      <Card sx={{ width: '100%', maxWidth: 430 }} elevation={3}>
        <CardContent sx={{ p: 4 }}>
          {sent ? (
            <Stack spacing={2} alignItems="center" textAlign="center">
              <MarkEmailRead sx={{ fontSize: 52, color: 'success.main' }} />
              <Typography variant="h3">Revisa tu correo</Typography>
              <Typography variant="body2" color="text.secondary">
                Si la dirección está registrada, enviamos un enlace para restablecer la contraseña.
                El enlace es de un solo uso y expira en 1 hora.
              </Typography>
              <Button component={RouterLink} to="/login" variant="contained" fullWidth>
                Volver al inicio de sesión
              </Button>
            </Stack>
          ) : (
            <>
              <Typography variant="h2" gutterBottom>
                Recuperar contraseña
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Ingresa tu correo y te enviaremos un enlace para crear una nueva contraseña.
              </Typography>

              {serverError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {serverError}
                </Alert>
              )}

              <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
                <Stack spacing={2}>
                  <TextField
                    label="Correo electrónico"
                    type="email"
                    autoFocus
                    error={Boolean(errors.email)}
                    helperText={errors.email?.message}
                    {...register('email')}
                  />
                  <Button type="submit" variant="contained" size="large" disabled={isSubmitting}>
                    {isSubmitting ? 'Enviando…' : 'Enviar enlace'}
                  </Button>
                  <Link
                    component={RouterLink}
                    to="/login"
                    variant="body2"
                    textAlign="center"
                    underline="hover"
                  >
                    Volver al inicio de sesión
                  </Link>
                </Stack>
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
