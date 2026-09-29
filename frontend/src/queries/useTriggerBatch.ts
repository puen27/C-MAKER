// TanStack Query 훅 — 배치 수동 재실행 요청 (UC-18)
// 요청이 받아들여지면(또는 이미 실행 중이면) 상태 쿼리를 갱신해 폴링을 시작한다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { triggerBatch } from '../api/batch.api';
import { batchStatusQueryKey } from './useBatchRunStatus';

export function useTriggerBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerBatch,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: batchStatusQueryKey });
    },
  });
}
