/** Resultados agregados de un examen para el instructor (RF-072). */

import { ArrowBack } from '@mui/icons-material';
import {
  Box,
  Card,
  CardContent,
  Chip,
  IconButton,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Exam } from '@/shared/api/types';
import { ErrorState, Loading, PageHeader, StatCard } from '@/shared/components';

interface Results {
  attempts: number;
  graded: number;
  passed: number;
  pass_rate: number;
  average_score: number;
  distribution: Record<string, number>;
  hardest_questions: Array<{
    question_id: string;
    statement: string;
    attempts: number;
    wrong: number;
    error_rate: number;
  }>;
}

export default function ExamResultsPage() {
  const { examId = '' } = useParams();
  const navigate = useNavigate();

  const exam = useQuery({
    queryKey: ['exam', examId],
    queryFn: async () => (await api.get<Exam>(endpoints.exams.detail(examId))).data,
  });

  const results = useQuery({
    queryKey: ['exam', examId, 'results'],
    queryFn: async () => (await api.get<Results>(endpoints.exams.results(examId))).data,
  });

  if (results.isLoading) return <Loading />;
  if (results.isError) return <ErrorState error={results.error} onRetry={results.refetch} />;

  const data = results.data!;
  const maxBucket = Math.max(1, ...Object.values(data.distribution));

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton onClick={() => navigate(-1)} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          {exam.data?.training_title}
        </Typography>
      </Stack>

      <PageHeader
        title={exam.data?.title ?? 'Resultados'}
        subtitle="Desempeño de los participantes y preguntas más falladas"
      />

      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, md: 3 }}>
          <StatCard label="Intentos" value={data.attempts} hint={`${data.graded} corregidos`} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <StatCard label="Aprobados" value={data.passed} color="success.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <StatCard
            label="Tasa de aprobación"
            value={`${data.pass_rate.toFixed(0)}%`}
            color="success.main"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <StatCard label="Puntaje promedio" value={data.average_score.toFixed(1)} />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="h4" gutterBottom>
                Distribución de notas
              </Typography>
              <Stack spacing={2} sx={{ mt: 2 }}>
                {Object.entries(data.distribution).map(([range, count]) => (
                  <Box key={range}>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                      <Typography variant="body2">{range}%</Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {count}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={(count / maxBucket) * 100}
                      color={range === '0-59' ? 'error' : range === '90-100' ? 'success' : 'primary'}
                      sx={{ height: 8, borderRadius: 4 }}
                    />
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="h4" gutterBottom>
                Preguntas más falladas
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Un índice de error alto suele señalar contenido poco claro en el material.
              </Typography>

              {data.hardest_questions.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  Todavía no hay respuestas suficientes.
                </Typography>
              ) : (
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Pregunta</TableCell>
                        <TableCell align="right">Respuestas</TableCell>
                        <TableCell align="right">Erradas</TableCell>
                        <TableCell align="right">% error</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data.hardest_questions.map((row) => (
                        <TableRow key={row.question_id} hover>
                          <TableCell sx={{ maxWidth: 380 }}>
                            <Typography variant="body2" noWrap title={row.statement}>
                              {row.statement}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">{row.attempts}</TableCell>
                          <TableCell align="right">{row.wrong}</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={`${row.error_rate}%`}
                              size="small"
                              color={
                                row.error_rate > 60
                                  ? 'error'
                                  : row.error_rate > 35
                                    ? 'warning'
                                    : 'default'
                              }
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
