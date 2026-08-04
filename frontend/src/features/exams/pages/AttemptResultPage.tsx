/** Resultado del intento con retroalimentación y enlace a la sección a repasar (HU-052). */

import { ArrowBack, Cancel, CheckCircle, MenuBook, Replay } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { AttemptResult, AttemptResultItem } from '@/shared/api/types';
import { ErrorState } from '@/shared/components';
import { QUESTION_TYPE_LABEL } from '@/shared/utils/format';

export default function AttemptResultPage() {
  const { attemptId = '' } = useParams();
  const navigate = useNavigate();

  const result = useQuery({
    queryKey: ['attempt', attemptId, 'result'],
    queryFn: async () =>
      (await api.get<AttemptResult>(endpoints.attempts.result(attemptId))).data,
    // Mientras la IA corrige, el endpoint responde 409: se reintenta.
    retry: (failureCount) => failureCount < 15,
    retryDelay: 3000,
  });

  if (result.isLoading) {
    return (
      <Box sx={{ maxWidth: 640, mx: 'auto', textAlign: 'center', py: 8 }}>
        <CircularProgress sx={{ mb: 2 }} />
        <Typography variant="h4" gutterBottom>
          La IA está corrigiendo tu examen
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Las preguntas abiertas se evalúan con rúbrica; puede tardar unos segundos.
        </Typography>
        <LinearProgress sx={{ mt: 3, borderRadius: 4 }} />
      </Box>
    );
  }

  if (result.isError) return <ErrorState error={result.error} onRetry={result.refetch} />;

  const data = result.data!;

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <IconButton onClick={() => navigate('/mis-cursos')} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          Resultado de la evaluación
        </Typography>
      </Stack>

      <Card
        sx={{
          mb: 3,
          borderLeft: 6,
          borderColor: data.passed ? 'success.main' : 'error.main',
        }}
      >
        <CardContent sx={{ p: 3 }}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ sm: 'center' }}
            spacing={2}
          >
            <Box>
              <Typography variant="h2">{data.exam_title}</Typography>
              <Typography variant="body2" color="text.secondary">
                Intento {data.number}
              </Typography>
            </Box>
            <Stack alignItems={{ xs: 'flex-start', sm: 'flex-end' }}>
              <Typography variant="h1" color={data.passed ? 'success.main' : 'error.main'}>
                {data.percentage.toFixed(0)}%
              </Typography>
              <Chip
                icon={data.passed ? <CheckCircle /> : <Cancel />}
                label={data.passed ? 'Aprobado' : 'Reprobado'}
                color={data.passed ? 'success' : 'error'}
              />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                {data.score} de {data.max_score} puntos
              </Typography>
            </Stack>
          </Stack>

          {data.ai_feedback && (
            <Alert severity={data.passed ? 'success' : 'info'} sx={{ mt: 2.5 }}>
              {data.ai_feedback}
            </Alert>
          )}

          <Stack direction="row" spacing={1.5} sx={{ mt: 2.5 }}>
            <Button
              startIcon={<MenuBook />}
              variant="outlined"
              onClick={() => navigate(`/cursos/${data.training_id}`)}
            >
              Volver al curso
            </Button>
            {!data.passed && (
              <Button
                startIcon={<Replay />}
                variant="contained"
                onClick={() => navigate(`/examenes/${data.exam}/rendir`)}
              >
                Reintentar
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Typography variant="h3" sx={{ mb: 2 }}>
        Detalle por pregunta
      </Typography>

      <Stack spacing={2}>
        {data.results.map((item, index) => (
          <ResultCard
            key={item.question_id}
            item={item}
            index={index}
            trainingId={data.training_id}
            onReview={() => navigate(`/cursos/${data.training_id}`)}
          />
        ))}
      </Stack>
    </Box>
  );
}

function ResultCard({
  item,
  index,
  onReview,
}: {
  item: AttemptResultItem;
  index: number;
  trainingId: string;
  onReview: () => void;
}) {
  return (
    <Card
      variant="outlined"
      sx={{ borderLeft: 4, borderLeftColor: item.is_correct ? 'success.main' : 'error.main' }}
    >
      <CardContent sx={{ p: 2.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          {item.is_correct ? (
            <CheckCircle color="success" />
          ) : (
            <Cancel color="error" />
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
              <Chip label={index + 1} size="small" />
              <Chip label={QUESTION_TYPE_LABEL[item.type]} size="small" variant="outlined" />
              <Chip
                label={`${item.points_awarded} / ${item.points} pts`}
                size="small"
                color={item.is_correct ? 'success' : 'default'}
              />
            </Stack>

            <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
              {item.statement}
            </Typography>

            <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
              <Typography variant="caption" color="text.secondary" display="block">
                Tu respuesta
              </Typography>
              <Typography variant="body2">
                {item.your_answer.text ||
                  (item.your_answer.selected_option_ids.length > 0
                    ? item.correct_options
                        .filter((option) => item.your_answer.selected_option_ids.includes(option.id))
                        .map((option) => option.text)
                        .join(', ') || 'Alternativa incorrecta'
                    : 'Sin respuesta')}
              </Typography>
            </Paper>

            {!item.is_correct && (
              <Paper
                variant="outlined"
                sx={{ p: 1.5, mb: 1.5, borderColor: 'success.main' }}
              >
                <Typography variant="caption" color="success.main" display="block" fontWeight={700}>
                  Respuesta correcta
                </Typography>
                <Typography variant="body2">
                  {item.correct_options.length > 0
                    ? item.correct_options.map((option) => option.text).join(' · ')
                    : item.correct_text}
                </Typography>
              </Paper>
            )}

            {item.feedback && (
              <>
                <Typography variant="caption" color="text.secondary" display="block">
                  Retroalimentación
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  {item.feedback}
                </Typography>
              </>
            )}

            {item.explanation && (
              <>
                <Divider sx={{ my: 1.5 }} />
                <Typography variant="caption" color="text.secondary" display="block">
                  Explicación
                </Typography>
                <Typography variant="body2">{item.explanation}</Typography>
              </>
            )}

            {item.review_hint && (
              <Alert
                severity="info"
                sx={{ mt: 1.5 }}
                action={
                  <Button size="small" onClick={onReview}>
                    Ir al curso
                  </Button>
                }
              >
                {item.review_hint}
              </Alert>
            )}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
