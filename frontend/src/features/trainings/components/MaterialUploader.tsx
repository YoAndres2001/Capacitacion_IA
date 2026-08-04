/**
 * Carga de material con progreso y seguimiento del pipeline en vivo.
 *
 * Archivos pequeños van por multipart; los grandes (video) se envían por trozos
 * reanudables. Al terminar, el componente se suscribe al canal WebSocket del
 * material para mostrar el avance del procesamiento sin recargar la página.
 */

import { CloudUpload, Delete, InsertDriveFile, Refresh, Visibility } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { api, errorMessage, tokenStorage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Material } from '@/shared/api/types';
import { StatusChip } from '@/shared/components';
import { useSnackbar } from '@/shared/components/SnackbarProvider';
import { useMaterialStatus } from '@/features/trainings/hooks/useMaterialStatus';
import { MATERIAL_STEP_LABEL, formatBytes, formatDurationLong } from '@/shared/utils/format';

/** A partir de este tamaño conviene la carga por trozos reanudable. */
const CHUNKED_THRESHOLD = 20 * 1024 * 1024;

const ACCEPTED = '.mp4,.mov,.mkv,.webm,.avi,.mp3,.wav,.m4a,.pdf,.docx,.pptx,.txt,.md';

interface Props {
  lessonId: string;
  materials: Material[];
  onChanged: () => void;
}

export function MaterialUploader({ lessonId, materials, onChanged }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const snackbar = useSnackbar();
  const queryClient = useQueryClient();
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadName, setUploadName] = useState('');

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setUploadName(file.name);
      setUploadProgress(0);
      return file.size > CHUNKED_THRESHOLD
        ? uploadChunked(lessonId, file, setUploadProgress)
        : uploadDirect(lessonId, file, setUploadProgress);
    },
    onSuccess: () => {
      snackbar.success('Material cargado. La IA comenzó a procesarlo.');
      onChanged();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
    onSettled: () => {
      setUploadProgress(null);
      setUploadName('');
      if (inputRef.current) inputRef.current.value = '';
    },
  });

  const remove = useMutation({
    mutationFn: (materialId: string) => api.delete(endpoints.materials.detail(materialId)),
    onSuccess: () => {
      snackbar.info('Material eliminado.');
      onChanged();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const reprocess = useMutation({
    mutationFn: (materialId: string) => api.post(endpoints.materials.reprocess(materialId)),
    onSuccess: async () => {
      snackbar.info('Reprocesamiento encolado.');
      await queryClient.invalidateQueries({ queryKey: ['training'] });
      onChanged();
    },
    onError: (error) => snackbar.error(errorMessage(error)),
  });

  const handleFile = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) upload.mutate(file);
    },
    [upload],
  );

  return (
    <Box>
      <Stack spacing={1.5}>
        {materials.map((material) => (
          <MaterialRow
            key={material.id}
            material={material}
            onDelete={() => remove.mutate(material.id)}
            onReprocess={() => reprocess.mutate(material.id)}
          />
        ))}
      </Stack>

      {uploadProgress !== null && (
        <Paper variant="outlined" sx={{ p: 2, mt: 1.5 }}>
          <Typography variant="body2" gutterBottom noWrap>
            Subiendo {uploadName}
          </Typography>
          <LinearProgress variant="determinate" value={uploadProgress} sx={{ height: 6, borderRadius: 3 }} />
          <Typography variant="caption" color="text.secondary">
            {uploadProgress.toFixed(0)}%
          </Typography>
        </Paper>
      )}

      <Box sx={{ mt: 1.5 }}>
        <input
          ref={inputRef}
          type="file"
          hidden
          accept={ACCEPTED}
          onChange={handleFile}
        />
        <Button
          variant="outlined"
          size="small"
          startIcon={<CloudUpload />}
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
        >
          {upload.isPending ? 'Subiendo…' : 'Subir video o documento'}
        </Button>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
          MP4, MOV, MKV, WEBM, MP3, PDF, DOCX, PPTX, TXT o MD. Video hasta 4 GB.
        </Typography>
      </Box>
    </Box>
  );
}

function MaterialRow({
  material,
  onDelete,
  onReprocess,
}: {
  material: Material;
  onDelete: () => void;
  onReprocess: () => void;
}) {
  // El canal WebSocket entrega el avance del pipeline en tiempo real.
  const live = useMaterialStatus(material.id, material.status);
  const inProgress = ['PENDING', 'PROCESSING', 'ANALYZING'].includes(live.status);

  return (
    <Paper variant="outlined" sx={{ p: 1.75 }}>
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <InsertDriveFile color="action" />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            {material.original_filename}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="caption" color="text.secondary">
              {formatBytes(material.size_bytes)}
            </Typography>
            {material.duration_seconds > 0 && (
              <Typography variant="caption" color="text.secondary">
                · {formatDurationLong(material.duration_seconds)}
              </Typography>
            )}
            {material.page_count > 0 && (
              <Typography variant="caption" color="text.secondary">
                · {material.page_count} páginas
              </Typography>
            )}
            {material.partial_analysis && (
              <Chip label="Análisis parcial" size="small" color="warning" variant="outlined" />
            )}
          </Stack>
        </Box>

        <StatusChip status={live.status} />

        {live.status === 'AVAILABLE' && (
          <Tooltip title="Ver análisis de la IA">
            <IconButton component={RouterLink} to={`/materiales/${material.id}`} size="small">
              <Visibility fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        {['AVAILABLE', 'ERROR'].includes(live.status) && (
          <Tooltip title="Reprocesar">
            <IconButton onClick={onReprocess} size="small">
              <Refresh fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Eliminar">
          <IconButton onClick={onDelete} size="small" color="error">
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      {inProgress && (
        <Box sx={{ mt: 1.5 }}>
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {MATERIAL_STEP_LABEL[live.step] ?? 'Procesando'}
            </Typography>
            <Typography variant="caption">{live.progress}%</Typography>
          </Stack>
          <LinearProgress
            variant={live.progress > 0 ? 'determinate' : 'indeterminate'}
            value={live.progress}
            sx={{ height: 5, borderRadius: 3 }}
          />
        </Box>
      )}

      {live.status === 'ERROR' && (
        <Alert severity="error" sx={{ mt: 1.5 }} variant="outlined">
          <Typography variant="caption" component="div" fontWeight={600}>
            {live.errorCode || material.error_code}
          </Typography>
          {material.error_detail && (
            <Typography variant="caption">{material.error_detail}</Typography>
          )}
        </Alert>
      )}
    </Paper>
  );
}

// ── Estrategias de carga ─────────────────────────────────────
async function uploadDirect(
  lessonId: string,
  file: File,
  onProgress: (value: number) => void,
): Promise<Material> {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await api.post<Material>(endpoints.lessons.uploadMaterial(lessonId), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (event.total) onProgress((event.loaded / event.total) * 100);
    },
  });
  return data;
}

async function uploadChunked(
  lessonId: string,
  file: File,
  onProgress: (value: number) => void,
): Promise<Material> {
  const { data: session } = await api.post<{ id: string; chunk_size: number; total_chunks: number }>(
    endpoints.lessons.uploadSession(lessonId),
    { filename: file.name, size_bytes: file.size, mime_type: file.type },
  );

  const total = session.total_chunks;
  const token = tokenStorage.access;

  for (let index = 0; index < total; index += 1) {
    const start = index * session.chunk_size;
    const blob = file.slice(start, start + session.chunk_size);

    const formData = new FormData();
    formData.append('chunk', blob);

    // Se usa fetch para no arrastrar cabeceras JSON en el envío binario.
    const response = await fetch(
      `${api.defaults.baseURL}${endpoints.materials.uploadChunk(session.id)}?index=${index}`,
      {
        method: 'PUT',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      },
    );
    if (!response.ok) {
      throw new Error(`Falló el envío del trozo ${index + 1} de ${total}.`);
    }
    onProgress(((index + 1) / total) * 100);
  }

  const { data } = await api.post<Material>(endpoints.materials.uploadComplete(session.id));
  return data;
}
