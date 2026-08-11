/**
 * Tipos del contrato de la API (docs/10-api-rest.md).
 *
 * Se mantienen a mano y no generados para que el editor los muestre con la
 * documentación en español y sin ruido del generador.
 */

export type Role = 'SUPERADMIN' | 'ADMIN' | 'INSTRUCTOR' | 'STUDENT';

export type MaterialStatus = 'PENDING' | 'PROCESSING' | 'ANALYZING' | 'AVAILABLE' | 'ERROR';
export type MaterialType = 'VIDEO' | 'PDF' | 'DOCX' | 'PPTX' | 'TXT' | 'MD' | 'AUDIO';
export type TrainingStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
export type TrainingLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';
export type LessonType = 'VIDEO' | 'DOCUMENT' | 'TEXT' | 'QUIZ';
export type EnrollmentStatus = 'ASSIGNED' | 'IN_PROGRESS' | 'COMPLETED' | 'EXPIRED';
export type ExamStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
export type AttemptStatus = 'IN_PROGRESS' | 'SUBMITTED' | 'GRADING' | 'GRADED' | 'EXPIRED';
export type QuestionType =
  | 'SINGLE_CHOICE'
  | 'MULTIPLE_CHOICE'
  | 'TRUE_FALSE'
  | 'SHORT_ANSWER'
  | 'OPEN_ENDED';

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

export interface CompanyBrief {
  id: string;
  name: string;
  slug: string;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: Role;
  company: CompanyBrief | null;
  job_title: string;
  avatar: string | null;
  phone: string;
  language: string;
  timezone: string;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

export interface Profile extends Omit<User, 'is_active' | 'created_at'> {
  permissions: {
    manage_users: boolean;
    manage_content: boolean;
    view_analytics: boolean;
    generate_exams: boolean;
  };
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: Profile;
}

export interface VectorCollection {
  id: string;
  status: 'PENDING' | 'READY' | 'REBUILDING' | 'ERROR';
  embedding_model: string;
  provider: string;
  dimension: number;
  vector_count: number;
  index_type: string;
  version: number;
  last_rebuilt_at: string | null;
  error_detail: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  code: string;
  description: string;
  color: string;
  icon: string;
  status: 'ACTIVE' | 'ARCHIVED';
  training_count: number;
  material_count: number;
  vector_collection: VectorCollection | null;
  created_at: string;
  updated_at: string;
}

export interface Material {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  type: MaterialType;
  status: MaterialStatus;
  error_code: string;
  error_detail: string;
  duration_seconds: number;
  page_count: number;
  language: string;
  summary: string;
  partial_analysis: boolean;
  is_queryable: boolean;
  processed_at: string | null;
  created_at: string;
}

export interface Lesson {
  id: string;
  module: string;
  title: string;
  description: string;
  type: LessonType;
  order: number;
  duration_seconds: number;
  is_mandatory: boolean;
  content: string;
  materials: Material[];
  created_at: string;
}

export interface TrainingModule {
  id: string;
  training: string;
  title: string;
  description: string;
  order: number;
  lessons: Lesson[];
  lesson_count: number;
  created_at: string;
}

export interface Training {
  id: string;
  project: string;
  project_name: string;
  title: string;
  slug: string;
  description: string;
  level: TrainingLevel;
  cover_image: string | null;
  estimated_minutes: number;
  status: TrainingStatus;
  chat_enabled: boolean;
  cross_material_search: boolean;
  created_by: User | null;
  module_count: number;
  lesson_count: number;
  enrollment_count: number;
  can_be_published: boolean;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingDetail extends Training {
  modules: TrainingModule[];
}

export interface LessonProgress {
  id: string;
  lesson: string;
  completed: boolean;
  position_seconds: number;
  watched_seconds: number;
  last_viewed_at: string | null;
  completed_at: string | null;
}

export interface MyTraining {
  id: string;
  training_id: string;
  title: string;
  description: string;
  level: TrainingLevel;
  cover_image: string | null;
  estimated_minutes: number;
  project_name: string;
  chat_enabled: boolean;
  status: EnrollmentStatus;
  progress: string;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
  due_date: string | null;
}

export interface MyTrainingDetail extends TrainingDetail {
  /** Nulo en la vista previa del instructor: sin matrícula no hay progreso. */
  enrollment: MyTraining | null;
  lesson_progress: Record<string, LessonProgress>;
  preview: boolean;
}

export interface Enrollment {
  id: string;
  user: User;
  training: string;
  training_title: string;
  project_name: string;
  status: EnrollmentStatus;
  progress: string;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
  due_date: string | null;
}

export interface TranscriptSegment {
  index: number;
  start_time: number;
  end_time: number;
  text: string;
}

export interface Transcript {
  id: string;
  language: string;
  model: string;
  confidence: number;
  full_text: string;
  segments: TranscriptSegment[];
}

/** Texto de un documento para leerlo dentro del reproductor. */
export interface MaterialContent {
  material_id: string;
  type: MaterialType;
  page_count: number;
  blocks: Array<{ order: number; page: number | null; heading: string; text: string }>;
}

export interface Chapter {
  id: string;
  order: number;
  title: string;
  summary: string;
  start_time: number | null;
  end_time: number | null;
  start_page: number | null;
  end_page: number | null;
}

export interface Concept {
  id: string;
  name: string;
  definition: string;
  relevance: number;
  first_mention_time: number | null;
  page: number | null;
}

export interface Faq {
  id: string;
  question: string;
  answer: string;
  order: number;
}

export interface Citation {
  id?: string;
  chunk_id?: string;
  chunk?: string;
  material_id?: string;
  material?: string;
  label: string;
  start_time: number | null;
  page: number | null;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: 'USER' | 'ASSISTANT' | 'SYSTEM' | 'TOOL';
  content: string;
  grounded: boolean;
  citations: Citation[];
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  model: string;
  feedback: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  training: string;
  title: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export interface QuestionOption {
  id: string;
  text: string;
  is_correct?: boolean;
  order: number;
  feedback?: string;
}

export interface Question {
  id: string;
  exam?: string;
  type: QuestionType;
  statement: string;
  level: TrainingLevel;
  points: string;
  order: number;
  explanation?: string;
  correct_text?: string;
  options: QuestionOption[];
  source_material?: string | null;
  source_material_title?: string;
  source_start_time?: number | null;
  source_page?: number | null;
  generated_by_ai?: boolean;
}

export interface Exam {
  id: string;
  training: string;
  training_title: string;
  title: string;
  description: string;
  status: ExamStatus;
  passing_score: number;
  max_attempts: number;
  time_limit_minutes: number;
  min_progress_required: number;
  score_policy: 'BEST' | 'LAST' | 'AVERAGE';
  shuffle_questions: boolean;
  generated_by_ai: boolean;
  generation_model: string;
  question_count: number;
  total_points: string;
  can_edit_questions: boolean;
  published_at: string | null;
  created_at: string;
}

export interface ExamDetail extends Exam {
  questions: Question[];
}

export interface Attempt {
  id: string;
  exam: string;
  exam_title: string;
  training_id: string;
  number: number;
  status: AttemptStatus;
  score: string | null;
  max_score: string;
  percentage: number;
  passed: boolean;
  ai_feedback: string;
  started_at: string;
  submitted_at: string | null;
  graded_at: string | null;
}

export interface AttemptDetail extends Attempt {
  questions: Question[];
  answers: Array<{
    id: string;
    question: string;
    selected_option_ids: string[];
    text_answer: string;
  }>;
  time_limit_minutes: number;
}

export interface AttemptResultItem {
  question_id: string;
  statement: string;
  type: QuestionType;
  points: number;
  points_awarded: number;
  is_correct: boolean;
  your_answer: { selected_option_ids: string[]; text: string };
  correct_options: Array<{ id: string; text: string }>;
  correct_text: string;
  explanation: string;
  feedback: string;
  review_hint: string;
  source: { material_id: string | null; start_time: number | null; page: number | null };
}

export interface AttemptResult extends Attempt {
  results: AttemptResultItem[];
}

export interface CourseSearchResult {
  material_id: string;
  material_title: string;
  material_type: MaterialType;
  lesson_id: string;
  excerpt: string;
  start_time: number | null;
  page: number | null;
  rank: number;
}

export interface AnalyticsOverview {
  users: {
    total: number;
    active: number;
    by_role: Array<{ role: Role; count: number }>;
    recently_active: number;
  };
  content: {
    projects: number;
    trainings: number;
    published_trainings: number;
    materials: number;
    materials_by_status: Array<{ status: MaterialStatus; count: number }>;
    chunks: number;
  };
  learning: {
    enrollments: number;
    completed: number;
    in_progress: number;
    average_progress: number;
  };
  assessment: { exams: number; attempts: number; graded: number; pass_rate: number };
  ai: {
    calls: number;
    total_tokens: number;
    cost_usd: number;
    chat_answers: number;
    no_context_rate: number;
  };
}

export interface MyStats {
  trainings: {
    assigned: number;
    completed: number;
    in_progress: number;
    average_progress: number;
  };
  exams: { taken: number; passed: number; average_score: number };
  ai: { questions_asked: number };
}

/** Serie de actividad del estudiante (vista «Progreso»). */
export interface MyActivity {
  range: { start: string; end: string; days: number };
  daily: Array<{ date: string; seconds: number; lessons: number }>;
  totals: { seconds: number; lessons: number; trainings: number };
  trainings: Array<{
    training_id: string;
    title: string;
    project_name: string;
    status: EnrollmentStatus;
    progress: number;
    seconds: number;
    lessons_viewed: number;
    lessons_completed: number;
    last_viewed_at: string | null;
  }>;
}

export interface AIHealth {
  provider: string;
  llm_model: string;
  whisper_model: string;
  embedding_provider: string;
  embedding_model: string;
  available: boolean;
  /** Los embeddings se calculan en el worker, no en un servicio externo. */
  embeddings_local: boolean;
}

/** Mensajes del WebSocket (docs/10-api-rest.md §11). */
export type WsMessage =
  | { type: 'ready'; session_id: string }
  | { type: 'thinking' }
  | { type: 'token'; content: string }
  | {
      type: 'answer.done';
      session_id: string;
      message_id: string;
      content: string;
      grounded: boolean;
      citations: Citation[];
    }
  | {
      type: 'status.changed';
      material_id: string;
      status: MaterialStatus;
      step: string;
      progress: number;
      error_code: string | null;
    }
  | { type: 'notification'; event: string; [key: string]: unknown }
  | { type: 'error'; code?: string; message: string }
  | { type: 'pong'; [key: string]: unknown };
