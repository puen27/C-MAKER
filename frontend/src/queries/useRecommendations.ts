// TanStack Query 훅 — 오늘의 접촉 TOP 20과 상단 요약 (서버 상태, UC-06)
// 쿼리 키는 NAME-F05 규칙(도메인 단위 배열)을 따른다.

import { useQuery } from '@tanstack/react-query';
import { fetchRecommendations, fetchRecommendationSummary } from '../api/recommendation.api';

export function recommendationsQueryKey(branchId: number | null, date: string) {
  return ['recommendations', branchId, date] as const;
}

export function recommendationSummaryQueryKey(branchId: number | null, date: string) {
  return ['recommendationSummary', branchId, date] as const;
}

export function useRecommendations(branchId: number | null, date: string) {
  return useQuery({
    queryKey: recommendationsQueryKey(branchId, date),
    queryFn: () => fetchRecommendations(date),
    enabled: branchId !== null && Boolean(date),
  });
}

export function useRecommendationSummary(branchId: number | null, date: string) {
  return useQuery({
    queryKey: recommendationSummaryQueryKey(branchId, date),
    queryFn: () => fetchRecommendationSummary(date),
    enabled: branchId !== null && Boolean(date),
  });
}
