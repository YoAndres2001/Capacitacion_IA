/**
 * Chat RAG de la capacitación, con streaming por WebSocket y citas clickeables.
 *
 * Cuando el socket está disponible, la respuesta llega token a token; si no,
 * cae automáticamente al endpoint HTTP síncrono.
 */

import { AutoAwesome, Send, SmartToy, ThumbDown, ThumbUp } from '@mui/icons-material';
import {
  Alert,
  Avatar,
  Box,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { ChatMessage, ChatSession, Citation, WsMessage } from '@/shared/api/types';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { useWebSocket } from '@/shared/hooks/useWebSocket';

const SUGGESTIONS = [
  '¿De qué trata esta capacitación?',
  'Resume el capítulo 1',
  'Explícamelo como si fuera principiante',
  'Dame un ejemplo práctico',
];

type Level = 'beginner' | 'intermediate' | 'advanced';

interface Props {
  trainingId: string;
  /** Salta el reproductor al segundo indicado por una cita. */
  onSeek?: (materialId: string, seconds: number) => void;
}

export function ChatPanel({ trainingId, onSeek }: Props) {
  const snackbar = useSnackbar();
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState('');
  const [level, setLevel] = useState<Level>('intermediate');
  const [streaming, setStreaming] = useState('');
  const [pending, setPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Una conversación por capacitación: se reutiliza la última o se crea una.
  const session = useQuery({
    queryKey: ['chat', trainingId],
    queryFn: async () => {
      const { data } = await api.get<ChatSession[]>(endpoints.trainings.chatSessions(trainingId));
      if (data.length > 0) return data[0];
      const created = await api.post<ChatSession>(endpoints.trainings.chatSessions(trainingId));
      return created.data;
    },
  });

  const sessionId = session.data?.id ?? '';

  const messages = useQuery({
    queryKey: ['chat', trainingId, sessionId, 'messages'],
    queryFn: async () => (await api.get<ChatMessage[]>(endpoints.chat.messages(sessionId))).data,
    enabled: Boolean(sessionId),
  });

  const handleSocket = useCallback(
    (message: WsMessage) => {
      switch (message.type) {
        case 'thinking':
          setStreaming('');
          break;
        case 'token':
          setStreaming((previous) => previous + message.content);
          break;
        case 'answer.done':
          setStreaming('');
          setPending(false);
          void queryClient.invalidateQueries({
            queryKey: ['chat', trainingId, sessionId, 'messages'],
          });
          break;
        case 'error':
          setStreaming('');
          setPending(false);
          snackbar.error(message.message);
          break;
        default:
          break;
      }
    },
    [queryClient, trainingId, sessionId, snackbar],
  );

  const socket = useWebSocket({
    path: sessionId ? `chat/${sessionId}` : null,
    onMessage: handleSocket,
    enabled: Boolean(sessionId),
  });

  // Respaldo HTTP cuando el WebSocket no está disponible.
  const askHttp = useMutation({
    mutationFn: (content: string) =>
      api.post<ChatMessage>(endpoints.chat.ask(sessionId), { content, level }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['chat', trainingId, sessionId, 'messages'],
      });
    },
    onError: (error) => snackbar.error(errorMessage(error)),
    onSettled: () => setPending(false),
  });

  const feedback = useMutation({
    mutationFn: ({ messageId, value }: { messageId: string; value: 1 | -1 }) =>
      api.post(endpoints.chat.feedback(sessionId, messageId), { feedback: value }),
    onSuccess: () => snackbar.success('Gracias por tu evaluación.'),
  });

  const send = useCallback(
    (text: string) => {
      const content = text.trim();
      if (!content || !sessionId || pending) return;

      setQuestion('');
      setPending(true);
      setStreaming('');

      const sentByWs = socket.send({ type: 'question', content, level });
      if (!sentByWs) askHttp.mutate(content);
    },
    [sessionId, pending, socket, level, askHttp],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.data, streaming]);

  const history = useMemo(() => messages.data ?? [], [messages.data]);

  return (
    <Stack sx={{ height: '100%', minHeight: 0 }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider' }}
      >
        <SmartToy color="primary" />
        <Typography variant="subtitle1" sx={{ flex: 1 }}>
          Tutor IA
        </Typography>
        <Select
          size="small"
          value={level}
          onChange={(event) => setLevel(event.target.value as Level)}
          sx={{ minWidth: 132 }}
        >
          <MenuItem value="beginner">Principiante</MenuItem>
          <MenuItem value="intermediate">Intermedio</MenuItem>
          <MenuItem value="advanced">Avanzado</MenuItem>
        </Select>
      </Stack>

      <Box sx={{ flex: 1, overflowY: 'auto', p: 2, minHeight: 0 }}>
        {history.length === 0 && !streaming && (
          <Stack spacing={2} sx={{ py: 3 }}>
            <Alert severity="info" icon={<AutoAwesome />}>
              Pregunta lo que quieras sobre esta capacitación. La IA responde{' '}
              <strong>solo con el contenido del curso</strong> y cita el minuto o la página exacta.
            </Alert>
            <Typography variant="caption" color="text.secondary">
              Sugerencias:
            </Typography>
            <Stack spacing={1}>
              {SUGGESTIONS.map((suggestion) => (
                <Chip
                  key={suggestion}
                  label={suggestion}
                  onClick={() => send(suggestion)}
                  variant="outlined"
                  sx={{ justifyContent: 'flex-start', height: 'auto', py: 0.75 }}
                />
              ))}
            </Stack>
          </Stack>
        )}

        <Stack spacing={2}>
          {history.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onSeek={onSeek}
              onFeedback={(value) => feedback.mutate({ messageId: message.id, value })}
            />
          ))}

          {streaming && (
            <Stack direction="row" spacing={1.5}>
              <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main' }}>
                <SmartToy sx={{ fontSize: 17 }} />
              </Avatar>
              <Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {streaming}
                  <Box component="span" sx={{ opacity: 0.5 }}>
                    ▌
                  </Box>
                </Typography>
              </Paper>
            </Stack>
          )}

          {pending && !streaming && (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main' }}>
                <SmartToy sx={{ fontSize: 17 }} />
              </Avatar>
              <CircularProgress size={16} />
              <Typography variant="caption" color="text.secondary">
                Buscando en el material…
              </Typography>
            </Stack>
          )}
        </Stack>
        <div ref={bottomRef} />
      </Box>

      <Divider />
      <Box sx={{ p: 1.5 }}>
        <Stack direction="row" spacing={1}>
          <TextField
            placeholder="Escribe tu pregunta…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                send(question);
              }
            }}
            multiline
            maxRows={4}
            disabled={!sessionId || pending}
          />
          <IconButton
            color="primary"
            onClick={() => send(question)}
            disabled={!question.trim() || pending || !sessionId}
            aria-label="Enviar pregunta"
          >
            <Send />
          </IconButton>
        </Stack>
        {socket.status !== 'open' && (
          <Typography variant="caption" color="text.secondary">
            Modo sin streaming (la respuesta llegará completa).
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

function MessageBubble({
  message,
  onSeek,
  onFeedback,
}: {
  message: ChatMessage;
  onSeek?: (materialId: string, seconds: number) => void;
  onFeedback: (value: 1 | -1) => void;
}) {
  const isUser = message.role === 'USER';

  if (isUser) {
    return (
      <Stack direction="row" justifyContent="flex-end">
        <Paper
          sx={{
            p: 1.5,
            maxWidth: '85%',
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
          }}
        >
          <Typography variant="body2">{message.content}</Typography>
        </Paper>
      </Stack>
    );
  }

  return (
    <Stack direction="row" spacing={1.5}>
      <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main' }}>
        <SmartToy sx={{ fontSize: 17 }} />
      </Avatar>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {message.content}
          </Typography>

          {!message.grounded && (
            <Chip
              label="Sin información en el material"
              size="small"
              color="warning"
              sx={{ mt: 1 }}
            />
          )}

          {message.citations.length > 0 && (
            <Box sx={{ mt: 1.5 }}>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                Fuentes:
              </Typography>
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                {message.citations.map((citation, index) => (
                  <CitationChip
                    key={citation.id ?? index}
                    index={index + 1}
                    citation={citation}
                    onSeek={onSeek}
                  />
                ))}
              </Stack>
            </Box>
          )}
        </Paper>

        <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
          <Tooltip title="Respuesta útil">
            <IconButton
              size="small"
              onClick={() => onFeedback(1)}
              color={message.feedback === 1 ? 'primary' : 'default'}
            >
              <ThumbUp sx={{ fontSize: 15 }} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Respuesta poco útil">
            <IconButton
              size="small"
              onClick={() => onFeedback(-1)}
              color={message.feedback === -1 ? 'error' : 'default'}
            >
              <ThumbDown sx={{ fontSize: 15 }} />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>
    </Stack>
  );
}

function CitationChip({
  index,
  citation,
  onSeek,
}: {
  index: number;
  citation: Citation;
  onSeek?: (materialId: string, seconds: number) => void;
}) {
  const materialId = citation.material_id ?? citation.material;
  const clickable = Boolean(onSeek && materialId && citation.start_time !== null);

  return (
    <Chip
      label={`[${index}] ${citation.label}`}
      size="small"
      variant="outlined"
      color={clickable ? 'primary' : 'default'}
      onClick={
        clickable
          ? () => onSeek!(String(materialId), citation.start_time as number)
          : undefined
      }
      sx={{ maxWidth: '100%' }}
    />
  );
}
