// 태깅(TAG_FEEDBACK) API 클라이언트 (docs/4-project-principle.md §6, UC-09, VAL-06)
//
// ⚠ 실제 API 연동 지점: 백엔드 준비 후 mock 호출을
// apiFetch<Recommendation>(`/recommendations/${recommendationId}/tag`, { method: 'POST', body: request })
// 로 교체한다.

import type { Recommendation, RejectedReason, TagStatus } from '../types/recommendation';
import { mockUpdateTag } from './mockData';

export interface UpdateTagRequest {
  recommendationId: string;
  tagStatus: TagStatus;
  /** tagStatus가 REJECTED일 때만 필수 (VAL-06) */
  rejectedReason?: RejectedReason;
}

const MOCK_LATENCY_MS = 150;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export async function updateTag(request: UpdateTagRequest): Promise<Recommendation> {
  // TODO(실제 API 연동): return apiFetch<Recommendation>(`/recommendations/${request.recommendationId}/tag`, { method: 'POST', body: request });
  const updated = mockUpdateTag(request.recommendationId, request.tagStatus, request.rejectedReason);
  return delay(updated);
}
