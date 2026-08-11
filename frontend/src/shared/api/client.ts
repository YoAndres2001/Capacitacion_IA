/**
 * Cliente HTTP único de la aplicación.
 *
 * Responsabilidades: adjuntar el JWT, refrescarlo automáticamente ante un 401
 * (encolando las peticiones concurrentes para no disparar N refrescos) y
 * normalizar el formato de error de la API.
 */

import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import type { ApiError } from './types';

const API_URL = import.meta.env.VITE_API_URL ?? '/api/v1';

const ACCESS_KEY = 'nexora.access';
const REFRESH_KEY = 'nexora.refresh';

export const tokenStorage = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiException extends Error {
  constructor(
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public status = 0,
  ) {
    super(message);
    this.name = 'ApiException';
  }
}

export const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Refresco de token con cola ───────────────────────────────
let refreshing: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStorage.refresh;
  if (!refresh) throw new ApiException('NO_REFRESH_TOKEN', 'Sesión expirada.');

  // Instancia limpia: evita que el interceptor reintente en bucle.
  const { data } = await axios.post<{ access: string; refresh?: string }>(
    `${API_URL}/auth/refresh`,
    { refresh },
    { headers: { 'Content-Type': 'application/json' } },
  );
  tokenStorage.set(data.access, data.refresh);
  return data.access;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };

    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      try {
        refreshing = refreshing ?? refreshAccessToken().finally(() => (refreshing = null));
        const token = await refreshing;
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      } catch {
        tokenStorage.clear();
        if (!location.pathname.startsWith('/login')) {
          location.href = '/login?expired=1';
        }
      }
    }

    return Promise.reject(toApiException(error));
  },
);

function toApiException(error: AxiosError<ApiError>): ApiException {
  const status = error.response?.status ?? 0;
  const payload = error.response?.data;

  if (payload?.error) {
    return new ApiException(
      payload.error.code,
      payload.error.message,
      payload.error.details ?? {},
      status,
    );
  }
  if (error.code === 'ECONNABORTED') {
    return new ApiException('TIMEOUT', 'La operación tardó demasiado. Inténtalo de nuevo.', {}, status);
  }
  if (!error.response) {
    return new ApiException('NETWORK_ERROR', 'No se pudo conectar con el servidor.', {}, 0);
  }
  return new ApiException('UNKNOWN_ERROR', error.message || 'Error inesperado.', {}, status);
}

/** Mensaje listo para mostrar al usuario. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiException) return error.message;
  if (error instanceof Error) return error.message;
  return 'Ocurrió un error inesperado.';
}
