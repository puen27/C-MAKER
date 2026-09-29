// 공통 레이아웃 (NAME-F01) — docs/8-wireframe.md §1 공통 레이아웃
// 상단 유틸리티 바 + 좌측 사이드바 + 지점 헤더 + 콘텐츠 영역

import type { ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import './Layout.css';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  function handleLogout() {
    logout();
    navigate('/login', { replace: true });
  }

  const isDashboardActive =
    location.pathname === '/dashboard' || location.pathname.startsWith('/brief');

  return (
    <div className="layout">
      <div className="layout__utility-bar">
        <div className="layout__utility-row">
          <span className="layout__logo">BranchSense</span>
          {user && (
            <div className="layout__user-info">
              <span>{user.name} 님 · 09:47 연장</span>
              <button type="button" onClick={handleLogout}>
                로그아웃
              </button>
            </div>
          )}
        </div>
        <div className="layout__aux-links">고객센터 · 도움말</div>
      </div>

      {user && (
        <div className="layout__branch-header">
          <span>지점명: {user.branchName}</span>
          <span>
            {user.name} · {user.role === 'RM' ? 'RM' : '지점장'} ▾
          </span>
        </div>
      )}

      <div className="layout__body">
        <nav className="layout__sidebar">
          <button
            type="button"
            className={`layout__nav-item ${isDashboardActive ? 'is-active' : ''}`}
            onClick={() => navigate('/dashboard')}
          >
            오늘의 접촉
          </button>
        </nav>
        <main className="layout__content">{children}</main>
      </div>
    </div>
  );
}
