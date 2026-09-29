// 공통 레이아웃 (NAME-F01) — docs/8-wireframe.md §1 공통 레이아웃
// 상단 유틸리티 바 + 좌측 사이드바(역할별 메뉴) + [지점 헤더 + 데이터 지연 배너 + 콘텐츠 영역]

import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { ROLE_LABEL } from '../../types/auth';
import { navItemsFor } from '../../utils/roles';
import { DataDelayBanner } from './DataDelayBanner';
import { StatusBadge } from './StatusBadge';
import { TopUtilityBar } from './TopUtilityBar';
import './Layout.css';

interface LayoutProps {
  children: ReactNode;
}

/** 사이드바 메뉴 아이콘 20px (9-style-guide.md §7) — 아이콘 라이브러리 없이 인라인 SVG로 둔다 */
function NavIcon({ path }: { path: string }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: '0 0 20 20',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
  };
  if (path.startsWith('/admin/thresholds')) {
    // 슬라이더(임계치 조정)
    return (
      <svg {...common}>
        <path d="M3 6h8M15 6h2M3 14h2M9 14h8" />
        <circle cx="13" cy="6" r="2" />
        <circle cx="7" cy="14" r="2" />
      </svg>
    );
  }
  // 체크 목록(오늘의 접촉 명부)
  return (
    <svg {...common}>
      <path d="M3.5 5.5l1.5 1.5 2.5-3M3.5 12.5l1.5 1.5 2.5-3M10.5 5.5h6M10.5 12.5h6" />
    </svg>
  );
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const navItems = user ? navItemsFor(user.role) : [];

  return (
    <div className="layout">
      <TopUtilityBar />

      <div className="layout__body">
        <nav className="layout__sidebar" aria-label="주 메뉴">
          {/* 역할별로 노출되지 않는 메뉴는 DOM에 렌더링하지 않는다(9-style-guide.md §5.6) */}
          {navItems.map((item) => {
            const active = item.activePrefixes.some((prefix) => location.pathname.startsWith(prefix));
            return (
              <NavLink
                key={item.path}
                to={item.path}
                title={item.label}
                className={`layout__nav-item ${active ? 'is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <NavIcon path={item.path} />
                <span className="layout__nav-label">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="layout__main">
          {user && (
            <div className="layout__branch-header">
              <span className="layout__branch">
                {user.branchName ? (
                  <>
                    <span className="layout__branch-label">지점명</span>
                    <span className="layout__branch-name">{user.branchName}</span>
                  </>
                ) : (
                  <span className="layout__branch-name">본부</span>
                )}
              </span>
              <span className="layout__user">
                {user.name}
                <StatusBadge tone="outline">{ROLE_LABEL[user.role]}</StatusBadge>
              </span>
            </div>
          )}
          <main className="layout__content">
            <div className="layout__content-inner">
              <DataDelayBanner />
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
