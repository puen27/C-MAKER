// 데이터 기준 도장 — NH-Campaigner-UI-proposal.html 변경 포인트 3, PRD F-1, RULE-SENSE-04
// 상단 노란 지연 배너 대신 출처별 기준일을 늘 보여준다.
// '지연' 표시는 소스 장애로 전일 데이터를 쓴(fallback) 출처에만 붙인다. 공표 주기 때문에 기준일이
// 며칠 전인 것(예: 휴일 다음 날 환율)은 지연이 아니다.
// 배치 실패·수집 실패처럼 도장만으로 알 수 없는 상황은 도장 아래 한 줄로 알리고,
// 지점장·본부(마케팅)에게는 그 줄에 수동 재연동 버튼을 둔다(UC-18).

import { useCallback, useState } from 'react';
import { ManualBatchTrigger } from './ManualBatchTrigger';
import { SourceStamp } from './SourceStamp';
import { useDataFreshness } from '../../queries/useBatchRunStatus';
import { useAuthStore } from '../../stores/authStore';
import type { BatchRunStatus, SourceFreshness } from '../../types/batchRun';
import { canTriggerBatch } from '../../utils/roles';
import './DataFreshnessStamps.css';

function isFallback(source: SourceFreshness): boolean {
  return source.isFallback || source.status === 'FALLBACK';
}

function describe(source: SourceFreshness): string {
  if (source.status === 'UNAVAILABLE') return `${source.displayName}: 오늘 수집하지 못했습니다.`;
  const base = `${source.displayName} 기준일 ${source.latestAsOfDate ?? '없음'}`;
  return isFallback(source) ? `${base}. 소스 장애로 이전 데이터를 사용했습니다.` : base;
}

export function DataFreshnessStamps() {
  const user = useAuthStore((state) => state.user);
  const freshnessQuery = useDataFreshness(Boolean(user));
  const [completion, setCompletion] = useState<{ ok: boolean; message: string } | null>(null);

  const handleFinished = useCallback((status: Exclude<BatchRunStatus, 'RUNNING'>, reason: string | null) => {
    setCompletion(
      status === 'SUCCESS'
        ? { ok: true, message: '재연동이 완료되었습니다. 최신 데이터로 갱신되었습니다.' }
        : { ok: false, message: `재연동이 실패했습니다${reason ? `: ${reason}` : '.'}` },
    );
  }, []);

  const freshness = freshnessQuery.data;
  if (!user || !freshness || freshness.sources.length === 0) return null;
  const showTrigger = canTriggerBatch(user.role);

  return (
    <div className="data-stamps">
      <div className="data-stamps__row">
        <span className="data-stamps__label">데이터 기준</span>
        {freshness.sources.map((source) => {
          const fallback = isFallback(source);
          const unavailable = source.status === 'UNAVAILABLE';
          return (
            <SourceStamp
              key={source.sourceName}
              className={`${fallback ? 'is-fallback' : ''} ${unavailable ? 'is-unavailable' : ''}`}
              title={describe(source)}
              source={source.displayName}
              date={source.latestAsOfDate}
              dateLabel={unavailable ? '미수집' : source.latestAsOfDate ? undefined : '—'}
            >
              {fallback && <span className="data-stamp__delay">지연</span>}
              <span className="sr-only">{describe(source)}</span>
            </SourceStamp>
          );
        })}
      </div>
      {freshness.delayed && freshness.message && (
        <div className="data-stamps__notice" role="status">
          <span>{freshness.message}</span>
          {showTrigger && <ManualBatchTrigger onFinished={handleFinished} />}
        </div>
      )}
      {completion && (
        <div className={`data-stamps__notice ${completion.ok ? '' : 'is-error'}`} role="status">
          <span>{completion.message}</span>
          <button type="button" className="data-stamps__dismiss" onClick={() => setCompletion(null)}>
            닫기
          </button>
        </div>
      )}
    </div>
  );
}
