/**
 * Conexión al contenedor `websocket` (Daphne), independiente del backend HTTP.
 *
 * Reconecta con backoff exponencial y adjunta el JWT por query string, porque
 * el handshake de WebSocket no admite cabeceras personalizadas.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { tokenStorage } from '@/shared/api/client';
import type { WsMessage } from '@/shared/api/types';

const WS_BASE = import.meta.env.VITE_WS_URL ?? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;

const MAX_RETRIES = 6;

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

interface Options {
  /** Ruta relativa dentro de /ws, p. ej. `materials/<id>` */
  path: string | null;
  onMessage?: (message: WsMessage) => void;
  enabled?: boolean;
}

export function useWebSocket({ path, onMessage, enabled = true }: Options) {
  const [status, setStatus] = useState<WsStatus>('closed');
  const socketRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const handlerRef = useRef(onMessage);

  handlerRef.current = onMessage;

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const socket = socketRef.current;
    if (!socket) return;
    socketRef.current = null;

    // Se anulan los handlers para que este cierre no dispare una reconexión.
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;

    if (socket.readyState === WebSocket.CONNECTING) {
      // Cerrar durante el handshake provoca el aviso del navegador
      // "closed before the connection is established". En React StrictMode el
      // efecto se monta y desmonta dos veces, así que esto ocurre siempre en
      // desarrollo: se espera a que abra y recién ahí se cierra limpiamente.
      socket.onopen = () => socket.close(1000, 'cleanup');
      return;
    }

    socket.onopen = null;
    if (socket.readyState === WebSocket.OPEN) {
      socket.close(1000, 'cleanup');
    }
  }, []);

  const connect = useCallback(() => {
    if (!path || !enabled) return;
    const token = tokenStorage.access;
    if (!token) return;

    setStatus('connecting');
    const socket = new WebSocket(`${WS_BASE}/${path}/?token=${encodeURIComponent(token)}`);
    socketRef.current = socket;

    socket.onopen = () => {
      retriesRef.current = 0;
      setStatus('open');
    };

    socket.onmessage = (event) => {
      try {
        handlerRef.current?.(JSON.parse(event.data) as WsMessage);
      } catch {
        // Un mensaje mal formado no debe tumbar la conexión.
      }
    };

    socket.onerror = () => setStatus('error');

    socket.onclose = (event) => {
      setStatus('closed');
      // 4401/4403: el servidor rechazó la credencial → reintentar no sirve.
      if (event.code === 4401 || event.code === 4403) return;
      if (retriesRef.current >= MAX_RETRIES) return;

      const delay = Math.min(1000 * 2 ** retriesRef.current, 20_000);
      retriesRef.current += 1;
      timerRef.current = window.setTimeout(connect, delay);
    };
  }, [path, enabled]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  const send = useCallback((payload: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  return { status, send, reconnect: connect };
}
