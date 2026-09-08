// TanStack Query 훅 — 오늘의 접촉 TOP 20 (서버 상태, UC-06)
// 쿼리 키는 NAME-F05 규칙(도메인 단위 배열)을 따른다.

import { useQuery } from '@tanstack/react-query';
import { fetchRecommendations } from '../api/recommendation.api';

export function recommendationsQueryKey(branchId: string, date: string) {
  return ['recommendations', branchId, date] as const;
}

export function useRecommendations(branchId: string, date: string) {
  return useQuery({
    queryKey: recommendationsQueryKey(branchId, date),
    queryFn: () => fetchRecommendations(branchId, date),
    enabled: Boolean(branchId && date),
  });
}
