/**
 * Avance de la generación de un examen, en vivo por WebSocket (CU-13).
 *
 * Generar un examen tarda decenas de minutos en CPU y la petición HTTP responde
 * `202` de inmediato, así que sin este seguimiento el usuario no puede
 * distinguir "trabajando" de "se colgó".
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket } from '@/shared/hooks/useWebSocket';
import type { WsMessage } from '@/shared/api/types';

export interface ExamGeneration {
  /** 0-100. */
  progress: number;
  /** Etapa informada por el backend: `queued`, `material`, `questions`, `done`. */
  step: string;
  questions: number;
  total: number;
  failed: boolean;
  message: string;
  startedAt: number;
}

/**
 * El avance sobrevive a una recarga de la página, pero no para siempre: si el
 * aviso de término se perdió (pestaña cerrada al terminar la tarea), el
 * registro caduca en vez de dejar una barra viva eternamente.
 */
const MAX_AGE_MS = 3 * 60 * 60 * 1000;

const storageKey = (trainingId: string) => `exam-generation:${trainingId}`;

function restore(trainingId: string): ExamGeneration | null {
  try {
    const raw = sessionStorage.getItem(storageKey(trainingId));
    if (!raw) return null;

    const parsed = JSON.parse(raw) as ExamGeneration;
    if (Date.now() - parsed.startedAt > MAX_AGE_MS) {
      sessionStorage.removeItem(storageKey(trainingId));
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function persist(trainingId: string, value: ExamGeneration | null): void {
  try {
    if (value) sessionStorage.setItem(storageKey(trainingId), JSON.stringify(value));
    else sessionStorage.removeItem(storageKey(trainingId));
  } catch {
    // Modo privado o cuota llena: el seguimiento en vivo sigue funcionando.
  }
}

export function useExamGeneration(trainingId: string, onFinished: () => void) {
  const [state, setState] = useState<ExamGeneration | null>(null);
  const stateRef = useRef<ExamGeneration | null>(null);
  const finishedRef = useRef(onFinished);

  finishedRef.current = onFinished;

  const write = useCallback(
    (next: ExamGeneration | null) => {
      stateRef.current = next;
      setState(next);
      persist(trainingId, next);
    },
    [trainingId],
  );

  // Al abrir el curso (o tras recargar) se recupera una generación en marcha.
  useEffect(() => {
    const restored = restore(trainingId);
    stateRef.current = restored;
    setState(restored);
  }, [trainingId]);

  const start = useCallback(
    (total: number) =>
      write({
        progress: 0,
        step: 'queued',
        questions: 0,
        total,
        failed: false,
        message: '',
        startedAt: Date.now(),
      }),
    [write],
  );

  const dismiss = useCallback(() => write(null), [write]);

  const handleMessage = useCallback(
    (message: WsMessage) => {
      if (message.type !== 'notification') return;
      if (String(message.training_id ?? '') !== trainingId) return;

      const previous = stateRef.current;

      switch (message.event) {
        case 'exam.generation_progress':
          write({
            progress: Number(message.progress ?? 0),
            step: String(message.step ?? ''),
            questions: Number(message.questions ?? 0),
            total: Number(message.total ?? previous?.total ?? 0),
            failed: false,
            message: '',
            startedAt: previous?.startedAt ?? Date.now(),
          });
          break;

        case 'exam.generated':
          write(null);
          finishedRef.current();
          break;

        case 'exam.generation_failed':
          write({
            progress: previous?.progress ?? 0,
            step: 'error',
            questions: Number(message.questions ?? previous?.questions ?? 0),
            total: previous?.total ?? 0,
            failed: true,
            message: String(message.message ?? 'La generación falló.'),
            startedAt: previous?.startedAt ?? Date.now(),
          });
          // Puede haber quedado un examen vacío en borrador: conviene refrescar.
          finishedRef.current();
          break;
      }
    },
    [trainingId, write],
  );

  // El socket solo se mantiene abierto mientras hay algo que seguir.
  const active = state !== null && !state.failed;

  useWebSocket({
    path: active ? 'notifications' : null,
    onMessage: handleMessage,
    enabled: active,
  });

  return { generation: state, start, dismiss };
}
