import { zodResolver } from '@hookform/resolvers/zod';
import { School, Visibility, VisibilityOff } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  InputAdornment,
  Link,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link as RouterLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { errorMessage } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';

const schema = z.object({
  email: z.string().min(1, 'El correo es obligatorio.').email('Formato de correo inválido.'),
  password: z.string().min(1, 'La contraseña es obligatoria.'),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const expired = new URLSearchParams(location.search).get('expired') === '1';

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  if (!loading && isAuthenticated) return <Navigate to="/" replace />;

  const onSubmit = async (values: FormValues) => {
    setServerError('');
    try {
      const user = await login(values.email, values.password);
      navigate(user.permissions.manage_content ? '/admin' : '/mis-cursos', { replace: true });
    } catch (error) {
      setServerError(errorMessage(error));
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        p: 2,
        background: (theme) =>
          theme.palette.mode === 'light'
            ? 'linear-gradient(135deg, #e3f2fd 0%, #f4f6f9 60%)'
            : 'linear-gradient(135deg, #0f1419 0%, #161c24 60%)',
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 430 }} elevation={3}>
        <CardContent sx={{ p: 4 }}>
          <Stack alignItems="center" spacing={1} sx={{ mb: 3 }}>
            <School sx={{ fontSize: 44, color: 'primary.main' }} />
            <Typography variant="h2">Capacita IA</Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              Plataforma de capacitaciones con Inteligencia Artificial
            </Typography>
          </Stack>

          {expired && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Tu sesión expiró. Vuelve a iniciar sesión.
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
                label="Correo electrónico"
                type="email"
                autoComplete="username"
                autoFocus
                error={Boolean(errors.email)}
                helperText={errors.email?.message}
                {...register('email')}
              />
              <TextField
                label="Contraseña"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                error={Boolean(errors.password)}
                helperText={errors.password?.message}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowPassword((value) => !value)}
                        edge="end"
                        aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
                {...register('password')}
              />
              <Button type="submit" variant="contained" size="large" disabled={isSubmitting}>
                {isSubmitting ? 'Ingresando…' : 'Ingresar'}
              </Button>
              <Link
                component={RouterLink}
                to="/forgot-password"
                variant="body2"
                textAlign="center"
                underline="hover"
              >
                ¿Olvidaste tu contraseña?
              </Link>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
