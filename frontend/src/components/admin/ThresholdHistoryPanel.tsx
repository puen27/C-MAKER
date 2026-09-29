// 임계치 변경 이력 (NAME-F01) — UC-15 "변경 이력(수정 계정·일시·이전값)이 보존된다", REQ-15

import { toUserMessage } from '../../api/client';
import { useThresholdHistory } from '../../queries/useThresholds';
import type { Threshold } from '../../types/threshold';
import { formatDateTime } from '../../utils/date';

interface ThresholdHistoryPanelProps {
  threshold: Threshold;
}

export function ThresholdHistoryPanel({ threshold }: ThresholdHistoryPanelProps) {
  const { data = [], isLoading, isError, error } = useThresholdHistory(threshold.id, true);

  if (isLoading) return <p className="threshold-editor__description">불러오는 중…</p>;
  if (isError) return <p className="threshold-editor__error">{toUserMessage(error)}</p>;
  if (data.length === 0) return <p className="threshold-editor__description">변경 이력이 없습니다(초기값).</p>;

  return (
    <ul className="threshold-history">
      {data.map((item) => (
        <li key={item.id}>
          <span className="threshold-history__when">{formatDateTime(item.changedAt)}</span>
          <span>{item.changedByName ?? '알 수 없음'}</span>
          <span className="threshold-history__change">
            {item.beforeValue ? `${item.beforeValue.threshold_value}${item.beforeValue.unit}` : '-'} →{' '}
            {item.afterValue ? `${item.afterValue.threshold_value}${item.afterValue.unit}` : '-'}
          </span>
        </li>
      ))}
    </ul>
  );
}
