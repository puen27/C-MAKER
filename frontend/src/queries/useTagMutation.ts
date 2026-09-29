// TanStack Query 훅 — 추천 항목 태깅 (서버 상태 변경, UC-09)
// 저장 성공 시 추천 목록/브리프 쿼리를 invalidate해 화면을 갱신한다(PRIN-07 단일 진실 공급원).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { updateTag, type UpdateTagRequest } from '../api/tag.api';
import { briefQueryKey } from './useBrief';

export function useTagMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UpdateTagRequest) => updateTag(request),
    onSuccess: (updated) => {
      // 추천 목록은 branchId/date별로 키가 나뉘므로 'recommendations' 전체를 무효화한다.
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
      queryClient.invalidateQueries({ queryKey: briefQueryKey(updated.id) });
    },
  });
}
