// 태깅 + 되돌리기 UI 훅 (UC-09 "저장 직후 되돌리기가 가능")
// 직전 태깅 1건의 이전 값만 화면 상태로 들고 있다가, 되돌리기 시 그 값으로 다시 저장한다.
// (이전 값이 미태깅이면 태깅 삭제). 서버 데이터 자체는 TanStack Query 캐시가 진실 공급원이다.

import { useCallback, useState } from 'react';
import { toUserMessage } from '../api/client';
import type { RejectedReason, TagStatus } from '../types/recommendation';
import { useTagMutation, type TagChange } from './useTagMutation';

export interface TagTarget {
  id: number;
  businessName: string;
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason | null;
}

export interface LastTagChange {
  businessName: string;
  applied: TagStatus;
  previous: TagChange;
}

export function useTagWithUndo() {
  const mutation = useTagMutation();
  const [lastChange, setLastChange] = useState<LastTagChange | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tag = useCallback(
    (target: TagTarget, status: TagStatus, reason?: RejectedReason) => {
      setError(null);
      const previous: TagChange = {
        recommendationId: target.id,
        tagStatus: target.tagStatus,
        rejectedReason: target.rejectedReason ?? null,
      };
      mutation.mutate(
        { recommendationId: target.id, tagStatus: status, rejectedReason: reason ?? null },
        {
          onSuccess: () => setLastChange({ businessName: target.businessName, applied: status, previous }),
          onError: (err) => setError(toUserMessage(err)),
        },
      );
    },
    [mutation],
  );

  const undo = useCallback(() => {
    if (!lastChange) return;
    setError(null);
    mutation.mutate(lastChange.previous, {
      onSuccess: () => setLastChange(null),
      onError: (err) => setError(toUserMessage(err)),
    });
  }, [lastChange, mutation]);

  const dismiss = useCallback(() => {
    setLastChange(null);
    setError(null);
  }, []);

  return { tag, undo, dismiss, lastChange, error, isPending: mutation.isPending };
}
