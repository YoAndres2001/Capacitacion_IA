/** Reportes de progreso, resultados y utilización de IA (RF-070 a RF-074). */

import { Download } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  MenuItem,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api, tokenStorage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Paginated, Project } from '@/shared/api/types';
import { ErrorState, Loading, PageHeader, ProgressBar, StatCard } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { STATUS_LABEL, formatDate, progressValue } from '@/shared/utils/format';

interface ProgressRow {
  enrollment_id: string;
  user_name: string;
  user_email: string;
  training_title: string;
  project_name: string;
  status: string;
  progress: number;
  assigned_at: string;
  completed_at: string | null;
}

interface ExamResultsReport {
  summary: { attempts: number; pass_rate: number; average_score: number };
  by_exam: Array<{
    exam_id: string;
    exam_title: string;
    training_title: string;
    attempts: number;
    passed: number;
    pass_rate: number;
    average_score: number;
  }>;
}

interface AIUsageReport {
  calls: number;
  total_tokens: number;
  cost_usd: number;
  chat_answers: number;
  no_context_rate: number;
  by_purpose: Array<{
    purpose: string;
    provider: string;
    model: string;
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
  }>;
  top_questions: Array<{ content: string; count: number }>;
}

const PURPOSE_LABEL: Record<string, string> = {
  TRANSCRIPTION: 'Transcripción',
  EMBEDDING: 'Embeddings',
  ANALYSIS: 'Análisis de material',
  CHAT: 'Chat RAG',
  AGENT: 'Agente tutor',
  EXAM_GENERATION: 'Generación de exámenes',
  EXAM_GRADING: 'Corrección de exámenes',
};

export default function AnalyticsPage() {
  const snackbar = useSnackbar();
  const [tab, setTab] = useState('progress');
  const [projectFilter, setProjectFilter] = useState('');

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: async () => (await api.get<Paginated<Project>>(endpoints.projects.list)).data,
  });

  const progress = useQuery({
    queryKey: ['analytics', 'progress', projectFilter],
    queryFn: async () =>
      (
        await api.get<ProgressRow[]>(endpoints.analytics.progress, {
          params: projectFilter ? { project: projectFilter } : {},
        })
      ).data,
    enabled: tab === 'progress',
  });

  const examResults = useQuery({
    queryKey: ['analytics', 'exam-results'],
    queryFn: async () =>
      (await api.get<ExamResultsReport>(endpoints.analytics.examResults)).data,
    enabled: tab === 'exams',
  });

  const aiUsage = useQuery({
    queryKey: ['analytics', 'ai-usage'],
    queryFn: async () => (await api.get<AIUsageReport>(endpoints.analytics.aiUsage)).data,
    enabled: tab === 'ai',
  });

  const exportCsv = async (report: string) => {
    try {
      const response = await fetch(
        `${api.defaults.baseURL}${endpoints.analytics.export}?report=${report}&format=csv`,
        { headers: { Authorization: `Bearer ${tokenStorage.access}` } },
      );
      if (!response.ok) throw new Error('No se pudo generar el archivo.');

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${report}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      snackbar.error(error instanceof Error ? error.message : 'Error al exportar.');
    }
  };

  return (
    <Box>
      <PageHeader title="Analítica" subtitle="Progreso, resultados y consumo de IA" />

      <Tabs
        value={tab}
        onChange={(_, value) => setTab(value)}
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label="Progreso" value="progress" />
        <Tab label="Evaluaciones" value="exams" />
        <Tab label="Uso de IA" value="ai" />
      </Tabs>

      {tab === 'progress' && (
        <Box>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'stretch', sm: 'center' }}
            sx={{ mb: 2 }}
            spacing={2}
          >
            <TextField
              select
              label="Proyecto"
              value={projectFilter}
              onChange={(event) => setProjectFilter(event.target.value)}
              sx={{ maxWidth: { sm: 280 } }}
            >
              <MenuItem value="">Todos</MenuItem>
              {(projects.data?.results ?? []).map((project) => (
                <MenuItem key={project.id} value={project.id}>
                  {project.name}
                </MenuItem>
              ))}
            </TextField>
            <Button startIcon={<Download />} onClick={() => exportCsv('progress')}>
              Exportar CSV
            </Button>
          </Stack>

          {progress.isLoading && <Loading />}
          {progress.isError && <ErrorState error={progress.error} onRetry={progress.refetch} />}
          {progress.data && (
            <Card>
              <CardContent sx={{ p: 0 }}>
                <Box sx={{ overflowX: 'auto' }}>
                  {/* `minWidth` es lo que fuerza el desplazamiento: sin él las
                      columnas se comprimen hasta volverse ilegibles. */}
                  <Table size="small" sx={{ minWidth: 860 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Usuario</TableCell>
                        <TableCell>Proyecto</TableCell>
                        <TableCell>Capacitación</TableCell>
                        <TableCell>Estado</TableCell>
                        <TableCell sx={{ minWidth: 160 }}>Avance</TableCell>
                        <TableCell>Asignado</TableCell>
                        <TableCell>Completado</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {progress.data.map((row) => (
                        <TableRow key={row.enrollment_id} hover>
                          <TableCell>
                            <Typography variant="body2" fontWeight={600}>
                              {row.user_name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {row.user_email}
                            </Typography>
                          </TableCell>
                          <TableCell>{row.project_name}</TableCell>
                          <TableCell>{row.training_title}</TableCell>
                          <TableCell>
                            <Chip
                              label={STATUS_LABEL[row.status] ?? row.status}
                              size="small"
                              color={row.status === 'COMPLETED' ? 'success' : 'default'}
                            />
                          </TableCell>
                          <TableCell>
                            <ProgressBar value={progressValue(row.progress)} label="" />
                          </TableCell>
                          <TableCell>{formatDate(row.assigned_at)}</TableCell>
                          <TableCell>{formatDate(row.completed_at)}</TableCell>
                        </TableRow>
                      ))}
                      {progress.data.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                            <Typography variant="body2" color="text.secondary">
                              Sin inscripciones registradas.
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </Box>
              </CardContent>
            </Card>
          )}
        </Box>
      )}

      {tab === 'exams' && (
        <Box>
          <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
            <Button startIcon={<Download />} onClick={() => exportCsv('attempts')}>
              Exportar CSV
            </Button>
          </Stack>

          {examResults.isLoading && <Loading />}
          {examResults.data && (
            <>
              <Grid container spacing={2.5} sx={{ mb: 3 }}>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <StatCard label="Intentos corregidos" value={examResults.data.summary.attempts} />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <StatCard
                    label="Tasa de aprobación"
                    value={`${examResults.data.summary.pass_rate.toFixed(0)}%`}
                    color="success.main"
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <StatCard
                    label="Puntaje promedio"
                    value={examResults.data.summary.average_score.toFixed(1)}
                  />
                </Grid>
              </Grid>

              <Card>
                <CardContent sx={{ p: 0 }}>
                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small" sx={{ minWidth: 640 }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Examen</TableCell>
                          <TableCell>Capacitación</TableCell>
                          <TableCell align="right">Intentos</TableCell>
                          <TableCell align="right">Aprobados</TableCell>
                          <TableCell align="right">Tasa</TableCell>
                          <TableCell align="right">Promedio</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {examResults.data.by_exam.map((row) => (
                          <TableRow key={row.exam_id} hover>
                            <TableCell>{row.exam_title}</TableCell>
                            <TableCell>{row.training_title}</TableCell>
                            <TableCell align="right">{row.attempts}</TableCell>
                            <TableCell align="right">{row.passed}</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${row.pass_rate}%`}
                                size="small"
                                color={row.pass_rate >= 70 ? 'success' : 'warning'}
                              />
                            </TableCell>
                            <TableCell align="right">{row.average_score.toFixed(1)}</TableCell>
                          </TableRow>
                        ))}
                        {examResults.data.by_exam.length === 0 && (
                          <TableRow>
                            <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                              <Typography variant="body2" color="text.secondary">
                                Aún no hay exámenes rendidos.
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </Box>
                </CardContent>
              </Card>
            </>
          )}
        </Box>
      )}

      {tab === 'ai' && (
        <Box>
          {aiUsage.isLoading && <Loading />}
          {aiUsage.data && (
            <>
              <Grid container spacing={2.5} sx={{ mb: 3 }}>
                <Grid size={{ xs: 6, md: 3 }}>
                  <StatCard label="Llamadas" value={aiUsage.data.calls.toLocaleString('es-CL')} />
                </Grid>
                <Grid size={{ xs: 6, md: 3 }}>
                  <StatCard
                    label="Tokens"
                    value={aiUsage.data.total_tokens.toLocaleString('es-CL')}
                  />
                </Grid>
                <Grid size={{ xs: 6, md: 3 }}>
                  <StatCard
                    label="Costo estimado"
                    value={`US$ ${aiUsage.data.cost_usd.toFixed(2)}`}
                    hint={aiUsage.data.cost_usd === 0 ? 'Modelos locales gratuitos' : undefined}
                  />
                </Grid>
                <Grid size={{ xs: 6, md: 3 }}>
                  <StatCard
                    label="Sin contexto"
                    value={`${aiUsage.data.no_context_rate.toFixed(1)}%`}
                    hint={`${aiUsage.data.chat_answers} respuestas`}
                    color="warning.main"
                  />
                </Grid>
              </Grid>

              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 7 }}>
                  <Card>
                    <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                      <Typography variant="h4" gutterBottom>
                        Consumo por propósito
                      </Typography>
                      {/* Cinco columnas no entran en un teléfono: la tabla se
                          desplaza dentro de la tarjeta, no arrastra la página. */}
                      <Box sx={{ overflowX: 'auto', mx: { xs: -1, sm: 0 } }}>
                      <Table size="small" sx={{ mt: 1, minWidth: 420 }}>
                        <TableHead>
                          <TableRow>
                            <TableCell>Propósito</TableCell>
                            <TableCell>Modelo</TableCell>
                            <TableCell align="right">Llamadas</TableCell>
                            <TableCell align="right">Tokens</TableCell>
                            <TableCell align="right">Costo</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {aiUsage.data.by_purpose.map((row, index) => (
                            <TableRow key={`${row.purpose}-${index}`}>
                              <TableCell>{PURPOSE_LABEL[row.purpose] ?? row.purpose}</TableCell>
                              <TableCell>
                                <Typography variant="caption">{row.model}</Typography>
                              </TableCell>
                              <TableCell align="right">{row.calls}</TableCell>
                              <TableCell align="right">
                                {(row.prompt_tokens + row.completion_tokens).toLocaleString('es-CL')}
                              </TableCell>
                              <TableCell align="right">US$ {row.cost_usd.toFixed(4)}</TableCell>
                            </TableRow>
                          ))}
                          {aiUsage.data.by_purpose.length === 0 && (
                            <TableRow>
                              <TableCell colSpan={5} align="center" sx={{ py: 3 }}>
                                <Typography variant="body2" color="text.secondary">
                                  Sin consumo registrado todavía.
                                </Typography>
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid size={{ xs: 12, md: 5 }}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                      <Typography variant="h4" gutterBottom>
                        Preguntas más frecuentes
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        Lo que más consultan los usuarios indica dónde reforzar el contenido.
                      </Typography>
                      <Stack spacing={1.25}>
                        {aiUsage.data.top_questions.slice(0, 12).map((row, index) => (
                          <Box key={index}>
                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                              <Typography variant="body2" noWrap title={row.content}>
                                {row.content}
                              </Typography>
                              <Chip label={row.count} size="small" />
                            </Stack>
                            <LinearProgress
                              variant="determinate"
                              value={
                                (row.count /
                                  Math.max(1, aiUsage.data!.top_questions[0]?.count ?? 1)) *
                                100
                              }
                              sx={{ height: 4, borderRadius: 2, mt: 0.5 }}
                            />
                          </Box>
                        ))}
                        {aiUsage.data.top_questions.length === 0 && (
                          <Typography variant="body2" color="text.secondary">
                            Todavía no hay preguntas registradas.
                          </Typography>
                        )}
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </>
          )}
        </Box>
      )}
    </Box>
  );
}
