// 상담 브리프(BRIEF) API 클라이언트 (UC-07)

import type { Brief } from '../types/brief';
import { apiFetch } from './client';

export function fetchBrief(recommendationId: number): Promise<Brief> {
  return apiFetch<Brief>(`/recommendations/${recommendationId}/brief`);
}
