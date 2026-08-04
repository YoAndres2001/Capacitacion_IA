/** Utilidades de formato compartidas. */

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

export function formatDurationLong(seconds: number | null | undefined): string {
  if (!seconds) return '—';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours > 0) return `${hours} h ${minutes} min`;
  return `${minutes} min`;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('es-CL', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('es-CL', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '—';
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return 'hace un momento';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `hace ${days} d`;
  return formatDate(value);
}

export const STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pendiente',
  PROCESSING: 'Procesando',
  ANALYZING: 'Analizando',
  AVAILABLE: 'Disponible',
  ERROR: 'Error',
  DRAFT: 'Borrador',
  PUBLISHED: 'Publicada',
  ARCHIVED: 'Archivada',
  ASSIGNED: 'Asignada',
  IN_PROGRESS: 'En curso',
  COMPLETED: 'Completada',
  EXPIRED: 'Vencida',
  SUBMITTED: 'Entregado',
  GRADING: 'Corrigiendo',
  GRADED: 'Corregido',
};

export const LEVEL_LABEL: Record<string, string> = {
  BEGINNER: 'Principiante',
  INTERMEDIATE: 'Intermedio',
  ADVANCED: 'Avanzado',
};

export const ROLE_LABEL: Record<string, string> = {
  SUPERADMIN: 'Superadministrador',
  ADMIN: 'Administrador',
  INSTRUCTOR: 'Instructor',
  STUDENT: 'Estudiante',
};

export const QUESTION_TYPE_LABEL: Record<string, string> = {
  SINGLE_CHOICE: 'Selección única',
  MULTIPLE_CHOICE: 'Selección múltiple',
  TRUE_FALSE: 'Verdadero / Falso',
  SHORT_ANSWER: 'Respuesta corta',
  OPEN_ENDED: 'Pregunta abierta',
};

export const MATERIAL_STEP_LABEL: Record<string, string> = {
  start: 'Iniciando',
  extract: 'Extrayendo contenido',
  transcription: 'Transcribiendo audio',
  extraction: 'Extrayendo documento',
  chunking: 'Fragmentando',
  embeddings: 'Generando embeddings',
  analysis: 'Analizando con IA',
  done: 'Completado',
  error: 'Error',
};

export function progressValue(progress: string | number | null | undefined): number {
  if (progress === null || progress === undefined) return 0;
  const value = typeof progress === 'string' ? Number.parseFloat(progress) : progress;
  return Number.isFinite(value) ? value : 0;
}
