// 임계치(THRESHOLD_CONFIG) API 클라이언트 (UC-15)

import type { Threshold, ThresholdHistoryItem } from '../types/threshold';
import { apiFetch } from './client';

export function fetchThresholds(): Promise<Threshold[]> {
  return apiFetch<Threshold[]>('/thresholds');
}

export interface UpdateThresholdRequest {
  id: number;
  thresholdValue: number;
  unit: string;
}

export function updateThreshold(request: UpdateThresholdRequest): Promise<Threshold> {
  return apiFetch<Threshold>(`/thresholds/${request.id}`, {
    method: 'PUT',
    body: { thresholdValue: request.thresholdValue, unit: request.unit },
  });
}

export function fetchThresholdHistory(id: number): Promise<ThresholdHistoryItem[]> {
  return apiFetch<ThresholdHistoryItem[]>(`/thresholds/${id}/history`);
}
