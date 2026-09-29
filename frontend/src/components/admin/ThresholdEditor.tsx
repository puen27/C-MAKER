// 임계치 편집 표 (NAME-F01) — docs/8-wireframe.md §6, docs/9-style-guide.md §5.2·§5.9, UC-15
// 값 저장 시 즉시 검증(VAL-05)하고, 저장된 값은 다음 배치부터 적용된다.
// 서버도 같은 규칙으로 다시 검증한다 — 여기서의 검증은 입력 편의용이다.

import { Fragment, useState } from 'react';
import { Button } from '../common/Button';
import { StatusBadge } from '../common/StatusBadge';
import { ThresholdHistoryPanel } from './ThresholdHistoryPanel';
import { toUserMessage } from '../../api/client';
import { useUpdateThreshold } from '../../queries/useThresholds';
import type { Threshold } from '../../types/threshold';
import { formatDateTime } from '../../utils/date';
import './ThresholdEditor.css';

function validate(threshold: Threshold, raw: string): string | null {
  if (raw.trim() === '') return '값을 입력해주세요.';
  const value = Number(raw);
  if (!Number.isFinite(value)) return '숫자를 입력해주세요.';
  if (value < 0) return '0 이상이어야 합니다.';
  if (threshold.integerOnly && !Number.isInteger(value)) return '정수만 입력할 수 있습니다.';
  if (threshold.minValue !== null && value < threshold.minValue) return `최소 ${threshold.minValue}${threshold.unit}`;
  if (threshold.maxValue !== null && value > threshold.maxValue) return `최대 ${threshold.maxValue}${threshold.unit}`;
  return null;
}

interface ThresholdRowProps {
  threshold: Threshold;
}

function ThresholdRow({ threshold }: ThresholdRowProps) {
  const [draft, setDraft] = useState(String(threshold.thresholdValue));
  const [clientError, setClientError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const mutation = useUpdateThreshold();
  const inputId = `threshold-${threshold.id}`;
  const errorId = `${inputId}-error`;
  const changed = draft.trim() !== String(threshold.thresholdValue);
  const error = clientError ?? (mutation.isError ? toUserMessage(mutation.error) : null);

  function handleSave() {
    const message = validate(threshold, draft);
    setClientError(message);
    setSaved(false);
    if (message) return;
    mutation.mutate(
      { id: threshold.id, thresholdValue: Number(draft), unit: threshold.unit },
      {
        onSuccess: (updated) => {
          setDraft(String(updated.thresholdValue));
          setSaved(true);
        },
      },
    );
  }

  return (
    <Fragment>
      <tr>
        <td>
          <div className="threshold-editor__label">{threshold.label}</div>
          <div className="threshold-editor__description">{threshold.description}</div>
        </td>
        <td>
          {threshold.isFixed ? (
            <StatusBadge tone="dashed">발효 즉시 (고정)</StatusBadge>
          ) : (
            <div className="threshold-editor__value">
              <label htmlFor={inputId} className="threshold-editor__sr-only">
                {threshold.label} 임계치
              </label>
              <input
                id={inputId}
                className={`input threshold-editor__input ${error ? 'error' : ''}`}
                type="number"
                inputMode="decimal"
                min={threshold.minValue ?? 0}
                max={threshold.maxValue ?? undefined}
                step={threshold.integerOnly ? 1 : 0.1}
                value={draft}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setClientError(null);
                  setSaved(false);
                  mutation.reset();
                }}
              />
              <span className="threshold-editor__unit">{threshold.unit}</span>
              <Button
                variant="primary-square"
                disabled={!changed || mutation.isPending}
                onClick={handleSave}
              >
                {mutation.isPending ? '저장 중…' : '저장'}
              </Button>
            </div>
          )}
          {error && (
            <p id={errorId} className="threshold-editor__error" role="alert">
              {error}
            </p>
          )}
          {saved && <p className="threshold-editor__saved">저장되었습니다. 다음 배치부터 적용됩니다.</p>}
        </td>
        <td className="threshold-editor__meta">
          <div>{formatDateTime(threshold.updatedAt)}</div>
          <div>{threshold.updatedByName ?? '초기값'}</div>
        </td>
        <td>
          <button
            type="button"
            className="threshold-editor__history-toggle"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((prev) => !prev)}
          >
            변경 이력 {historyOpen ? '▴' : '▾'}
          </button>
        </td>
      </tr>
      {historyOpen && (
        <tr className="threshold-editor__history-row">
          <td colSpan={4}>
            <ThresholdHistoryPanel threshold={threshold} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

interface ThresholdEditorProps {
  title: string;
  thresholds: Threshold[];
}

export function ThresholdEditor({ title, thresholds }: ThresholdEditorProps) {
  return (
    <section className="threshold-editor">
      <h2 className="threshold-editor__title">
        {title}
        <span className="threshold-editor__count">{thresholds.length}개</span>
      </h2>
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="threshold-editor__col-item">
              항목
            </th>
            <th scope="col" className="threshold-editor__col-value">
              현재 임계치
            </th>
            <th scope="col">최근 수정</th>
            <th scope="col">
              <span className="threshold-editor__sr-only">이력</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {thresholds.map((threshold) => (
            // 서버 값이 바뀌면(다른 관리자 저장 등) 입력 초안을 새 값으로 초기화한다.
            <ThresholdRow key={`${threshold.id}-${threshold.updatedAt}`} threshold={threshold} />
          ))}
        </tbody>
      </table>
    </section>
  );
}
