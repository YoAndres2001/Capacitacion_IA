/** Constructor de la capacitación: módulos, lecciones, material y evaluaciones. */

import {
  Add,
  ArrowBack,
  AutoAwesome,
  Delete,
  ExpandMore,
  People,
  Publish,
  Quiz,
  Unpublished,
} from '@mui/icons-material';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Exam, Lesson, TrainingDetail, TrainingModule } from '@/shared/api/types';
import { ConfirmDialog, ErrorState, Loading, PageHeader, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { EnrollmentPanel } from '@/features/trainings/components/EnrollmentPanel';
import { ExamGeneratorDialog } from '@/features/exams/components/ExamGeneratorDialog';
import { MaterialUploader } from '@/features/trainings/components/MaterialUploader';
import { formatDurationLong } from '@/shared/utils/format';

export default function TrainingBuilderPage() {
  const { trainingId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const tab = params.get('tab') ?? 'content';
  const [moduleDialog, setModuleDialog] = useState(false);
  const [lessonDialog, setLessonDialog] = useState<string | null>(null);
  const [generatorOpen, setGeneratorOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{ kind: 'module' | 'lesson'; id: string } | null>(
    null,
  );

  const training = useQuery({
    queryKey: ['training', trainingId],
    queryFn: async () => (await api.get<TrainingDetail>(endpoints.trainings.tree(trainingId))).data,
  });

  const exams = useQuery({
    queryKey: ['training', trainingId, 'exams'],
    queryFn: async () => (await api.get<Exam[]>(endpoints.trainings.exams(trainingId))).data,
    enabled: tab === 'exams',
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['training', trainingId] });

  const publish = useMutation({
    mutationFn: (action: 'publish' | 'unpublish') =>
      api.post(
        action === 'publish'
          ? endpoints.trainings.publish(trainingId)
          : endpoints.trainings.unpublish(trainingId),
      ),
    onSuccess: async (_, action) => {
      await refresh();
      snackbar.success(action === 'publish' ? 'Capacitación publicada.' : 'Capacitación despublicada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const createModule = useMutation({
    mutationFn: (title: string) => api.post(endpoints.trainings.modules(trainingId), { title }),
    onSuccess: async () => {
      await refresh();
      setModuleDialog(false);
      snackbar.success('Módulo agregado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const createLesson = useMutation({
    mutationFn: ({ moduleId, ...payload }: { moduleId: string; title: string; type: string }) =>
      api.post(endpoints.modules.lessons(moduleId), payload),
    onSuccess: async () => {
      await refresh();
      setLessonDialog(null);
      snackbar.success('Lección agregada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: ({ kind, id }: { kind: 'module' | 'lesson'; id: string }) =>
      api.delete(kind === 'module' ? endpoints.modules.detail(id) : endpoints.lessons.detail(id)),
    onSuccess: async () => {
      await refresh();
      setConfirmDelete(null);
      snackbar.info('Elemento eliminado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (training.isLoading) return <Loading label="Cargando capacitación…" />;
  if (training.isError) return <ErrorState error={training.error} onRetry={training.refetch} />;

  const data = training.data!;

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton onClick={() => navigate('/capacitaciones')} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          {data.project_name}
        </Typography>
      </Stack>

      <PageHeader
        title={data.title}
        subtitle={data.description || 'Sin descripción'}
        actions={
          <>
            <StatusChip status={data.status} />
            {data.status === 'DRAFT' ? (
              <Tooltip
                title={
                  data.can_be_published
                    ? 'Publicar'
                    : 'Necesita al menos una lección con material disponible'
                }
              >
                <span>
                  <Button
                    variant="contained"
                    startIcon={<Publish />}
                    disabled={!data.can_be_published || publish.isPending}
                    onClick={() => publish.mutate('publish')}
                  >
                    Publicar
                  </Button>
                </span>
              </Tooltip>
            ) : (
              <Button
                variant="outlined"
                startIcon={<Unpublished />}
                onClick={() => publish.mutate('unpublish')}
              >
                Despublicar
              </Button>
            )}
          </>
        }
      />

      {data.status === 'DRAFT' && !data.can_be_published && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Para publicar, sube al menos un video o documento y espera a que la IA termine de
          procesarlo (estado <strong>Disponible</strong>).
        </Alert>
      )}

      <Tabs
        value={tab}
        onChange={(_, value) => setParams({ tab: value })}
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label="Contenido" value="content" />
        <Tab label="Evaluaciones" value="exams" icon={<Quiz />} iconPosition="start" />
        <Tab label="Participantes" value="enrollments" icon={<People />} iconPosition="start" />
      </Tabs>

      {tab === 'content' && (
        <Box>
          <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
            <Button startIcon={<Add />} variant="outlined" onClick={() => setModuleDialog(true)}>
              Agregar módulo
            </Button>
          </Stack>

          {data.modules.length === 0 ? (
            <Card>
              <CardContent sx={{ py: 6, textAlign: 'center' }}>
                <Typography variant="h4" gutterBottom>
                  Empieza por el primer módulo
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  Estructura la capacitación en módulos y, dentro de cada uno, agrega lecciones con
                  su video o documento.
                </Typography>
                <Button variant="contained" startIcon={<Add />} onClick={() => setModuleDialog(true)}>
                  Agregar módulo
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Stack spacing={1.5}>
              {data.modules.map((module, index) => (
                <ModuleAccordion
                  key={module.id}
                  module={module}
                  index={index}
                  onAddLesson={() => setLessonDialog(module.id)}
                  onDeleteModule={() => setConfirmDelete({ kind: 'module', id: module.id })}
                  onDeleteLesson={(lessonId) => setConfirmDelete({ kind: 'lesson', id: lessonId })}
                  onChanged={refresh}
                />
              ))}
            </Stack>
          )}
        </Box>
      )}

      {tab === 'exams' && (
        <Box>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary">
              La IA genera el examen en borrador; tú lo revisas y lo publicas.
            </Typography>
            <Button
              variant="contained"
              startIcon={<AutoAwesome />}
              onClick={() => setGeneratorOpen(true)}
            >
              Generar con IA
            </Button>
          </Stack>

          {(exams.data?.length ?? 0) === 0 ? (
            <Card>
              <CardContent sx={{ py: 6, textAlign: 'center' }}>
                <Quiz sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
                <Typography variant="h4" gutterBottom>
                  Sin evaluaciones
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Genera un examen automáticamente a partir del material procesado.
                </Typography>
              </CardContent>
            </Card>
          ) : (
            <Stack spacing={1.5}>
              {exams.data!.map((exam) => (
                <Card key={exam.id} variant="outlined">
                  <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      justifyContent="space-between"
                      alignItems={{ sm: 'center' }}
                      spacing={1.5}
                    >
                      <Box>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="subtitle1">{exam.title}</Typography>
                          {exam.generated_by_ai && (
                            <Chip
                              label="IA"
                              size="small"
                              color="secondary"
                              icon={<AutoAwesome sx={{ fontSize: 14 }} />}
                            />
                          )}
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {exam.question_count} preguntas · {exam.total_points} puntos · aprobación{' '}
                          {exam.passing_score}% · {exam.max_attempts} intentos
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <StatusChip status={exam.status} />
                        <Button
                          size="small"
                          component={RouterLink}
                          to={`/examenes/${exam.id}/editor`}
                        >
                          Revisar
                        </Button>
                        {exam.status === 'PUBLISHED' && (
                          <Button
                            size="small"
                            component={RouterLink}
                            to={`/examenes/${exam.id}/resultados`}
                          >
                            Resultados
                          </Button>
                        )}
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>
              ))}
            </Stack>
          )}
        </Box>
      )}

      {tab === 'enrollments' && <EnrollmentPanel trainingId={trainingId} />}

      {/* Diálogos */}
      <ModuleDialog
        open={moduleDialog}
        onClose={() => setModuleDialog(false)}
        onSubmit={(title) => createModule.mutate(title)}
        loading={createModule.isPending}
      />
      <LessonDialog
        open={lessonDialog !== null}
        onClose={() => setLessonDialog(null)}
        onSubmit={(title, type) =>
          lessonDialog && createLesson.mutate({ moduleId: lessonDialog, title, type })
        }
        loading={createLesson.isPending}
      />
      <ExamGeneratorDialog
        open={generatorOpen}
        trainingId={trainingId}
        onClose={() => setGeneratorOpen(false)}
        onGenerated={() => exams.refetch()}
      />
      <ConfirmDialog
        open={confirmDelete !== null}
        title={confirmDelete?.kind === 'module' ? 'Eliminar módulo' : 'Eliminar lección'}
        message="Se eliminará junto con su material, transcripciones y fragmentos indexados. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        destructive
        loading={remove.isPending}
        onConfirm={() => confirmDelete && remove.mutate(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </Box>
  );
}

function ModuleAccordion({
  module,
  index,
  onAddLesson,
  onDeleteModule,
  onDeleteLesson,
  onChanged,
}: {
  module: TrainingModule;
  index: number;
  onAddLesson: () => void;
  onDeleteModule: () => void;
  onDeleteLesson: (lessonId: string) => void;
  onChanged: () => void;
}) {
  return (
    <Accordion defaultExpanded={index === 0} disableGutters>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ width: '100%', pr: 2 }}>
          <Chip label={index + 1} size="small" />
          <Typography variant="subtitle1" sx={{ flex: 1 }}>
            {module.title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {module.lessons.length} lecciones
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          {module.lessons.map((lesson) => (
            <LessonBlock
              key={lesson.id}
              lesson={lesson}
              onDelete={() => onDeleteLesson(lesson.id)}
              onChanged={onChanged}
            />
          ))}

          <Divider />
          <Stack direction="row" spacing={1}>
            <Button size="small" startIcon={<Add />} onClick={onAddLesson}>
              Agregar lección
            </Button>
            <Button size="small" color="error" startIcon={<Delete />} onClick={onDeleteModule}>
              Eliminar módulo
            </Button>
          </Stack>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

function LessonBlock({
  lesson,
  onDelete,
  onChanged,
}: {
  lesson: Lesson;
  onDelete: () => void;
  onChanged: () => void;
}) {
  return (
    <Card variant="outlined">
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Box>
            <Typography variant="subtitle2">{lesson.title}</Typography>
            <Typography variant="caption" color="text.secondary">
              {lesson.type === 'VIDEO' ? 'Video' : lesson.type === 'DOCUMENT' ? 'Documento' : 'Texto'}
              {lesson.duration_seconds > 0 && ` · ${formatDurationLong(lesson.duration_seconds)}`}
            </Typography>
          </Box>
          <IconButton size="small" color="error" onClick={onDelete} aria-label="Eliminar lección">
            <Delete fontSize="small" />
          </IconButton>
        </Stack>

        <MaterialUploader
          lessonId={lesson.id}
          materials={lesson.materials}
          onChanged={onChanged}
        />
      </CardContent>
    </Card>
  );
}

function ModuleDialog({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (title: string) => void;
  loading: boolean;
}) {
  const [title, setTitle] = useState('');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Nuevo módulo</DialogTitle>
      <DialogContent>
        <TextField
          label="Título del módulo"
          autoFocus
          sx={{ mt: 1 }}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Fundamentos"
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={title.trim().length < 2 || loading}
          onClick={() => {
            onSubmit(title.trim());
            setTitle('');
          }}
        >
          Agregar
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function LessonDialog({
  open,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (title: string, type: string) => void;
  loading: boolean;
}) {
  const [title, setTitle] = useState('');
  const [type, setType] = useState('VIDEO');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Nueva lección</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Título"
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <TextField
            select
            label="Tipo"
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <MenuItem value="VIDEO">Video</MenuItem>
            <MenuItem value="DOCUMENT">Documento</MenuItem>
            <MenuItem value="TEXT">Texto</MenuItem>
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={title.trim().length < 2 || loading}
          onClick={() => {
            onSubmit(title.trim(), type);
            setTitle('');
          }}
        >
          Agregar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
