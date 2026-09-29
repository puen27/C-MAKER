// 역할별 화면 권한 (docs/8-wireframe.md §1 역할별 노출 메뉴, VAL-08)
// 서버가 최종 권한을 검증한다. 여기서는 권한 없는 메뉴·버튼을 DOM에 렌더링하지 않기 위한 판단만 한다
// (9-style-guide.md §5.6: 숨김이 아니라 미렌더링).

import type { UserRole } from '../types/auth';

export interface NavItem {
  path: string;
  label: string;
  /** 이 메뉴가 활성으로 보일 경로 접두어 */
  activePrefixes: string[];
}

const DASHBOARD: NavItem = { path: '/dashboard', label: '오늘의 접촉', activePrefixes: ['/dashboard', '/brief'] };
const THRESHOLDS: NavItem = { path: '/admin/thresholds', label: '임계치 관리', activePrefixes: ['/admin/thresholds'] };

/**
 * MVP에서 구현된 메뉴만 노출한다. 운영 브리핑(UC-11)·채택률 대시보드(UC-16)는 Phase 2,
 * 캠페인(UC-12~14)은 Phase 3 범위라 화면이 아직 없다(CLAUDE.md §9).
 */
export function navItemsFor(role: UserRole): NavItem[] {
  switch (role) {
    case 'RM':
    case 'BRANCH_MANAGER':
      return [DASHBOARD];
    case 'HQ_MARKETING':
      return [THRESHOLDS];
    case 'HQ_COMPLIANCE':
      return [];
  }
}

export function homePathFor(role: UserRole): string {
  switch (role) {
    case 'RM':
    case 'BRANCH_MANAGER':
      return '/dashboard';
    case 'HQ_MARKETING':
      return '/admin/thresholds';
    case 'HQ_COMPLIANCE':
      return '/pending';
  }
}

/** UC-09 태깅·UC-08 CRM 파일 다운로드는 RM 역할 (docs/10-implementation-guide.md §6.1) */
export function canTag(role: UserRole): boolean {
  return role === 'RM';
}

export function canExportCrm(role: UserRole): boolean {
  return role === 'RM';
}

/** RULE-SENSE-06: 수동 재연동은 지점장·본부(마케팅)만 */
export function canTriggerBatch(role: UserRole): boolean {
  return role === 'BRANCH_MANAGER' || role === 'HQ_MARKETING';
}
