// 추천(RECOMMENDATION) API 클라이언트 (UC-06, UC-08)
// 소속 지점은 서버가 토큰으로 판단한다 — 클라이언트가 지점 ID를 보내지 않는다(OPS-03).

import type { CrmFileFormat, Recommendation, RecommendationSummary } from '../types/recommendation';
import { apiDownload, apiFetch } from './client';

export function fetchRecommendations(date: string): Promise<Recommendation[]> {
  return apiFetch<Recommendation[]>(`/recommendations?date=${encodeURIComponent(date)}`);
}

export function fetchRecommendationSummary(date: string): Promise<RecommendationSummary> {
  return apiFetch<RecommendationSummary>(`/recommendations/summary?date=${encodeURIComponent(date)}`);
}

/** CRM 등록 파일(CSV/XLSX) 다운로드 — REQ-07 */
export function downloadCrmFile(date: string, format: CrmFileFormat): Promise<{ blob: Blob; filename: string }> {
  return apiDownload(`/recommendations/export?date=${encodeURIComponent(date)}&format=${format}`);
}
