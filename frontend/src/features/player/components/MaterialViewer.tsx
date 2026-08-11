/**
 * Visor del material de la lección dentro de la plataforma.
 *
 * Video y audio se reproducen en línea; el PDF se muestra en el visor del
 * navegador; Word, PowerPoint y texto plano se leen con el texto extraído por
 * el backend, porque el navegador no sabe representarlos.
 */

import { Audiotrack, Description, Download, OpenInNew, PlayCircle } from '@mui/icons-material';
import { Box, Button, Divider, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { Material, MaterialContent } from '@/shared/api/types';
import { ErrorState, Loading } from '@/shared/components';

/** Tipos que el navegador no puede representar y se leen como texto. */
const TEXT_TYPES = new Set(['DOCX', 'PPTX', 'TXT', 'MD']);

const VIEWER_HEIGHT = '62vh';

export interface MaterialViewerProps {
  material?: Material;
  streamUrl?: string;
  /** Ref por callback: sirve igual para `<video>` que para `<audio>`. */
  onMediaRef: (element: HTMLMediaElement | null) => void;
  onLoadedMetadata: () => void;
  onTimeUpdate: () => void;
  onEnded: () => void;
}

export function MaterialViewer({
  material,
  streamUrl,
  onMediaRef,
  onLoadedMetadata,
  onTimeUpdate,
  onEnded,
}: MaterialViewerProps) {
  if (!material) {
    return (
      <Placeholder icon={<PlayCircle />} message="Esta lección aún no tiene material disponible." />
    );
  }

  if (!streamUrl) {
    return <Placeholder icon={<Description />} message="Preparando el material…" />;
  }

  if (material.type === 'VIDEO') {
    return (
      <video
        ref={onMediaRef}
        key={material.id}
        src={streamUrl}
        controls
        controlsList="nodownload"
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={onTimeUpdate}
        onEnded={onEnded}
        style={{ width: '100%', maxHeight: '58vh', display: 'block' }}
      />
    );
  }

  if (material.type === 'AUDIO') {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Audiotrack sx={{ fontSize: 44, mb: 2, color: 'grey.500' }} />
        <audio
          ref={onMediaRef}
          key={material.id}
          src={streamUrl}
          controls
          onLoadedMetadata={onLoadedMetadata}
          onTimeUpdate={onTimeUpdate}
          onEnded={onEnded}
          style={{ width: '100%' }}
        />
      </Box>
    );
  }

  if (material.type === 'PDF') {
    return (
      <Box sx={{ bgcolor: 'background.paper' }}>
        <DocumentToolbar material={material} url={streamUrl} />
        <Box
          component="iframe"
          key={material.id}
          src={`${streamUrl}#view=FitH`}
          title={material.original_filename}
          sx={{ width: '100%', height: VIEWER_HEIGHT, border: 0, display: 'block' }}
        />
      </Box>
    );
  }

  if (TEXT_TYPES.has(material.type)) {
    return <TextDocument material={material} url={streamUrl} />;
  }

  return (
    <Box sx={{ bgcolor: 'background.paper' }}>
      <DocumentToolbar material={material} url={streamUrl} />
      <Placeholder
        icon={<Description />}
        message="Este formato no se puede mostrar en el navegador; ábrelo o descárgalo."
      />
    </Box>
  );
}

function TextDocument({ material, url }: { material: Material; url: string }) {
  const content = useQuery({
    queryKey: ['material', material.id, 'content'],
    queryFn: async () =>
      (await api.get<MaterialContent>(endpoints.materials.content(material.id))).data,
    retry: false,
  });

  return (
    <Box sx={{ bgcolor: 'background.paper' }}>
      <DocumentToolbar material={material} url={url} />
      <Box sx={{ height: VIEWER_HEIGHT, overflowY: 'auto', px: 3, py: 2 }}>
        {content.isLoading && <Loading label="Cargando el documento…" />}
        {content.isError && (
          <ErrorState error={content.error} onRetry={() => content.refetch()} />
        )}
        {content.data && (
          <Stack spacing={1.5}>
            {content.data.blocks.map((block, index) => (
              <Box key={`${block.order}-${index}`}>
                {block.page !== null && block.page !== content.data.blocks[index - 1]?.page && (
                  <>
                    {index > 0 && <Divider sx={{ my: 2 }} />}
                    <Typography variant="caption" color="text.secondary">
                      Página {block.page}
                    </Typography>
                  </>
                )}
                {block.heading && (
                  <Typography variant="subtitle2" sx={{ mt: 1 }}>
                    {block.heading}
                  </Typography>
                )}
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {block.text}
                </Typography>
              </Box>
            ))}
            {content.data.blocks.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                El documento no tiene texto legible; descárgalo para revisarlo.
              </Typography>
            )}
          </Stack>
        )}
      </Box>
    </Box>
  );
}

function DocumentToolbar({ material, url }: { material: Material; url: string }) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      justifyContent="space-between"
      spacing={1.5}
      sx={{ px: 2, py: 1, borderBottom: 1, borderColor: 'divider' }}
    >
      <Typography variant="caption" color="text.secondary" noWrap>
        {material.original_filename}
        {material.page_count > 0 && ` · ${material.page_count} págs.`}
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          startIcon={<OpenInNew />}
          href={url}
          target="_blank"
          rel="noreferrer"
        >
          Abrir
        </Button>
        <Button
          size="small"
          startIcon={<Download />}
          href={url}
          download={material.original_filename}
        >
          Descargar
        </Button>
      </Stack>
    </Stack>
  );
}

function Placeholder({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <Paper elevation={0} sx={{ py: 8, textAlign: 'center', color: 'text.secondary' }}>
      <Box sx={{ '& svg': { fontSize: 44 }, mb: 1 }}>{icon}</Box>
      <Typography variant="body2">{message}</Typography>
    </Paper>
  );
}
