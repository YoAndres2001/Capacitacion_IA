/** Componentes reutilizables de la interfaz. */

import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import type { ChipProps } from '@mui/material';
import type { ReactNode } from 'react';
import { STATUS_LABEL } from '@/shared/utils/format';
import { statusColor, trainingStatusColor } from '@/app/theme';

// ── Encabezado de página ─────────────────────────────────────
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      justifyContent="space-between"
      alignItems={{ xs: 'stretch', sm: 'center' }}
      spacing={2}
      sx={{ mb: 3 }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h1">{title}</Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {actions && (
        // Varias páginas pasan tres o cuatro acciones: en un teléfono no caben
        // en una fila, así que se reparten en varias sin desbordar la pantalla.
        <Stack
          direction="row"
          spacing={1}
          flexWrap="wrap"
          useFlexGap
          sx={{ flexShrink: 0, alignItems: 'center' }}
        >
          {actions}
        </Stack>
      )}
    </Stack>
  );
}

// ── Estados de carga y vacío ─────────────────────────────────
export function Loading({ label = 'Cargando…' }: { label?: string }) {
  return (
    <Stack alignItems="center" justifyContent="center" spacing={2} sx={{ py: 8 }}>
      <CircularProgress />
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
    </Stack>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: { xs: 3, sm: 4, md: 6 }, textAlign: 'center', borderStyle: 'dashed' }}
    >
      {icon && (
        <Box sx={{ mb: 2, color: 'text.disabled', '& svg': { fontSize: { xs: 44, sm: 56 } } }}>
          {icon}
        </Box>
      )}
      <Typography variant="h4" gutterBottom>
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: 460, mx: 'auto' }}>
          {description}
        </Typography>
      )}
      {action}
    </Paper>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Ocurrió un error inesperado.';
  return (
    <Alert
      severity="error"
      action={
        onRetry && (
          <Button color="inherit" size="small" onClick={onRetry}>
            Reintentar
          </Button>
        )
      }
    >
      {message}
    </Alert>
  );
}

// ── Chips de estado ──────────────────────────────────────────
export function StatusChip({
  status,
  size = 'small',
}: {
  status: string;
  size?: ChipProps['size'];
}) {
  const color =
    (statusColor as Record<string, ChipProps['color']>)[status] ??
    (trainingStatusColor as Record<string, ChipProps['color']>)[status] ??
    'default';

  return <Chip label={STATUS_LABEL[status] ?? status} color={color} size={size} variant="filled" />;
}

// ── Progreso ─────────────────────────────────────────────────
export function ProgressBar({
  value,
  label,
  color = 'primary',
}: {
  value: number;
  label?: string;
  color?: 'primary' | 'success' | 'warning' | 'error';
}) {
  return (
    <Box sx={{ width: '100%' }}>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          {label ?? 'Avance'}
        </Typography>
        <Typography variant="caption" fontWeight={600}>
          {value.toFixed(0)}%
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={Math.min(100, Math.max(0, value))}
        color={color}
        sx={{ height: 8, borderRadius: 4 }}
      />
    </Box>
  );
}

// ── Confirmación ─────────────────────────────────────────────
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirmar',
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {typeof message === 'string' ? <DialogContentText>{message}</DialogContentText> : message}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCancel} disabled={loading}>
          Cancelar
        </Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color={destructive ? 'error' : 'primary'}
          disabled={loading}
        >
          {loading ? 'Procesando…' : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Tarjeta de métrica ───────────────────────────────────────
export function StatCard({
  label,
  value,
  hint,
  icon,
  color = 'primary.main',
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  color?: string;
}) {
  return (
    <Paper sx={{ p: { xs: 1.75, sm: 2.5 }, height: '100%' }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          {/* En dos columnas de teléfono la etiqueta no cabe en una línea:
              se deja envolver en vez de recortarla con puntos suspensivos. */}
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.3, wordBreak: 'break-word' }}
          >
            {label}
          </Typography>
          <Typography variant="h2" sx={{ mt: 0.5, mb: hint ? 0.5 : 0 }}>
            {value}
          </Typography>
          {hint && (
            <Typography variant="caption" color="text.secondary">
              {hint}
            </Typography>
          )}
        </Box>
        {icon && (
          <Box
            sx={{
              color,
              opacity: 0.85,
              flexShrink: 0,
              // El icono decorativo estorba cuando el ancho es el recurso
              // escaso: desaparece en teléfonos.
              display: { xs: 'none', sm: 'block' },
              '& svg': { fontSize: 34 },
            }}
          >
            {icon}
          </Box>
        )}
      </Stack>
    </Paper>
  );
}
