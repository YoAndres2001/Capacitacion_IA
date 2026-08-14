/** Revisión y publicación de un examen (RF-063, RF-068). */

import { Add, ArrowBack, AutoAwesome, CheckCircle, Delete, Edit, Publish } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { ExamDetail, Question } from '@/shared/api/types';
import { ConfirmDialog, ErrorState, Loading, PageHeader, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { ExamFormDialog } from '@/features/exams/components/ExamFormDialog';
import { QuestionFormDialog } from '@/features/exams/components/QuestionFormDialog';
import { LEVEL_LABEL, QUESTION_TYPE_LABEL, formatDuration } from '@/shared/utils/format';

export default function ExamEditorPage() {
  const { examId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // `undefined` = cerrado; `null` = pregunta nueva; objeto = edición.
  const [questionDialog, setQuestionDialog] = useState<Question | null | undefined>(undefined);

  const exam = useQuery({
    queryKey: ['exam', examId],
    queryFn: async () => (await api.get<ExamDetail>(endpoints.exams.detail(examId))).data,
    // Solo tiene sentido esperar preguntas cuando la IA las está redactando;
    // en un examen manual el sondeo sería un bucle infinito de peticiones.
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && data.generated_by_ai && data.questions.length === 0 ? 4000 : false;
    },
  });

  const publish = useMutation({
    mutationFn: () => api.post(endpoints.exams.publish(examId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['exam', examId] });
      snackbar.success('Examen publicado. Ya está disponible para los estudiantes.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const removeQuestion = useMutation({
    mutationFn: (questionId: string) => api.delete(endpoints.questions.detail(questionId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['exam', examId] });
      setConfirmDelete(null);
      snackbar.info('Pregunta eliminada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (exam.isLoading) return <Loading />;
  if (exam.isError) return <ErrorState error={exam.error} onRetry={exam.refetch} />;

  const data = exam.data!;
  const generating = data.questions.length === 0 && data.generated_by_ai;

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton onClick={() => navigate(-1)} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          {data.training_title}
        </Typography>
      </Stack>

      <PageHeader
        title={data.title}
        subtitle={`${data.question_count} preguntas · ${data.total_points} puntos · aprobación ${data.passing_score}%`}
        actions={
          <>
            <StatusChip status={data.status} />
            {data.can_edit_questions && (
              <>
                <Button
                  variant="outlined"
                  startIcon={<Edit />}
                  onClick={() => setSettingsOpen(true)}
                >
                  Editar
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Add />}
                  onClick={() => setQuestionDialog(null)}
                >
                  Agregar pregunta
                </Button>
              </>
            )}
            {data.status === 'DRAFT' && (
              <Button
                variant="contained"
                startIcon={<Publish />}
                onClick={() => publish.mutate()}
                disabled={data.questions.length === 0 || publish.isPending}
              >
                Publicar
              </Button>
            )}
          </>
        }
      />

      {generating && (
        <Alert severity="info" icon={<AutoAwesome />} sx={{ mb: 3 }}>
          La IA está generando las preguntas. Esta página se actualiza sola cuando terminen.
        </Alert>
      )}

      {!data.can_edit_questions && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          El examen está publicado y ya tiene intentos registrados: las preguntas quedaron
          bloqueadas para no invalidar los resultados existentes.
        </Alert>
      )}

      {data.questions.length === 0 && !generating ? (
        <Card>
          <CardContent sx={{ py: 6, textAlign: 'center' }}>
            <Typography variant="h4" gutterBottom>
              Todavía no hay preguntas
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Agrega las preguntas una a una. El examen no se puede publicar hasta que tenga al
              menos una con su respuesta correcta definida.
            </Typography>
            <Button variant="contained" startIcon={<Add />} onClick={() => setQuestionDialog(null)}>
              Agregar pregunta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={2}>
          {data.questions.map((question, index) => (
            <QuestionCard
              key={question.id}
              question={question}
              index={index}
              editable={data.can_edit_questions}
              onEdit={() => setQuestionDialog(question)}
              onDelete={() => setConfirmDelete(question.id)}
            />
          ))}
        </Stack>
      )}

      {settingsOpen && (
        <ExamFormDialog open exam={data} onClose={() => setSettingsOpen(false)} />
      )}
      {questionDialog !== undefined && (
        <QuestionFormDialog
          open
          examId={examId}
          question={questionDialog}
          onClose={() => setQuestionDialog(undefined)}
        />
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Eliminar pregunta"
        message="La pregunta se eliminará del examen. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        destructive
        loading={removeQuestion.isPending}
        onConfirm={() => confirmDelete && removeQuestion.mutate(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </Box>
  );
}

function QuestionCard({
  question,
  index,
  editable,
  onEdit,
  onDelete,
}: {
  question: Question;
  index: number;
  editable: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <Card variant="outlined">
      <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Chip label={index + 1} size="small" />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
              <Chip label={QUESTION_TYPE_LABEL[question.type]} size="small" color="primary" variant="outlined" />
              <Chip label={LEVEL_LABEL[question.level]} size="small" variant="outlined" />
              <Chip label={`${question.points} pts`} size="small" variant="outlined" />
              {question.generated_by_ai && (
                <Chip
                  label="IA"
                  size="small"
                  color="secondary"
                  icon={<AutoAwesome sx={{ fontSize: 13 }} />}
                />
              )}
            </Stack>

            <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
              {question.statement}
            </Typography>

            {question.options.length > 0 && (
              <Stack spacing={0.75} sx={{ mb: 1.5 }}>
                {question.options.map((option) => (
                  <Stack key={option.id} direction="row" spacing={1} alignItems="flex-start">
                    <CheckCircle
                      fontSize="small"
                      color={option.is_correct ? 'success' : 'disabled'}
                      sx={{ mt: 0.25 }}
                    />
                    <Typography
                      variant="body2"
                      color={option.is_correct ? 'success.main' : 'text.primary'}
                      fontWeight={option.is_correct ? 600 : 400}
                    >
                      {option.text}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            )}

            {question.correct_text && (
              <Alert severity="success" variant="outlined" sx={{ mb: 1.5, py: 0.5 }}>
                <Typography variant="caption" fontWeight={700} display="block">
                  Respuesta esperada
                </Typography>
                <Typography variant="body2">{question.correct_text}</Typography>
              </Alert>
            )}

            {question.explanation && (
              <>
                <Divider sx={{ my: 1.5 }} />
                <Typography variant="caption" color="text.secondary" display="block">
                  Explicación
                </Typography>
                <Typography variant="body2">{question.explanation}</Typography>
              </>
            )}

            {question.source_material_title && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: 'block' }}>
                Fuente: {question.source_material_title}
                {question.source_start_time != null &&
                  ` · minuto ${formatDuration(question.source_start_time)}`}
                {question.source_page != null && ` · página ${question.source_page}`}
              </Typography>
            )}
          </Box>

          {editable && (
            <Stack direction="row" spacing={0.5}>
              <Tooltip title="Editar pregunta">
                <IconButton size="small" onClick={onEdit}>
                  <Edit fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Eliminar pregunta">
                <IconButton size="small" color="error" onClick={onDelete}>
                  <Delete fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
