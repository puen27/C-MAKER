// Zustand 스토어 — 클라이언트 전용 필터 상태 (NAME-F03)
// 대시보드 상단 상태 필터 탭(전체/미태깅/방문함/보류/부적합)의 "현재 선택"만 보관한다.
// 실제 추천 목록 데이터는 TanStack Query 캐시가 단일 진실 공급원이다(PRIN-07).

import { create } from 'zustand';
import type { TagStatus } from '../types/recommendation';

export type DashboardFilter = 'ALL' | TagStatus;

interface FilterState {
  dashboardFilter: DashboardFilter;
  setDashboardFilter: (filter: DashboardFilter) => void;
}

export const useFilterStore = create<FilterState>((set) => ({
  dashboardFilter: 'ALL',
  setDashboardFilter: (filter) => set({ dashboardFilter: filter }),
}));
