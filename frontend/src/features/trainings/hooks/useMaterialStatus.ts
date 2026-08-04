/** Estado de procesamiento de un material, en vivo por WebSocket. */

import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from '@/shared/hooks/useWebSocket';
import type { MaterialStatus, WsMessage } from '@/shared/api/types';

interface LiveStatus {
  status: MaterialStatus;
  step: string;
  progress: number;
  errorCode: string | null;
}

export function useMaterialStatus(materialId: string, initialStatus: MaterialStatus): LiveStatus {
  const queryClient = useQueryClient();
  const [state, setState] = useState<LiveStatus>({
    status: initialStatus,
    step: '',
    progress: initialStatus === 'AVAILABLE' ? 100 : 0,
    errorCode: null,
  });

  // Si el listado se recarga con otro estado, se sincroniza.
  useEffect(() => {
    setState((previous) =>
      previous.status === initialStatus ? previous : { ...previous, status: initialStatus },
    );
  }, [initialStatus]);

  const handleMessage = useCallback(
    (message: WsMessage) => {
      if (message.type !== 'status.changed') return;

      setState({
        status: message.status,
        step: message.step,
        progress: message.progress,
        errorCode: message.error_code,
      });

      // Al terminar, refrescamos los datos del curso para traer los artefactos.
      if (message.status === 'AVAILABLE' || message.status === 'ERROR') {
        void queryClient.invalidateQueries({ queryKey: ['training'] });
        void queryClient.invalidateQueries({ queryKey: ['material', materialId] });
      }
    },
    [queryClient, materialId],
  );

  // Solo mantenemos abierto el socket mientras el material está en proceso.
  const active = ['PENDING', 'PROCESSING', 'ANALYZING'].includes(state.status);

  useWebSocket({
    path: active ? `materials/${materialId}` : null,
    onMessage: handleMessage,
    enabled: active,
  });

  return state;
}
