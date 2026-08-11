/**
 * Reproductor del curso: video + transcripción sincronizada + capítulos + chat IA.
 *
 * Guarda la posición cada 10 s y al salir, y marca la lección completada al
 * alcanzar el 90 % de reproducción (RF-032, RF-033).
 */

import {
  ArrowBack,
  CheckCircle,
  Description,
  ExpandMore,
  MenuBook,
  PlayCircle,
  Quiz,
  Search,
  SmartToy,
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
  Divider,
  Drawer,
  IconButton,
  InputAdornment,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type {
  Chapter,
  CourseSearchResult,
  Exam,
  Lesson,
  MyTrainingDetail,
  Transcript,
} from '@/shared/api/types';
import { ErrorState, Loading, ProgressBar } from '@/shared/components';
import { ChatPanel } from '@/features/chat/ChatPanel';
import { MaterialViewer } from '@/features/player/components/MaterialViewer';
import { formatDuration, progressValue } from '@/shared/utils/format';

const SAVE_INTERVAL_MS = 10_000;

export default function CoursePlayerPage() {
  const { trainingId = '' } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  /**
   * Tres columnas (video + índice + chat) piden mucho ancho: con el cajón fijo
   * de 248 px, el índice de 380 px y el chat de 400 px, por debajo de un
   * monitor grande al video le quedarían menos de 400 px. Por eso cada columna
   * lateral aparece en su propio umbral y, si no cabe, se ofrece en un cajón.
   */
  const chatInline = useMediaQuery(theme.breakpoints.up('xl'));
  const sideInline = useMediaQuery(theme.breakpoints.up('lg'));
  const queryClient = useQueryClient();

  // Sirve para `<video>` y `<audio>`: ambos exponen la API de HTMLMediaElement.
  const videoRef = useRef<HTMLMediaElement | null>(null);
  const [lessonId, setLessonId] = useState<string>('');
  const [chatOpen, setChatOpen] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [sideTab, setSideTab] = useState('content');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentTime, setCurrentTime] = useState(0);

  const course = useQuery({
    queryKey: ['course', trainingId],
    queryFn: async () =>
      (await api.get<MyTrainingDetail>(endpoints.me.trainingDetail(trainingId))).data,
  });

  const exams = useQuery({
    queryKey: ['course', trainingId, 'exams'],
    queryFn: async () => (await api.get<Exam[]>(endpoints.trainings.exams(trainingId))).data,
  });

  const lessons = useMemo(
    () => course.data?.modules.flatMap((module) => module.lessons) ?? [],
    [course.data],
  );

  // Al cargar, se abre la primera lección no completada.
  useEffect(() => {
    if (lessonId || lessons.length === 0 || !course.data) return;
    const progress = course.data.lesson_progress;
    const next = lessons.find((lesson) => !progress[lesson.id]?.completed) ?? lessons[0];
    setLessonId(next.id);
  }, [lessons, lessonId, course.data]);

  const lesson = lessons.find((item) => item.id === lessonId);
  const material = lesson?.materials.find((item) => item.status === 'AVAILABLE');

  const stream = useQuery({
    queryKey: ['material', material?.id, 'stream'],
    queryFn: async () =>
      (await api.get<{ url: string; mime_type: string; duration_seconds: number }>(
        endpoints.materials.stream(material!.id),
      )).data,
    enabled: Boolean(material),
  });

  const transcript = useQuery({
    queryKey: ['material', material?.id, 'transcript'],
    queryFn: async () =>
      (await api.get<Transcript>(endpoints.materials.transcript(material!.id))).data,
    enabled: Boolean(material),
    retry: false,
  });

  const chapters = useQuery({
    queryKey: ['material', material?.id, 'chapters'],
    queryFn: async () => (await api.get<Chapter[]>(endpoints.materials.chapters(material!.id))).data,
    enabled: Boolean(material),
  });

  const search = useQuery({
    queryKey: ['course', trainingId, 'search', searchTerm],
    queryFn: async () =>
      (
        await api.get<CourseSearchResult[]>(endpoints.trainings.search(trainingId), {
          params: { q: searchTerm },
        })
      ).data,
    enabled: searchTerm.trim().length >= 2 && sideTab === 'search',
  });

  // En la vista previa no hay matrícula: escribir progreso devolvería 403 y, si
  // la hubiera, ensuciaría las estadísticas del curso con la visita del autor.
  const isPreview = course.data?.preview ?? false;

  const saveProgress = useMutation({
    mutationFn: ({ id, position }: { id: string; position: number }) =>
      api.patch(endpoints.lessons.progress(id), {
        position_seconds: Math.floor(position),
        watched_seconds: Math.floor(position),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['course', trainingId] }),
  });

  const completeLesson = useMutation({
    mutationFn: (id: string) => api.post(endpoints.lessons.complete(id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['course', trainingId] }),
  });

  // Guardado periódico y al desmontar (RF-032).
  //
  // Solo se reporta lo REPRODUCIDO (`currentTime`). Una lección de documento no
  // tiene reproducción que medir y no se le atribuye tiempo: su avance se marca
  // como completada, de forma explícita. Medir el rato con la pestaña abierta se
  // descartó a propósito — no distingue leer de dejar la ventana olvidada.
  useEffect(() => {
    if (!lessonId || isPreview) return;

    const flush = () => {
      const position = videoRef.current?.currentTime ?? 0;
      if (position > 0) saveProgress.mutate({ id: lessonId, position });
    };

    const timer = window.setInterval(flush, SAVE_INTERVAL_MS);
    // Cerrar la pestaña no dispara el desmontaje: sin esto se perdería el
    // último tramo de reproducción.
    const onHide = () => {
      if (document.visibilityState === 'hidden') flush();
    };
    document.addEventListener('visibilitychange', onHide);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onHide);
      flush();
    };
    // saveProgress es estable dentro del ciclo de vida de la página.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId, isPreview]);

  // Reanudar donde quedó.
  const handleLoadedMetadata = useCallback(() => {
    const saved = course.data?.lesson_progress[lessonId]?.position_seconds ?? 0;
    if (saved > 5 && videoRef.current) {
      videoRef.current.currentTime = saved;
    }
  }, [course.data, lessonId]);

  const handleTimeUpdate = useCallback(() => {
    const element = videoRef.current;
    if (!element || !element.duration) return;
    setCurrentTime(element.currentTime);
  }, []);

  const seekTo = useCallback((seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      void videoRef.current.play();
    }
  }, []);

  const seekFromCitation = useCallback(
    (materialId: string, seconds: number) => {
      const target = lessons.find((item) =>
        item.materials.some((mat) => mat.id === materialId),
      );
      if (target && target.id !== lessonId) {
        setLessonId(target.id);
        // El video necesita recargar; el salto se aplica tras el metadata.
        window.setTimeout(() => seekTo(seconds), 700);
      } else {
        seekTo(seconds);
      }
    },
    [lessons, lessonId, seekTo],
  );

  if (course.isLoading) return <Loading label="Cargando curso…" />;
  if (course.isError) return <ErrorState error={course.error} onRetry={course.refetch} />;

  const data = course.data!;
  const progress = progressValue(data.enrollment?.progress ?? 0);
  // El estudiante solo ve exámenes publicados; en la vista previa se muestran
  // también los borradores, que es justo lo que el instructor quiere revisar.
  const publishedExams = (exams.data ?? []).filter(
    (exam) => exam.status === 'PUBLISHED' || isPreview,
  );
  const activeSegmentIndex = transcript.data?.segments.findIndex(
    (segment) => currentTime >= segment.start_time && currentTime <= segment.end_time,
  );

  return (
    <Box>
      {isPreview && (
        <Alert
          severity="info"
          icon={<Visibility />}
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => navigate(`/capacitaciones/${trainingId}/editor`)}
            >
              Volver al editor
            </Button>
          }
        >
          Estás viendo el curso <strong>como lo verá un estudiante</strong>. No se registra
          progreso y los exámenes en borrador también aparecen.
        </Alert>
      )}

      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <IconButton
          onClick={() => navigate(isPreview ? `/capacitaciones/${trainingId}/editor` : '/inicio')}
          aria-label="Volver"
        >
          <ArrowBack />
        </IconButton>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h3" noWrap>
            {data.title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {data.project_name}
          </Typography>
        </Box>
        {/* Cuando el índice no cabe al costado, se abre desde aquí: sin esto
            un estudiante en teléfono no tendría cómo cambiar de lección. */}
        {!sideInline && (
          <Tooltip title="Contenido del curso">
            <IconButton onClick={() => setSideOpen(true)} aria-label="Contenido del curso">
              <MenuBook />
            </IconButton>
          </Tooltip>
        )}
        {data.chat_enabled && !chatInline && (
          <Button
            startIcon={<SmartToy />}
            variant="outlined"
            onClick={() => setChatOpen(true)}
            sx={{ flexShrink: 0 }}
          >
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
              Tutor&nbsp;
            </Box>
            IA
          </Button>
        )}
      </Stack>

      {!isPreview && (
        <Box sx={{ mb: 2, maxWidth: 420 }}>
          <ProgressBar
            value={progress}
            label="Avance del curso"
            color={progress >= 100 ? 'success' : 'primary'}
          />
        </Box>
      )}

      <Stack direction="row" spacing={{ xs: 0, lg: 2.5 }} alignItems="flex-start">
        {/* Columna principal */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Card>
            <Box
              sx={{
                bgcolor: material?.type === 'VIDEO' ? 'black' : 'background.paper',
                position: 'relative',
              }}
            >
              <MaterialViewer
                material={material}
                streamUrl={stream.data?.url}
                onMediaRef={(element) => {
                  videoRef.current = element;
                }}
                onLoadedMetadata={handleLoadedMetadata}
                onTimeUpdate={handleTimeUpdate}
                onEnded={() => !isPreview && completeLesson.mutate(lessonId)}
              />
            </Box>

            <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                justifyContent="space-between"
                alignItems={{ sm: 'center' }}
                spacing={1.5}
              >
                <Box>
                  <Typography variant="h4">{lesson?.title ?? 'Selecciona una lección'}</Typography>
                  {lesson?.description && (
                    <Typography variant="body2" color="text.secondary">
                      {lesson.description}
                    </Typography>
                  )}
                </Box>
                <Tooltip title={isPreview ? 'En la vista previa no se registra progreso' : ''}>
                  <span>
                    <Button
                      variant={data.lesson_progress[lessonId]?.completed ? 'outlined' : 'contained'}
                      startIcon={<CheckCircle />}
                      onClick={() => completeLesson.mutate(lessonId)}
                      disabled={
                        !lessonId || isPreview || data.lesson_progress[lessonId]?.completed
                      }
                    >
                      {data.lesson_progress[lessonId]?.completed
                        ? 'Completada'
                        : 'Marcar completada'}
                    </Button>
                  </span>
                </Tooltip>
              </Stack>

              {material?.summary && (
                <Alert severity="info" icon={false} sx={{ mt: 2 }}>
                  <Typography variant="caption" fontWeight={700} display="block">
                    Resumen generado por IA
                  </Typography>
                  <Typography variant="body2">{material.summary}</Typography>
                </Alert>
              )}
            </CardContent>
          </Card>

          {publishedExams.length > 0 && (
            <Card sx={{ mt: 2.5 }}>
              <CardContent sx={{ p: { xs: 2, sm: 2.5 } }}>
                <Typography variant="h4" gutterBottom>
                  Evaluaciones
                </Typography>
                <Stack spacing={1.5} sx={{ mt: 1.5 }}>
                  {publishedExams.map((exam) => {
                    const enabled = progress >= exam.min_progress_required;
                    return (
                      <Stack
                        key={exam.id}
                        direction={{ xs: 'column', sm: 'row' }}
                        alignItems={{ xs: 'flex-start', sm: 'center' }}
                        justifyContent="space-between"
                        spacing={1.5}
                      >
                        <Box>
                          <Typography variant="subtitle2">{exam.title}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {exam.question_count} preguntas · aprobación {exam.passing_score}% ·{' '}
                            {exam.max_attempts} intentos
                            {exam.time_limit_minutes > 0 && ` · ${exam.time_limit_minutes} min`}
                          </Typography>
                        </Box>
                        <Tooltip
                          title={
                            enabled
                              ? 'Rendir la evaluación'
                              : `Necesitas ${exam.min_progress_required}% de avance`
                          }
                        >
                          <span>
                            <Button
                              variant="contained"
                              startIcon={<Quiz />}
                              disabled={!enabled}
                              onClick={() => navigate(`/examenes/${exam.id}/rendir`)}
                            >
                              Rendir
                            </Button>
                          </span>
                        </Tooltip>
                      </Stack>
                    );
                  })}
                </Stack>
              </CardContent>
            </Card>
          )}
        </Box>

        {/* Columna lateral: contenido, transcripción, búsqueda.
            Va al costado en monitores y en un cajón lateral cuando no cabe. */}
        <SidePanelShell
          inline={sideInline}
          open={sideOpen}
          onClose={() => setSideOpen(false)}
        >
          <Tabs
            value={sideTab}
            onChange={(_, value) => setSideTab(value)}
            variant="fullWidth"
            sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
          >
            <Tab label="Contenido" value="content" />
            <Tab label="Transcripción" value="transcript" />
            <Tab label={<Search fontSize="small" />} value="search" />
          </Tabs>

          <Box sx={{ flex: 1, maxHeight: { xs: 'none', lg: '68vh' }, overflowY: 'auto' }}>
            {sideTab === 'content' && (
              <Box sx={{ p: 1 }}>
                {data.modules.map((module, index) => (
                  <Accordion key={module.id} defaultExpanded={index === 0} disableGutters elevation={0}>
                    <AccordionSummary expandIcon={<ExpandMore />}>
                      <Typography variant="subtitle2">{module.title}</Typography>
                    </AccordionSummary>
                    <AccordionDetails sx={{ p: 0 }}>
                      <List dense disablePadding>
                        {module.lessons.map((item: Lesson) => {
                          const done = data.lesson_progress[item.id]?.completed;
                          return (
                            <ListItemButton
                              key={item.id}
                              selected={item.id === lessonId}
                              onClick={() => setLessonId(item.id)}
                            >
                              <ListItemIcon sx={{ minWidth: 34 }}>
                                {done ? (
                                  <CheckCircle color="success" fontSize="small" />
                                ) : item.type === 'VIDEO' ? (
                                  <PlayCircle fontSize="small" />
                                ) : (
                                  <Description fontSize="small" />
                                )}
                              </ListItemIcon>
                              <ListItemText
                                primary={item.title}
                                secondary={
                                  item.duration_seconds > 0
                                    ? formatDuration(item.duration_seconds)
                                    : undefined
                                }
                                primaryTypographyProps={{ fontSize: 13.5 }}
                              />
                            </ListItemButton>
                          );
                        })}
                      </List>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
            )}

            {sideTab === 'transcript' && (
              <Box sx={{ p: 2 }}>
                {(chapters.data?.length ?? 0) > 0 && (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      Capítulos
                    </Typography>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.75, mb: 2 }}>
                      {chapters.data!.map((chapter) => (
                        <Chip
                          key={chapter.id}
                          label={`${formatDuration(chapter.start_time ?? 0)} ${chapter.title}`}
                          size="small"
                          variant="outlined"
                          onClick={() => chapter.start_time !== null && seekTo(chapter.start_time)}
                        />
                      ))}
                    </Stack>
                    <Divider sx={{ mb: 2 }} />
                  </>
                )}

                {transcript.data ? (
                  <Stack spacing={0.75}>
                    {transcript.data.segments.map((segment, index) => (
                      <Paper
                        key={segment.index}
                        variant={index === activeSegmentIndex ? 'elevation' : 'outlined'}
                        elevation={index === activeSegmentIndex ? 3 : 0}
                        onClick={() => seekTo(segment.start_time)}
                        sx={{
                          p: 1,
                          cursor: 'pointer',
                          borderColor: index === activeSegmentIndex ? 'primary.main' : undefined,
                          bgcolor: index === activeSegmentIndex ? 'action.selected' : undefined,
                        }}
                      >
                        <Typography variant="caption" color="primary.main">
                          {formatDuration(segment.start_time)}
                        </Typography>
                        <Typography variant="body2">{segment.text}</Typography>
                      </Paper>
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Esta lección no tiene transcripción.
                  </Typography>
                )}
              </Box>
            )}

            {sideTab === 'search' && (
              <Box sx={{ p: 2 }}>
                <TextField
                  placeholder="Buscar en todo el curso…"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Search fontSize="small" />
                      </InputAdornment>
                    ),
                  }}
                />
                <Stack spacing={1} sx={{ mt: 2 }}>
                  {(search.data ?? []).map((result, index) => (
                    <Paper
                      key={`${result.material_id}-${index}`}
                      variant="outlined"
                      sx={{ p: 1.25, cursor: result.start_time !== null ? 'pointer' : 'default' }}
                      onClick={() =>
                        result.start_time !== null &&
                        seekFromCitation(result.material_id, result.start_time)
                      }
                    >
                      <Typography variant="caption" color="primary.main">
                        {result.material_title}
                        {result.start_time !== null && ` · ${formatDuration(result.start_time)}`}
                        {result.page !== null && ` · pág. ${result.page}`}
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{ mt: 0.5 }}
                        dangerouslySetInnerHTML={{ __html: result.excerpt }}
                      />
                    </Paper>
                  ))}
                  {searchTerm.trim().length >= 2 && (search.data?.length ?? 0) === 0 && !search.isLoading && (
                    <Typography variant="body2" color="text.secondary">
                      Sin coincidencias.
                    </Typography>
                  )}
                </Stack>
              </Box>
            )}
          </Box>
        </SidePanelShell>

        {/* Chat IA fijo solo cuando sobra ancho para una tercera columna */}
        {data.chat_enabled && chatInline && (
          <Card sx={{ width: 400, flexShrink: 0, height: '78vh', display: 'flex' }}>
            <ChatPanel trainingId={trainingId} onSeek={seekFromCitation} />
          </Card>
        )}
      </Stack>

      {/* Chat IA en cajón para el resto de las pantallas */}
      <Drawer
        anchor="right"
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 420 } } }}
      >
        <ChatPanel trainingId={trainingId} onSeek={seekFromCitation} />
      </Drawer>
    </Box>
  );
}

/**
 * Contenedor del panel lateral del curso.
 *
 * Es el mismo contenido en los dos casos; lo único que cambia es si vive al
 * costado del video o se superpone en un cajón, así que se resuelve aquí en
 * vez de duplicar el índice, la transcripción y el buscador.
 */
function SidePanelShell({
  inline,
  open,
  onClose,
  children,
}: {
  inline: boolean;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (inline) {
    return (
      <Card
        sx={{
          width: { lg: 340, xl: 380 },
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {children}
      </Card>
    );
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: { width: { xs: '100%', sm: 420 }, display: 'flex', flexDirection: 'column' },
      }}
    >
      {children}
    </Drawer>
  );
}
