// 데이터 지연 배너 (NAME-F01) — docs/8-wireframe.md §1, RULE-SENSE-04, UC-18
// 배너는 모든 역할에게 보이고, 우측 "수동 재연동" 버튼은 지점장·본부(마케팅)에게만 렌더링된다.
// 평상시(지연 없음)에는 배너와 버튼 모두 나타나지 않는다(UC-18 인수 기준).

import { useCallback, useState } from 'react';
import { Banner } from './Banner';
import { ManualBatchTrigger } from './ManualBatchTrigger';
import { useDataFreshness } from '../../queries/useBatchRunStatus';
import { useAuthStore } from '../../stores/authStore';
import type { BatchRunStatus } from '../../types/batchRun';
import { canTriggerBatch } from '../../utils/roles';

export function DataDelayBanner() {
  const user = useAuthStore((state) => state.user);
  const freshnessQuery = useDataFreshness(Boolean(user));
  const [completion, setCompletion] = useState<{ ok: boolean; message: string } | null>(null);

  const handleFinished = useCallback((status: Exclude<BatchRunStatus, 'RUNNING'>, reason: string | null) => {
    setCompletion(
      status === 'SUCCESS'
        ? { ok: true, message: '재연동이 완료되었습니다. 대시보드가 최신 데이터로 갱신되었습니다.' }
        : { ok: false, message: `재연동이 실패했습니다${reason ? `: ${reason}` : '.'}` },
    );
  }, []);

  if (!user) return null;
  const freshness = freshnessQuery.data;
  const showTrigger = canTriggerBatch(user.role);

  return (
    <>
      {completion && (
        <Banner
          tone={completion.ok ? 'info' : 'warning'}
          action={
            <button type="button" className="banner__dismiss" onClick={() => setCompletion(null)}>
              닫기
            </button>
          }
        >
          {completion.message}
        </Banner>
      )}
      {freshness?.delayed && (
        <Banner action={showTrigger ? <ManualBatchTrigger onFinished={handleFinished} /> : undefined}>
          ⚠ {freshness.message}
          {freshness.sources.some((source) => source.delayDays > 0) && (
            <span className="banner__hint">
              {' '}
              (
              {freshness.sources
                .filter((source) => source.delayDays > 0)
                .map((source) => `${source.displayName} ${source.delayDays}일 전`)
                .join(', ')}
              )
            </span>
          )}
        </Banner>
      )}
    </>
  );
}
