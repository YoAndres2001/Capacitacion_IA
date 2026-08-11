/** Revisión del análisis que produjo la IA sobre un material (HU-023). */

import { ArrowBack, AutoAwesome, Refresh } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  IconButton,
  LinearProgress,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, errorMessage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Chapter, Concept, Faq, Material, Transcript } from '@/shared/api/types';
import { ErrorState, Loading, PageHeader, StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { formatDuration, formatDurationLong } from '@/shared/utils/format';

export default function MaterialAnalysisPage() {
  const { materialId = '' } = useParams();
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const [tab, setTab] = useState('summary');

  const material = useQuery({
    queryKey: ['material', materialId],
    queryFn: async () => (await api.get<Material>(endpoints.materials.detail(materialId))).data,
  });

  const available = material.data?.status === 'AVAILABLE';

  const transcript = useQuery({
    queryKey: ['material', materialId, 'transcript'],
    queryFn: async () =>
      (await api.get<Transcript>(endpoints.materials.transcript(materialId))).data,
    enabled: available && tab === 'transcript',
    retry: false,
  });

  const chapters = useQuery({
    queryKey: ['material', materialId, 'chapters'],
    queryFn: async () => (await api.get<Chapter[]>(endpoints.materials.chapters(materialId))).data,
    enabled: available,
  });

  const concepts = useQuery({
    queryKey: ['material', materialId, 'concepts'],
    queryFn: async () => (await api.get<Concept[]>(endpoints.materials.concepts(materialId))).data,
    enabled: available && tab === 'concepts',
  });

  const faqs = useQuery({
    queryKey: ['material', materialId, 'faqs'],
    queryFn: async () => (await api.get<Faq[]>(endpoints.materials.faqs(materialId))).data,
    enabled: available && tab === 'faqs',
  });

  const reprocess = useMutation({
    mutationFn: () => api.post(endpoints.materials.reprocess(materialId)),
    onSuccess: () => snackbar.info('Reprocesamiento encolado.'),
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  if (material.isLoading) return <Loading />;
  if (material.isError) return <ErrorState error={material.error} onRetry={material.refetch} />;

  const data = material.data!;

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton onClick={() => navigate(-1)} aria-label="Volver">
          <ArrowBack />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          Análisis del material
        </Typography>
      </Stack>

      <PageHeader
        title={data.original_filename}
        subtitle={[
          data.type,
          data.duration_seconds > 0 && formatDurationLong(data.duration_seconds),
          data.page_count > 0 && `${data.page_count} páginas`,
          data.language && `idioma: ${data.language}`,
        ]
          .filter(Boolean)
          .join(' · ')}
        actions={
          <>
            <StatusChip status={data.status} />
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={() => reprocess.mutate()}
              disabled={reprocess.isPending || !['AVAILABLE', 'ERROR'].includes(data.status)}
            >
              Reprocesar
            </Button>
          </>
        }
      />

      {!available && data.status !== 'ERROR' && (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ py: 4, textAlign: 'center' }}>
            <AutoAwesome sx={{ fontSize: 42, color: 'primary.main', mb: 1 }} />
            <Typography variant="h4" gutterBottom>
              La IA está procesando este material
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Transcripción, capítulos, conceptos y embeddings se generan en segundo plano.
            </Typography>
            <LinearProgress sx={{ maxWidth: 360, mx: 'auto', borderRadius: 4 }} />
          </CardContent>
        </Card>
      )}

      {data.status === 'ERROR' && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="subtitle2">{data.error_code}</Typography>
          <Typography variant="body2">{data.error_detail}</Typography>
        </Alert>
      )}

      {data.partial_analysis && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          El análisis quedó parcial: los embeddings se generaron correctamente (el chat funciona),
          pero alguna cadena del LLM falló. Puedes reprocesar para completarlo.
        </Alert>
      )}

      {available && (
        <>
          <Tabs
            value={tab}
            onChange={(_, value) => setTab(value)}
            sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label="Resumen" value="summary" />
            <Tab label={`Capítulos (${chapters.data?.length ?? 0})`} value="chapters" />
            <Tab label="Conceptos" value="concepts" />
            <Tab label="Preguntas frecuentes" value="faqs" />
            <Tab label="Transcripción" value="transcript" />
          </Tabs>

          {tab === 'summary' && (
            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                <Typography variant="h4" gutterBottom>
                  Resumen ejecutivo
                </Typography>
                <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.75 }}>
                  {data.summary || 'La IA no generó resumen para este material.'}
                </Typography>
              </CardContent>
            </Card>
          )}

          {tab === 'chapters' && (
            <Stack spacing={1.5}>
              {(chapters.data ?? []).map((chapter, index) => (
                <Card key={chapter.id} variant="outlined">
                  <CardContent sx={{ py: 2 }}>
                    <Stack direction="row" spacing={1.5} alignItems="flex-start">
                      <Chip label={index + 1} size="small" />
                      <Box sx={{ flex: 1 }}>
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                          <Typography variant="subtitle1">{chapter.title}</Typography>
                          {chapter.start_time !== null && (
                            <Chip
                              label={`${formatDuration(chapter.start_time)} – ${formatDuration(chapter.end_time ?? 0)}`}
                              size="small"
                              variant="outlined"
                            />
                          )}
                          {chapter.start_page !== null && (
                            <Chip
                              label={`págs. ${chapter.start_page}–${chapter.end_page ?? chapter.start_page}`}
                              size="small"
                              variant="outlined"
                            />
                          )}
                        </Stack>
                        {chapter.summary && (
                          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                            {chapter.summary}
                          </Typography>
                        )}
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              ))}
              {(chapters.data?.length ?? 0) === 0 && (
                <Typography variant="body2" color="text.secondary">
                  No se detectaron capítulos.
                </Typography>
              )}
            </Stack>
          )}

          {tab === 'concepts' && (
            <Stack spacing={1.5}>
              {(concepts.data ?? []).map((concept) => (
                <Card key={concept.id} variant="outlined">
                  <CardContent sx={{ py: 2 }}>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="center"
                      spacing={1}
                      flexWrap="wrap"
                      useFlexGap
                    >
                      <Typography variant="subtitle1">{concept.name}</Typography>
                      <Chip
                        label={`relevancia ${(concept.relevance * 100).toFixed(0)}%`}
                        size="small"
                        color={concept.relevance > 0.7 ? 'primary' : 'default'}
                      />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                      {concept.definition}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
              {(concepts.data?.length ?? 0) === 0 && !concepts.isLoading && (
                <Typography variant="body2" color="text.secondary">
                  No se extrajeron conceptos.
                </Typography>
              )}
            </Stack>
          )}

          {tab === 'faqs' && (
            <Stack spacing={1.5}>
              {(faqs.data ?? []).map((faq) => (
                <Card key={faq.id} variant="outlined">
                  <CardContent sx={{ py: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      {faq.question}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {faq.answer}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
              {(faqs.data?.length ?? 0) === 0 && !faqs.isLoading && (
                <Typography variant="body2" color="text.secondary">
                  No se generaron preguntas frecuentes.
                </Typography>
              )}
            </Stack>
          )}

          {tab === 'transcript' && (
            <Card>
              <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                {transcript.isLoading && <Loading label="Cargando transcripción…" />}
                {transcript.isError && (
                  <Typography variant="body2" color="text.secondary">
                    Este material no tiene transcripción (solo los videos y audios la generan).
                  </Typography>
                )}
                {transcript.data && (
                  <>
                    <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                      <Chip label={`Idioma: ${transcript.data.language}`} size="small" />
                      <Chip label={transcript.data.model} size="small" variant="outlined" />
                      <Chip
                        label={`${transcript.data.segments.length} segmentos`}
                        size="small"
                        variant="outlined"
                      />
                    </Stack>
                    <Divider sx={{ mb: 2 }} />
                    <Stack spacing={1} sx={{ maxHeight: { xs: '55vh', md: 560 }, overflowY: 'auto' }}>
                      {transcript.data.segments.map((segment) => (
                        <Stack key={segment.index} direction="row" spacing={1.5}>
                          <Typography
                            variant="caption"
                            color="primary.main"
                            sx={{ minWidth: 56, fontVariantNumeric: 'tabular-nums' }}
                          >
                            {formatDuration(segment.start_time)}
                          </Typography>
                          <Typography variant="body2">{segment.text}</Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </Box>
  );
}
