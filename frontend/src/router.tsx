// 라우터 정의 (docs/4-project-principle.md §6) — 역할별 접근 제한(docs/8-wireframe.md 각 화면 접근 권한)
// 화면 가드는 UX용이며, 최종 권한 검증은 API 서버가 한다(OPS-03).

import type { ReactNode } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import type { UserRole } from './types/auth';
import { homePathFor } from './utils/roles';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { BriefDetailPage } from './pages/BriefDetailPage';
import { AdminThresholdPage } from './pages/AdminThresholdPage';
import { PendingPage } from './pages/PendingPage';

function RequireRole({ roles, children }: { roles?: UserRole[]; children: ReactNode }) {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  if (!token || !user) {
    return <Navigate to="/login" replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={homePathFor(user.role)} replace />;
  }
  return <>{children}</>;
}

function HomeRedirect() {
  const user = useAuthStore((state) => state.user);
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />;
}

const BRANCH_ROLES: UserRole[] = ['RM', 'BRANCH_MANAGER'];

const router = createBrowserRouter([
  { path: '/', element: <HomeRedirect /> },
  { path: '/login', element: <LoginPage /> },
  {
    path: '/dashboard',
    element: (
      <RequireRole roles={BRANCH_ROLES}>
        <DashboardPage />
      </RequireRole>
    ),
  },
  {
    path: '/brief/:id',
    element: (
      <RequireRole roles={BRANCH_ROLES}>
        <BriefDetailPage />
      </RequireRole>
    ),
  },
  {
    path: '/admin/thresholds',
    element: (
      <RequireRole roles={['HQ_MARKETING']}>
        <AdminThresholdPage />
      </RequireRole>
    ),
  },
  {
    path: '/pending',
    element: (
      <RequireRole roles={['HQ_COMPLIANCE']}>
        <PendingPage />
      </RequireRole>
    ),
  },
  { path: '*', element: <HomeRedirect /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
