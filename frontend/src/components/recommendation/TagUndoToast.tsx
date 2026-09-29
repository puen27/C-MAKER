// 태깅 저장 알림 + 되돌리기 (NAME-F01) — UC-09 인수 기준 "저장 직후 되돌리기가 가능"

import { useEffect } from 'react';
import { TAG_STATUS_LABEL } from '../../types/recommendation';
import type { LastTagChange } from '../../queries/useTagWithUndo';
import './TagUndoToast.css';

const AUTO_DISMISS_MS = 10_000;

interface TagUndoToastProps {
  lastChange: LastTagChange | null;
  error: string | null;
  pending: boolean;
  onUndo: () => void;
  onDismiss: () => void;
}

export function TagUndoToast({ lastChange, error, pending, onUndo, onDismiss }: TagUndoToastProps) {
  useEffect(() => {
    if (!lastChange && !error) return;
    const timer = window.setTimeout(onDismiss, AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [lastChange, error, onDismiss]);

  if (!lastChange && !error) return null;

  return (
    <div className={`tag-toast ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
      {error ? (
        <span>{error}</span>
      ) : (
        lastChange && (
          <>
            <span>
              {lastChange.businessName} · {TAG_STATUS_LABEL[lastChange.applied]} 저장됨
            </span>
            <button type="button" className="tag-toast__action" onClick={onUndo} disabled={pending}>
              되돌리기
            </button>
          </>
        )
      )}
      <button type="button" className="tag-toast__close" onClick={onDismiss} aria-label="알림 닫기">
        ×
      </button>
    </div>
  );
}
