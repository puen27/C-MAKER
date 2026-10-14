// Zustand 스토어 — 클라이언트 전용 필터 상태 (NAME-F03)
// 대시보드 기록 상태 탭(전체/기록 전/방문함/보류/부적합)과 신호별 대상 필터의 "현재 선택"만 보관한다.
// 실제 추천 목록 데이터는 TanStack Query 캐시가 단일 진실 공급원이다(PRIN-07).

import { create } from 'zustand';
import type { TagStatus } from '../types/recommendation';

export type DashboardFilter = 'ALL' | TagStatus;

interface FilterState {
  dashboardFilter: DashboardFilter;
  setDashboardFilter: (filter: DashboardFilter) => void;
  /** 신호별 대상 패널에서 고른 신호 키(signalType, utils/signal.ts). null이면 전체 */
  signalFilter: string | null;
  setSignalFilter: (signal: string | null) => void;
}

export const useFilterStore = create<FilterState>((set) => ({
  dashboardFilter: 'ALL',
  setDashboardFilter: (filter) => set({ dashboardFilter: filter }),
  signalFilter: null,
  setSignalFilter: (signal) => set({ signalFilter: signal }),
}));
