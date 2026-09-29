// 태깅(TAG_FEEDBACK) API 클라이언트 (UC-09, VAL-06)

import type { RejectedReason, TagResult } from '../types/recommendation';
import { apiFetch } from './client';

export interface UpdateTagRequest {
  recommendationId: number;
  tagStatus: 'VISITED' | 'HOLD' | 'REJECTED';
  /** tagStatus가 REJECTED일 때만 필수 (VAL-06) */
  rejectedReason?: RejectedReason;
}

export function updateTag(request: UpdateTagRequest): Promise<TagResult> {
  return apiFetch<TagResult>(`/recommendations/${request.recommendationId}/tag`, {
    method: 'POST',
    body: { tagStatus: request.tagStatus, rejectedReason: request.rejectedReason ?? null },
  });
}

/** 태깅 되돌리기 — 미태깅 상태로 복귀 */
export function revertTag(recommendationId: number): Promise<TagResult> {
  return apiFetch<TagResult>(`/recommendations/${recommendationId}/tag`, { method: 'DELETE' });
}
