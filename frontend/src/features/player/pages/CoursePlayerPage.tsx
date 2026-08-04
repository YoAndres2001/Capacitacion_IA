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
  PlayCircle,
  Quiz,
  Search,
  SmartToy,
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
import { formatDuration, progressValue } from '@/shared/utils/format';

const SAVE_INTERVAL_MS = 10_000;

export default function CoursePlayerPage() {
  const { trainingId = '' } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up('lg'));
  const queryClient = useQueryClient();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [lessonId, setLessonId] = useState<string>('');
  const [chatOpen, setChatOpen] = useState(false);
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
    enabled: Boolean(material && material.type !== 'PDF' && material.type !== 'DOCX'),
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
  useEffect(() => {
    if (!lessonId) return;

    const timer = window.setInterval(() => {
      const position = videoRef.current?.currentTime ?? 0;
      if (position > 0) saveProgress.mutate({ id: lessonId, position });
    }, SAVE_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
      const position = videoRef.current?.currentTime ?? 0;
      if (position > 0) saveProgress.mutate({ id: lessonId, position });
    };
    // saveProgress es estable dentro del ciclo de vida de la página.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId]);

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
  const progress = progressValue(data.enrollment.progress);
  const publishedExams = (exams.data ?? []).filter((exam) => exam.status === 'PUBLISHED');
  const activeSegmentIndex = transcript.data?.segments.findIndex(
    (segment) => currentTime >= segment.start_time && currentTime <= segment.end_time,
  );

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <IconButton onClick={() => navigate('/mis-cursos')} aria-label="Volver">
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
        {data.chat_enabled && !isDesktop && (
          <Button startIcon={<SmartToy />} variant="outlined" onClick={() => setChatOpen(true)}>
            Tutor IA
          </Button>
        )}
      </Stack>

      <Box sx={{ mb: 2, maxWidth: 420 }}>
        <ProgressBar
          value={progress}
          label="Avance del curso"
          color={progress >= 100 ? 'success' : 'primary'}
        />
      </Box>

      <Stack direction="row" spacing={2.5} alignItems="flex-start">
        {/* Columna principal */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Card>
            <Box sx={{ bgcolor: 'black', position: 'relative' }}>
              {material && stream.data ? (
                <video
                  ref={videoRef}
                  key={material.id}
                  src={stream.data.url}
                  controls
                  controlsList="nodownload"
                  onLoadedMetadata={handleLoadedMetadata}
                  onTimeUpdate={handleTimeUpdate}
                  onEnded={() => completeLesson.mutate(lessonId)}
                  style={{ width: '100%', maxHeight: '58vh', display: 'block' }}
                />
              ) : (
                <Box sx={{ py: 8, textAlign: 'center', color: 'grey.500' }}>
                  {material ? (
                    <>
                      <Description sx={{ fontSize: 44, mb: 1 }} />
                      <Typography variant="body2">
                        Material de tipo documento: consulta su contenido con el Tutor IA o
                        descárgalo desde la lección.
                      </Typography>
                    </>
                  ) : (
                    <>
                      <PlayCircle sx={{ fontSize: 44, mb: 1 }} />
                      <Typography variant="body2">
                        Esta lección aún no tiene material disponible.
                      </Typography>
                    </>
                  )}
                </Box>
              )}
            </Box>

            <CardContent sx={{ p: 2.5 }}>
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
                <Button
                  variant={data.lesson_progress[lessonId]?.completed ? 'outlined' : 'contained'}
                  startIcon={<CheckCircle />}
                  onClick={() => completeLesson.mutate(lessonId)}
                  disabled={!lessonId || data.lesson_progress[lessonId]?.completed}
                >
                  {data.lesson_progress[lessonId]?.completed ? 'Completada' : 'Marcar completada'}
                </Button>
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
              <CardContent sx={{ p: 2.5 }}>
                <Typography variant="h4" gutterBottom>
                  Evaluaciones
                </Typography>
                <Stack spacing={1.5} sx={{ mt: 1.5 }}>
                  {publishedExams.map((exam) => {
                    const enabled = progress >= exam.min_progress_required;
                    return (
                      <Stack
                        key={exam.id}
                        direction="row"
                        alignItems="center"
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

        {/* Columna lateral: contenido, transcripción, búsqueda */}
        <Card sx={{ width: 380, flexShrink: 0, display: { xs: 'none', md: 'block' } }}>
          <Tabs
            value={sideTab}
            onChange={(_, value) => setSideTab(value)}
            variant="fullWidth"
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          >
            <Tab label="Contenido" value="content" />
            <Tab label="Transcripción" value="transcript" />
            <Tab label={<Search fontSize="small" />} value="search" />
          </Tabs>

          <Box sx={{ maxHeight: '68vh', overflowY: 'auto' }}>
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
        </Card>

        {/* Chat IA fijo en pantallas grandes */}
        {data.chat_enabled && isDesktop && (
          <Card sx={{ width: 400, flexShrink: 0, height: '78vh', display: 'flex' }}>
            <ChatPanel trainingId={trainingId} onSeek={seekFromCitation} />
          </Card>
        )}
      </Stack>

      {/* Chat IA en cajón para pantallas pequeñas */}
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
