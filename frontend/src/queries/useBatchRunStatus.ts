// TanStack Query 훅 — BATCH_RUN 상태 폴링과 데이터 신선도 (UC-18, RULE-SENSE-04)
// 실행 중(RUNNING)이면 짧은 간격으로 폴링하고, 완료로 바뀌면 추천/브리프/신선도 쿼리를 무효화한다
// (4-project-principle.md §2 프론트엔드 레이어).

import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchBatchStatus, fetchDataFreshness } from '../api/batch.api';
import type { BatchRunStatus } from '../types/batchRun';

export const batchStatusQueryKey = ['batchRun', 'status'] as const;
export const dataFreshnessQueryKey = ['dataFreshness'] as const;

const RUNNING_POLL_MS = 5_000;
const IDLE_POLL_MS = 60_000;

export function useBatchRunStatus(
  enabled: boolean,
  onFinished?: (status: Exclude<BatchRunStatus, 'RUNNING'>, failureReason: string | null) => void,
) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: batchStatusQueryKey,
    queryFn: fetchBatchStatus,
    enabled,
    refetchInterval: (current) =>
      current.state.data?.latestRun?.status === 'RUNNING' ? RUNNING_POLL_MS : IDLE_POLL_MS,
  });

  const latest = query.data?.latestRun ?? null;
  const previous = useRef<{ id: number; status: BatchRunStatus } | null>(null);
  const finishedCallback = useRef(onFinished);

  useEffect(() => {
    finishedCallback.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    if (!latest) return;
    const before = previous.current;
    previous.current = { id: latest.id, status: latest.status };
    if (before && before.id === latest.id && before.status === 'RUNNING' && latest.status !== 'RUNNING') {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
      queryClient.invalidateQueries({ queryKey: ['recommendationSummary'] });
      queryClient.invalidateQueries({ queryKey: ['brief'] });
      queryClient.invalidateQueries({ queryKey: dataFreshnessQueryKey });
      finishedCallback.current?.(latest.status, latest.failureReason);
    }
  }, [latest, queryClient]);

  return query;
}

export function useDataFreshness(enabled: boolean) {
  return useQuery({
    queryKey: dataFreshnessQueryKey,
    queryFn: fetchDataFreshness,
    enabled,
    refetchInterval: IDLE_POLL_MS,
  });
}
