// TanStack Query 훅 — 추천 항목 태깅과 되돌리기 (서버 상태 변경, UC-09)
// 저장 성공 시 추천 목록/요약/브리프 쿼리를 invalidate해 화면을 갱신한다(PRIN-07 단일 진실 공급원).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { revertTag, updateTag } from '../api/tag.api';
import type { RejectedReason, TagStatus } from '../types/recommendation';
import { briefQueryKey } from './useBrief';

export interface TagChange {
  recommendationId: number;
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason | null;
}

/** UNTAGGED로의 변경은 되돌리기(DELETE), 그 외는 저장(POST)으로 보낸다. */
function applyTagChange(change: TagChange) {
  if (change.tagStatus === 'UNTAGGED') {
    return revertTag(change.recommendationId);
  }
  return updateTag({
    recommendationId: change.recommendationId,
    tagStatus: change.tagStatus,
    rejectedReason: change.tagStatus === 'REJECTED' ? (change.rejectedReason ?? undefined) : undefined,
  });
}

export function useTagMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: applyTagChange,
    onSuccess: (result) => {
      // 추천 목록은 branchId/date별로 키가 나뉘므로 도메인 키 전체를 무효화한다.
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
      queryClient.invalidateQueries({ queryKey: ['recommendationSummary'] });
      queryClient.invalidateQueries({ queryKey: briefQueryKey(result.recommendationId) });
    },
  });
}
