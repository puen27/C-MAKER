// 수동 재연동 버튼 (NAME-F01) — docs/8-wireframe.md §1, UC-18, REQ-17
// 지점장·본부(마케팅)에게만 렌더링된다(부모에서 canTriggerBatch로 판단 — RM·본부(준법)은 DOM에 없음).
// - 클릭 → 확인 다이얼로그 → 요청. 이미 실행 중이면 "재연동 중…" 비활성 + 예상 완료 시각
// - 쿨다운(VAL-12) 중이면 비활성 + "N분 후 다시 시도할 수 있습니다"
// - 완료 시 useBatchRunStatus가 추천/브리프 쿼리를 무효화해 대시보드를 갱신한다

import { useEffect, useState } from 'react';
import { Button } from './Button';
import { ConfirmDialog } from './ConfirmDialog';
import { toUserMessage } from '../../api/client';
import { useBatchRunStatus } from '../../queries/useBatchRunStatus';
import { useTriggerBatch } from '../../queries/useTriggerBatch';
import type { BatchRunStatus } from '../../types/batchRun';
import { formatDateTime } from '../../utils/date';

interface ManualBatchTriggerProps {
  onFinished?: (status: Exclude<BatchRunStatus, 'RUNNING'>, failureReason: string | null) => void;
}

export function ManualBatchTrigger({ onFinished }: ManualBatchTriggerProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const statusQuery = useBatchRunStatus(true, onFinished);
  const triggerMutation = useTriggerBatch();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const status = statusQuery.data;
  const latestRun = status?.latestRun ?? null;
  const isRunning = latestRun?.status === 'RUNNING' || triggerMutation.isPending;
  const elapsedSinceFetch = statusQuery.dataUpdatedAt ? (now - statusQuery.dataUpdatedAt) / 1000 : 0;
  const cooldownSeconds = Math.max(0, (status?.cooldownRemainingSeconds ?? 0) - elapsedSinceFetch);
  const cooldownMinutes = Math.ceil(cooldownSeconds / 60);
  const disabled = isRunning || cooldownSeconds > 0 || statusQuery.isLoading;

  function handleConfirm() {
    setConfirmOpen(false);
    setNotice(null);
    triggerMutation.mutate(undefined, {
      onSuccess: (result) => {
        if (result.alreadyRunning) {
          setNotice('이미 실행 중인 배치가 있어 새로 실행하지 않았습니다.');
        }
      },
      onError: (error) => setNotice(toUserMessage(error)),
    });
  }

  let hint: string | null = notice;
  if (!hint && latestRun?.status === 'RUNNING' && latestRun.expectedCompletionAt) {
    hint = `예상 완료 ${formatDateTime(latestRun.expectedCompletionAt)}`;
  } else if (!hint && cooldownSeconds > 0) {
    hint = `${cooldownMinutes}분 후 다시 시도할 수 있습니다`;
  }

  return (
    <>
      {hint && <span className="banner__hint">{hint}</span>}
      <Button
        variant="outline-pill"
        disabled={disabled}
        onClick={() => setConfirmOpen(true)}
        title={cooldownSeconds > 0 ? `${cooldownMinutes}분 후 다시 시도할 수 있습니다` : undefined}
      >
        {isRunning ? '재연동 중…' : '수동 재연동'}
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        title="수동 재연동"
        message="일간 배치를 지금 다시 실행할까요? 완료까지 수 분이 걸릴 수 있습니다."
        confirmLabel="실행"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
