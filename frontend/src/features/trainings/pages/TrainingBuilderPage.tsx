/** Constructor de la capacitación: módulos, lecciones, material y evaluaciones. */

import {
  Add,
  ArrowBack,
  AutoAwesome,
  Delete,
  Edit,
  ExpandMore,
  MoreVert,
  People,
  Publish,
  Quiz,
  Unpublished,
  Visibility,
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
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type {
  Exam,
  Lesson,
  TrainingDetail,
  TrainingLevel,
  TrainingModule,
} from '@/shared/api/types';
import { ConfirmDialog, ErrorState, Loading, PageHeader, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { EnrollmentPanel } from '@/features/trainings/components/EnrollmentPanel';
import { ExamFormDialog } from '@/features/exams/components/ExamFormDialog';
import { ExamGenerationCard } from '@/features/exams/components/ExamGenerationCard';
import { ExamGeneratorDialog } from '@/features/exams/components/ExamGeneratorDialog';
import { useExamGeneration } from '@/features/exams/hooks/useExamGeneration';
import { MaterialUploader } from '@/features/trainings/components/MaterialUploader';
import { formatDurationLong } from '@/shared/utils/format';

type ModuleDialogState = { mode: 'create' } | { mode: 'edit'; module: TrainingModule };
type LessonDialogState =
  | { mode: 'create'; moduleId: string }
  | { mode: 'edit'; lesson: Lesson };

type SaveLessonInput = { moduleId?: string; id?: string; title: string; type: string };

type TrainingValues = {
  title: string;
  description: string;
  level: TrainingLevel;
  estimated_minutes: number;
};

export default function TrainingBuilderPage() {
  const { trainingId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const tab = params.get('tab') ?? 'content';
  // Los diálogos de módulo y lección sirven tanto para crear como para editar.
  const [moduleDialog, setModuleDialog] = useState<ModuleDialogState | null>(null);
  const [lessonDialog, setLessonDialog] = useState<LessonDialogState | null>(null);
  const [generatorOpen, setGeneratorOpen] = useState(false);
  const [examDialog, setExamDialog] = useState(false);
  const [trainingDialog, setTrainingDialog] = useState(false);
  const [headerMenu, setHeaderMenu] = useState<HTMLElement | null>(null);
  const [confirmDeleteTraining, setConfirmDeleteTraining] = useState(false);
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

  const onGenerationFinished = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ['training', trainingId, 'exams'] }),
    [queryClient, trainingId],
  );
  const { generation, start, dismiss } = useExamGeneration(trainingId, onGenerationFinished);

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

  const updateTraining = useMutation({
    mutationFn: (values: TrainingValues) =>
      api.patch(endpoints.trainings.detail(trainingId), values),
    onSuccess: async () => {
      await refresh();
      await queryClient.invalidateQueries({ queryKey: ['trainings'] });
      setTrainingDialog(false);
      snackbar.success('Capacitación actualizada.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const deleteTraining = useMutation({
    mutationFn: () => api.delete(endpoints.trainings.detail(trainingId)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['trainings'] });
      snackbar.info('Capacitación eliminada.');
      navigate('/capacitaciones');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const saveModule = useMutation({
    mutationFn: ({ id, title }: { id?: string; title: string }) =>
      id
        ? api.patch(endpoints.modules.detail(id), { title })
        : api.post(endpoints.trainings.modules(trainingId), { title }),
    onSuccess: async (_, { id }) => {
      await refresh();
      setModuleDialog(null);
      snackbar.success(id ? 'Módulo actualizado.' : 'Módulo agregado.');
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const saveLesson = useMutation({
    mutationFn: async ({ moduleId, id, title, type }: SaveLessonInput) => {
      if (!id) {
        await api.post(endpoints.modules.lessons(moduleId!), { title, type });
        return;
      }
      // LessonViewSet solo acepta multipart/form-data (parser_classes), y hay que
      // pisar la cabecera JSON del cliente: con ella axios serializaría el
      // FormData como JSON y el backend respondería 415.
      const body = new FormData();
      body.append('title', title);
      body.append('type', type);
      await api.patch(endpoints.lessons.detail(id), body, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    onSuccess: async (_, { id }) => {
      await refresh();
      setLessonDialog(null);
      snackbar.success(id ? 'Lección actualizada.' : 'Lección agregada.');
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
            <Button variant="outlined" startIcon={<Edit />} onClick={() => setTrainingDialog(true)}>
              Editar
            </Button>
            {/* Revisar el curso con los ojos del estudiante antes de publicarlo:
                mismo reproductor, sin registrar progreso. */}
            <Button
              variant="outlined"
              startIcon={<Visibility />}
              onClick={() => navigate(`/cursos/${trainingId}`)}
            >
              Vista previa
            </Button>
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
            <IconButton
              aria-label="Más acciones"
              onClick={(event) => setHeaderMenu(event.currentTarget)}
            >
              <MoreVert />
            </IconButton>
          </>
        }
      />

      <Menu
        open={headerMenu !== null}
        anchorEl={headerMenu}
        onClose={() => setHeaderMenu(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem
          onClick={() => {
            setConfirmDeleteTraining(true);
            setHeaderMenu(null);
          }}
        >
          <ListItemIcon>
            <Delete fontSize="small" color="error" />
          </ListItemIcon>
          <ListItemText slotProps={{ primary: { color: 'error' } }}>
            Eliminar capacitación
          </ListItemText>
        </MenuItem>
      </Menu>

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
            <Button startIcon={<Add />} variant="outlined" onClick={() => setModuleDialog({ mode: 'create' })}>
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
                <Button variant="contained" startIcon={<Add />} onClick={() => setModuleDialog({ mode: 'create' })}>
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
                  onAddLesson={() => setLessonDialog({ mode: 'create', moduleId: module.id })}
                  onEditModule={() => setModuleDialog({ mode: 'edit', module })}
                  onDeleteModule={() => setConfirmDelete({ kind: 'module', id: module.id })}
                  onEditLesson={(lesson) => setLessonDialog({ mode: 'edit', lesson })}
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
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'stretch', sm: 'center' }}
            spacing={1.5}
            sx={{ mb: 2 }}
          >
            <Typography variant="body2" color="text.secondary">
              Crea la evaluación tú mismo o deja que la IA la redacte a partir del material.
            </Typography>
            <Stack direction="row" spacing={1.5} sx={{ flexShrink: 0 }}>
              <Button
                variant="outlined"
                startIcon={<Add />}
                onClick={() => setExamDialog(true)}
              >
                Crear manual
              </Button>
              <Button
                variant="contained"
                startIcon={<AutoAwesome />}
                disabled={generation !== null && !generation.failed}
                onClick={() => setGeneratorOpen(true)}
              >
                Generar con IA
              </Button>
            </Stack>
          </Stack>

          {generation && <ExamGenerationCard generation={generation} onDismiss={dismiss} />}

          {(exams.data?.length ?? 0) === 0 ? (
            <Card>
              <CardContent sx={{ py: 6, textAlign: 'center' }}>
                <Quiz sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
                <Typography variant="h4" gutterBottom>
                  Sin evaluaciones
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  Crea un examen y escribe tú las preguntas, o genéralo automáticamente a partir
                  del material procesado.
                </Typography>
                <Button variant="contained" startIcon={<Add />} onClick={() => setExamDialog(true)}>
                  Crear evaluación manual
                </Button>
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
                      <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        flexWrap="wrap"
                        useFlexGap
                      >
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
      <TrainingDialog
        // Remontar al abrir para que los campos partan del dato recién cargado.
        key={`training-${trainingDialog}`}
        open={trainingDialog}
        training={data}
        onClose={() => setTrainingDialog(false)}
        onSubmit={(values) => updateTraining.mutate(values)}
        loading={updateTraining.isPending}
      />
      <ModuleDialog
        key={moduleDialog?.mode === 'edit' ? moduleDialog.module.id : 'new-module'}
        open={moduleDialog !== null}
        initialTitle={moduleDialog?.mode === 'edit' ? moduleDialog.module.title : ''}
        onClose={() => setModuleDialog(null)}
        onSubmit={(title) =>
          saveModule.mutate({
            id: moduleDialog?.mode === 'edit' ? moduleDialog.module.id : undefined,
            title,
          })
        }
        loading={saveModule.isPending}
      />
      <LessonDialog
        key={lessonDialog?.mode === 'edit' ? lessonDialog.lesson.id : 'new-lesson'}
        open={lessonDialog !== null}
        initial={lessonDialog?.mode === 'edit' ? lessonDialog.lesson : null}
        onClose={() => setLessonDialog(null)}
        onSubmit={(title, type) => {
          if (!lessonDialog) return;
          saveLesson.mutate(
            lessonDialog.mode === 'edit'
              ? { id: lessonDialog.lesson.id, title, type }
              : { moduleId: lessonDialog.moduleId, title, type },
          );
        }}
        loading={saveLesson.isPending}
      />
      <ExamGeneratorDialog
        open={generatorOpen}
        trainingId={trainingId}
        onClose={() => setGeneratorOpen(false)}
        onGenerated={start}
      />
      {examDialog && (
        <ExamFormDialog
          open
          trainingId={trainingId}
          onClose={() => setExamDialog(false)}
          // Sin preguntas no hay nada que revisar: se salta directo al editor.
          onSaved={(created) => navigate(`/examenes/${created.id}/editor`)}
        />
      )}
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
      <ConfirmDialog
        open={confirmDeleteTraining}
        title="Eliminar capacitación"
        message={
          <>
            <DialogContentText>
              Se eliminará «{data.title}» con todos sus módulos, lecciones, material y evaluaciones.
              Esta acción no se puede deshacer.
            </DialogContentText>
            {data.enrollment_count > 0 && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Hay {data.enrollment_count} participante(s) asignado(s): también se perderá su avance.
                Si solo quieres retirarla de circulación, usa <strong>Despublicar</strong>.
              </Alert>
            )}
          </>
        }
        confirmLabel="Eliminar"
        destructive
        loading={deleteTraining.isPending}
        onConfirm={() => deleteTraining.mutate()}
        onCancel={() => setConfirmDeleteTraining(false)}
      />
    </Box>
  );
}

function ModuleAccordion({
  module,
  index,
  onAddLesson,
  onEditModule,
  onDeleteModule,
  onEditLesson,
  onDeleteLesson,
  onChanged,
}: {
  module: TrainingModule;
  index: number;
  onAddLesson: () => void;
  onEditModule: () => void;
  onDeleteModule: () => void;
  onEditLesson: (lesson: Lesson) => void;
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
          {/* Dentro del summary: sin stopPropagation el clic plegaría el acordeón. */}
          <IconButton
            size="small"
            aria-label={`Editar módulo ${module.title}`}
            onClick={(event) => {
              event.stopPropagation();
              onEditModule();
            }}
          >
            <Edit fontSize="small" />
          </IconButton>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          {module.lessons.map((lesson) => (
            <LessonBlock
              key={lesson.id}
              lesson={lesson}
              onEdit={() => onEditLesson(lesson)}
              onDelete={() => onDeleteLesson(lesson.id)}
              onChanged={onChanged}
            />
          ))}

          <Divider />
          <Stack direction="row" spacing={1}>
            <Button size="small" startIcon={<Add />} onClick={onAddLesson}>
              Agregar lección
            </Button>
            <Button size="small" startIcon={<Edit />} onClick={onEditModule}>
              Editar módulo
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
  onEdit,
  onDelete,
  onChanged,
}: {
  lesson: Lesson;
  onEdit: () => void;
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
          <Stack direction="row" spacing={0.5}>
            <IconButton size="small" onClick={onEdit} aria-label="Editar lección">
              <Edit fontSize="small" />
            </IconButton>
            <IconButton size="small" color="error" onClick={onDelete} aria-label="Eliminar lección">
              <Delete fontSize="small" />
            </IconButton>
          </Stack>
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

function TrainingDialog({
  open,
  training,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  training: TrainingDetail;
  onClose: () => void;
  onSubmit: (values: TrainingValues) => void;
  loading: boolean;
}) {
  const [values, setValues] = useState<TrainingValues>({
    title: training.title,
    description: training.description,
    level: training.level,
    estimated_minutes: training.estimated_minutes,
  });

  const set = <K extends keyof TrainingValues>(key: K, value: TrainingValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Editar capacitación</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Título"
            autoFocus
            value={values.title}
            onChange={(event) => set('title', event.target.value)}
          />
          <TextField
            label="Descripción"
            multiline
            rows={3}
            value={values.description}
            onChange={(event) => set('description', event.target.value)}
          />
          <TextField
            select
            label="Nivel"
            value={values.level}
            onChange={(event) => set('level', event.target.value as TrainingLevel)}
          >
            <MenuItem value="BEGINNER">Básico</MenuItem>
            <MenuItem value="INTERMEDIATE">Intermedio</MenuItem>
            <MenuItem value="ADVANCED">Avanzado</MenuItem>
          </TextField>
          <TextField
            label="Duración estimada (minutos)"
            type="number"
            value={values.estimated_minutes}
            onChange={(event) => set('estimated_minutes', Number(event.target.value))}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={values.title.trim().length < 3 || loading}
          onClick={() => onSubmit({ ...values, title: values.title.trim() })}
        >
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ModuleDialog({
  open,
  initialTitle,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  initialTitle: string;
  onClose: () => void;
  onSubmit: (title: string) => void;
  loading: boolean;
}) {
  const [title, setTitle] = useState(initialTitle);
  const editing = initialTitle !== '';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{editing ? 'Editar módulo' : 'Nuevo módulo'}</DialogTitle>
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
          onClick={() => onSubmit(title.trim())}
        >
          {editing ? 'Guardar' : 'Agregar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function LessonDialog({
  open,
  initial,
  onClose,
  onSubmit,
  loading,
}: {
  open: boolean;
  initial: Lesson | null;
  onClose: () => void;
  onSubmit: (title: string, type: string) => void;
  loading: boolean;
}) {
  const [title, setTitle] = useState(initial?.title ?? '');
  const [type, setType] = useState<string>(initial?.type ?? 'VIDEO');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{initial ? 'Editar lección' : 'Nueva lección'}</DialogTitle>
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
          onClick={() => onSubmit(title.trim(), type)}
        >
          {initial ? 'Guardar' : 'Agregar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
