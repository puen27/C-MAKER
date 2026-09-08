// 추천(RECOMMENDATION) API 클라이언트 (docs/4-project-principle.md §6, UC-06)
//
// ⚠ 실제 API 연동 지점: 백엔드 준비 후 mock 호출을
// apiFetch<Recommendation[]>(`/recommendations?branchId=${branchId}&date=${date}`) 로 교체한다.

import type { Recommendation } from '../types/recommendation';
import { mockFetchRecommendations } from './mockData';

const MOCK_LATENCY_MS = 200;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export async function fetchRecommendations(
  branchId: string,
  date: string,
): Promise<Recommendation[]> {
  // TODO(실제 API 연동): return apiFetch<Recommendation[]>(`/recommendations?branchId=${branchId}&date=${date}`);
  void branchId;
  void date;
  return delay(mockFetchRecommendations());
}
