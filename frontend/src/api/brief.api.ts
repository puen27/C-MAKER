// 상담 브리프(BRIEF) API 클라이언트 (docs/4-project-principle.md §6, UC-07)
//
// ⚠ 실제 API 연동 지점: 백엔드 준비 후 mock 호출을
// apiFetch<Brief>(`/recommendations/${recommendationId}/brief`) 로 교체한다.

import type { Brief } from '../types/brief';
import { mockFetchBrief } from './mockData';

const MOCK_LATENCY_MS = 200;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export async function fetchBrief(recommendationId: string): Promise<Brief> {
  // TODO(실제 API 연동): return apiFetch<Brief>(`/recommendations/${recommendationId}/brief`);
  return delay(mockFetchBrief(recommendationId));
}
