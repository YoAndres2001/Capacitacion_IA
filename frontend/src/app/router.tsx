/** Rutas de la aplicación con guardas por rol y carga diferida por feature. */

import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Loading } from '@/shared/components';
import { AppLayout } from '@/shared/components/AppLayout';
import { useAuth } from '@/features/auth/AuthContext';
import type { Role } from '@/shared/api/types';

// Auth
const LoginPage = lazy(() => import('@/features/auth/pages/LoginPage'));
const ForgotPasswordPage = lazy(() => import('@/features/auth/pages/ForgotPasswordPage'));
const ResetPasswordPage = lazy(() => import('@/features/auth/pages/ResetPasswordPage'));

// Administración
const AdminDashboard = lazy(() => import('@/features/dashboard/pages/AdminDashboard'));
const ProjectsPage = lazy(() => import('@/features/projects/pages/ProjectsPage'));
const ProjectDetailPage = lazy(() => import('@/features/projects/pages/ProjectDetailPage'));
const TrainingsPage = lazy(() => import('@/features/trainings/pages/TrainingsPage'));
const TrainingBuilderPage = lazy(() => import('@/features/trainings/pages/TrainingBuilderPage'));
const MaterialAnalysisPage = lazy(() => import('@/features/trainings/pages/MaterialAnalysisPage'));
const UsersPage = lazy(() => import('@/features/users/pages/UsersPage'));
const ExamEditorPage = lazy(() => import('@/features/exams/pages/ExamEditorPage'));
const ExamResultsPage = lazy(() => import('@/features/exams/pages/ExamResultsPage'));
const AnalyticsPage = lazy(() => import('@/features/analytics/pages/AnalyticsPage'));

// Estudiante
const StudentDashboard = lazy(() => import('@/features/dashboard/pages/StudentDashboard'));
const CoursePlayerPage = lazy(() => import('@/features/player/pages/CoursePlayerPage'));
const TakeExamPage = lazy(() => import('@/features/exams/pages/TakeExamPage'));
const AttemptResultPage = lazy(() => import('@/features/exams/pages/AttemptResultPage'));
const ProfilePage = lazy(() => import('@/features/auth/pages/ProfilePage'));

function RequireAuth({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const { isAuthenticated, loading, user } = useAuth();
  const location = useLocation();

  if (loading) return <Loading label="Verificando sesión…" />;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (roles && user && !roles.includes(user.role)) return <Navigate to="/" replace />;

  return <>{children}</>;
}

function RedirectHome() {
  const { user } = useAuth();
  // El administrador y el instructor entran a la consola; el estudiante, a sus cursos.
  return <Navigate to={user?.permissions.manage_content ? '/admin' : '/mis-cursos'} replace />;
}

const MANAGERS: Role[] = ['SUPERADMIN', 'ADMIN', 'INSTRUCTOR'];
const ADMINS: Role[] = ['SUPERADMIN', 'ADMIN'];

export function AppRouter() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* Públicas */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        {/* Privadas */}
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<RedirectHome />} />
          <Route path="/perfil" element={<ProfilePage />} />

          {/* Consola de administración */}
          <Route
            path="/admin"
            element={
              <RequireAuth roles={MANAGERS}>
                <AdminDashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/proyectos"
            element={
              <RequireAuth roles={MANAGERS}>
                <ProjectsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/proyectos/:projectId"
            element={
              <RequireAuth roles={MANAGERS}>
                <ProjectDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/capacitaciones"
            element={
              <RequireAuth roles={MANAGERS}>
                <TrainingsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/capacitaciones/:trainingId/editor"
            element={
              <RequireAuth roles={MANAGERS}>
                <TrainingBuilderPage />
              </RequireAuth>
            }
          />
          <Route
            path="/materiales/:materialId"
            element={
              <RequireAuth roles={MANAGERS}>
                <MaterialAnalysisPage />
              </RequireAuth>
            }
          />
          <Route
            path="/examenes/:examId/editor"
            element={
              <RequireAuth roles={MANAGERS}>
                <ExamEditorPage />
              </RequireAuth>
            }
          />
          <Route
            path="/examenes/:examId/resultados"
            element={
              <RequireAuth roles={MANAGERS}>
                <ExamResultsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/usuarios"
            element={
              <RequireAuth roles={ADMINS}>
                <UsersPage />
              </RequireAuth>
            }
          />
          <Route
            path="/analitica"
            element={
              <RequireAuth roles={ADMINS}>
                <AnalyticsPage />
              </RequireAuth>
            }
          />

          {/* Estudiante */}
          <Route path="/mis-cursos" element={<StudentDashboard />} />
          <Route path="/cursos/:trainingId" element={<CoursePlayerPage />} />
          <Route path="/examenes/:examId/rendir" element={<TakeExamPage />} />
          <Route path="/intentos/:attemptId" element={<AttemptResultPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
