/**
 * Academia: catálogo de cursos publicados de la empresa.
 *
 * Solo se pueden realizar los cursos en los que el educador invitó al
 * estudiante; el resto se muestra bloqueado con esa indicación.
 */

import { LockOutlined, PlayArrow, School, Search } from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import Grid from '@mui/material/Grid2';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { MyTraining, Paginated, Training } from '@/shared/api/types';
import { EmptyState, ErrorState, Loading, PageHeader, ProgressBar } from '@/shared/components';
import { LEVEL_LABEL, formatDurationLong, progressValue } from '@/shared/utils/format';

const LEVELS = ['BEGINNER', 'INTERMEDIATE', 'ADVANCED'] as const;

export default function AcademyPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [level, setLevel] = useState('');

  const catalog = useQuery({
    queryKey: ['academy', 'catalog'],
    queryFn: async () =>
      (
        await api.get<Paginated<Training>>(endpoints.trainings.list, {
          params: { status: 'PUBLISHED', page_size: 100 },
        })
      ).data,
  });

  const mine = useQuery({
    queryKey: ['me', 'trainings'],
    queryFn: async () => (await api.get<Paginated<MyTraining>>(endpoints.me.trainings)).data,
  });

  /** Inscripciones indexadas por curso, para saber a cuáles fui invitado. */
  const enrollmentByTraining = useMemo(() => {
    const map = new Map<string, MyTraining>();
    for (const item of mine.data?.results ?? []) map.set(item.training_id, item);
    return map;
  }, [mine.data]);

  const items = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (catalog.data?.results ?? []).filter((training) => {
      if (level && training.level !== level) return false;
      if (!term) return true;
      return (
        training.title.toLowerCase().includes(term) ||
        training.description.toLowerCase().includes(term) ||
        training.project_name.toLowerCase().includes(term)
      );
    });
  }, [catalog.data, search, level]);

  if (catalog.isLoading) return <Loading label="Cargando la academia…" />;
  if (catalog.isError) return <ErrorState error={catalog.error} onRetry={catalog.refetch} />;

  return (
    <Box>
      <PageHeader
        title="Academia"
        subtitle="Cursos disponibles en tu empresa. Para realizar uno, tu educador debe invitarte."
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3, maxWidth: 640 }}>
        <TextField
          placeholder="¿Qué quieres aprender?"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        <TextField
          select
          label="Nivel"
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          sx={{ minWidth: { sm: 180 } }}
        >
          <MenuItem value="">Todos</MenuItem>
          {LEVELS.map((value) => (
            <MenuItem key={value} value={value}>
              {LEVEL_LABEL[value]}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      {items.length === 0 ? (
        <EmptyState
          icon={<School />}
          title="No hay cursos que coincidan"
          description="Ajusta la búsqueda o consulta con tu educador por nuevos cursos publicados."
        />
      ) : (
        <Grid container spacing={2.5}>
          {items.map((training) => (
            <Grid size={{ xs: 12, sm: 6, lg: 4, xl: 3 }} key={training.id}>
              <CatalogCard
                training={training}
                enrollment={enrollmentByTraining.get(training.id)}
                onOpen={() => navigate(`/cursos/${training.id}`)}
              />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}

function CatalogCard({
  training,
  enrollment,
  onOpen,
}: {
  training: Training;
  enrollment?: MyTraining;
  onOpen: () => void;
}) {
  const enrolled = Boolean(enrollment);
  const progress = progressValue(enrollment?.progress);

  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ p: { xs: 2, sm: 2.5 }, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          <Chip label={training.project_name} size="small" variant="outlined" />
          <Chip label={LEVEL_LABEL[training.level] ?? training.level} size="small" />
          {enrolled ? (
            <Chip label="Inscrito" size="small" color="success" />
          ) : (
            <Chip
              label="Requiere invitación"
              size="small"
              icon={<LockOutlined />}
              variant="outlined"
            />
          )}
        </Stack>

        <Typography variant="h4" gutterBottom>
          {training.title}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            mb: 2,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {training.description || 'Sin descripción.'}
        </Typography>

        <Box sx={{ mt: 'auto' }}>
          {enrolled && <ProgressBar value={progress} />}
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mt: enrolled ? 1.5 : 0 }}
          >
            <Typography variant="caption" color="text.secondary">
              {training.lesson_count} clases · {formatDurationLong(training.estimated_minutes * 60)}
            </Typography>
            {enrolled ? (
              <Button size="small" variant="contained" startIcon={<PlayArrow />} onClick={onOpen}>
                {progress > 0 ? 'Continuar' : 'Comenzar'}
              </Button>
            ) : (
              <Tooltip title="Tu educador debe invitarte para realizar este curso.">
                <span>
                  <Button size="small" variant="outlined" startIcon={<LockOutlined />} disabled>
                    Bloqueado
                  </Button>
                </span>
              </Tooltip>
            )}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}
