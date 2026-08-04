/** Notificaciones en vivo entregadas por el contenedor `websocket`. */

import { Notifications } from '@mui/icons-material';
import {
  Badge,
  Box,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popover,
  Tooltip,
  Typography,
} from '@mui/material';
import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWebSocket } from '@/shared/hooks/useWebSocket';
import type { WsMessage } from '@/shared/api/types';

interface Notification {
  id: string;
  title: string;
  detail: string;
  path?: string;
  at: Date;
}

export function NotificationCenter() {
  const [items, setItems] = useState<Notification[]>([]);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();

  const handleMessage = useCallback((message: WsMessage) => {
    if (message.type !== 'notification') return;

    const notification = describe(message);
    if (notification) {
      setItems((previous) => [notification, ...previous].slice(0, 25));
    }
  }, []);

  const { status } = useWebSocket({ path: 'notifications', onMessage: handleMessage });

  return (
    <>
      <Tooltip title={status === 'open' ? 'Notificaciones' : 'Reconectando…'}>
        <IconButton onClick={(event) => setAnchorEl(event.currentTarget)} aria-label="Notificaciones">
          <Badge badgeContent={items.length} color="error" max={9}>
            <Notifications />
          </Badge>
        </IconButton>
      </Tooltip>

      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Box sx={{ width: 340 }}>
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography variant="subtitle2">Notificaciones</Typography>
          </Box>
          <Divider />
          {items.length === 0 ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                No tienes notificaciones nuevas.
              </Typography>
            </Box>
          ) : (
            <List dense sx={{ maxHeight: 380, overflowY: 'auto' }}>
              {items.map((item) => (
                <ListItemButton
                  key={item.id}
                  onClick={() => {
                    if (item.path) navigate(item.path);
                    setAnchorEl(null);
                  }}
                >
                  <ListItemText
                    primary={item.title}
                    secondary={item.detail}
                    primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }}
                    secondaryTypographyProps={{ fontSize: 12 }}
                  />
                </ListItemButton>
              ))}
            </List>
          )}
        </Box>
      </Popover>
    </>
  );
}

function describe(message: Extract<WsMessage, { type: 'notification' }>): Notification | null {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const event = String(message.event ?? '');

  switch (event) {
    case 'attempt.graded':
      return {
        id,
        title: message.passed ? 'Examen aprobado' : 'Examen corregido',
        detail: `Puntaje: ${Number(message.score ?? 0).toFixed(0)}%`,
        path: `/intentos/${message.attempt_id}`,
        at: new Date(),
      };
    case 'exam.generated':
      return {
        id,
        title: 'Examen generado por IA',
        detail: `${message.questions ?? 0} preguntas listas para revisar`,
        path: `/examenes/${message.exam_id}/editor`,
        at: new Date(),
      };
    case 'MaterialProcessed':
      return {
        id,
        title: 'Material procesado',
        detail: 'El contenido ya está disponible para consultas.',
        path: `/materiales/${message.material_id}`,
        at: new Date(),
      };
    case 'UserEnrolled':
      return {
        id,
        title: 'Nueva capacitación asignada',
        detail: 'Revisa tus cursos pendientes.',
        path: '/mis-cursos',
        at: new Date(),
      };
    default:
      return null;
  }
}
