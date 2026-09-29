// TanStack Query 훅 — 임계치 조회·변경·이력 (서버 상태, UC-15)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchThresholdHistory,
  fetchThresholds,
  updateThreshold,
  type UpdateThresholdRequest,
} from '../api/threshold.api';

export const thresholdsQueryKey = ['thresholds'] as const;

export function thresholdHistoryQueryKey(id: number) {
  return ['thresholds', id, 'history'] as const;
}

export function useThresholds() {
  return useQuery({ queryKey: thresholdsQueryKey, queryFn: fetchThresholds });
}

export function useThresholdHistory(id: number, enabled: boolean) {
  return useQuery({
    queryKey: thresholdHistoryQueryKey(id),
    queryFn: () => fetchThresholdHistory(id),
    enabled,
  });
}

export function useUpdateThreshold() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: UpdateThresholdRequest) => updateThreshold(request),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: thresholdsQueryKey });
      queryClient.invalidateQueries({ queryKey: thresholdHistoryQueryKey(updated.id) });
    },
  });
}
