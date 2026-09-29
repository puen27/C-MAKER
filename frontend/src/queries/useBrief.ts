// TanStack Query 훅 — 상담 브리프 상세 (서버 상태, UC-07)

import { useQuery } from '@tanstack/react-query';
import { fetchBrief } from '../api/brief.api';

export function briefQueryKey(recommendationId: number) {
  return ['brief', recommendationId] as const;
}

export function useBrief(recommendationId: number) {
  return useQuery({
    queryKey: briefQueryKey(recommendationId),
    queryFn: () => fetchBrief(recommendationId),
    enabled: Number.isInteger(recommendationId) && recommendationId > 0,
  });
}
