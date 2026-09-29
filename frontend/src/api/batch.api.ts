// 배치 수동 재실행 요청/상태 조회 (REQ-17, UC-18) 및 데이터 신선도(RULE-SENSE-04)

import type { BatchStatus, BatchTriggerResult, DataFreshness } from '../types/batchRun';
import { apiFetch } from './client';

export function triggerBatch(): Promise<BatchTriggerResult> {
  return apiFetch<BatchTriggerResult>('/batch/trigger', { method: 'POST' });
}

export function fetchBatchStatus(): Promise<BatchStatus> {
  return apiFetch<BatchStatus>('/batch/status');
}

export function fetchDataFreshness(): Promise<DataFreshness> {
  return apiFetch<DataFreshness>('/data-freshness');
}
