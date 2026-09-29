// 태깅 버튼 3종 (NAME-F01) — docs/8-wireframe.md §3·§4, VAL-06
// DashboardPage 카드와 BriefDetailPage에서 동일하게 재사용한다(스타일가이드 §5.1).
// 클릭 1회로 저장(부적합은 사유 선택 1회 추가). 같은 상태를 다시 누르면 아무 일도 하지 않는다.

import { useEffect, useRef, useState } from 'react';
import { Button } from '../common/Button';
import { REJECTED_REASON_LABEL, type RejectedReason, type TagStatus } from '../../types/recommendation';
import './TagButtons.css';

const REJECTED_REASONS: RejectedReason[] = ['ALREADY_CUSTOMER', 'NOT_TARGET', 'INFO_ERROR', 'UNREACHABLE'];

interface TagButtonsProps {
  currentStatus: TagStatus;
  currentReason?: RejectedReason | null;
  disabled?: boolean;
  onTag: (status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function TagButtons({ currentStatus, currentReason, disabled, onTag }: TagButtonsProps) {
  const [showRejectedMenu, setShowRejectedMenu] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showRejectedMenu) return;
    function handlePointer(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setShowRejectedMenu(false);
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setShowRejectedMenu(false);
    }
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [showRejectedMenu]);

  function tag(status: TagStatus, reason?: RejectedReason) {
    if (status === currentStatus && (status !== 'REJECTED' || reason === currentReason)) return;
    onTag(status, reason);
  }

  // 선택된 상태는 색 채움 + ✓로 표시한다(색만으로 구분하지 않음, 9-style-guide.md §1)
  const check = (status: TagStatus) =>
    currentStatus === status ? (
      <span className="btn__check" aria-hidden="true">
        ✓
      </span>
    ) : null;

  return (
    <div className="tag-buttons" role="group" aria-label="접촉 결과 태깅">
      <Button
        variant="tag-visited"
        className={currentStatus === 'VISITED' ? 'is-active' : ''}
        aria-pressed={currentStatus === 'VISITED'}
        disabled={disabled}
        onClick={() => tag('VISITED')}
      >
        {check('VISITED')}
        방문함
      </Button>
      <Button
        variant="tag-hold"
        className={currentStatus === 'HOLD' ? 'is-active' : ''}
        aria-pressed={currentStatus === 'HOLD'}
        disabled={disabled}
        onClick={() => tag('HOLD')}
      >
        {check('HOLD')}
        보류
      </Button>
      <div className="tag-buttons__rejected-wrap" ref={wrapRef}>
        <Button
          variant="tag-rejected"
          className={currentStatus === 'REJECTED' ? 'is-active' : ''}
          aria-pressed={currentStatus === 'REJECTED'}
          aria-haspopup="menu"
          aria-expanded={showRejectedMenu}
          disabled={disabled}
          onClick={() => setShowRejectedMenu((prev) => !prev)}
        >
          {check('REJECTED')}
          {currentStatus === 'REJECTED' && currentReason
            ? `부적합 · ${REJECTED_REASON_LABEL[currentReason]}`
            : '부적합'}
          <span className="btn__caret" aria-hidden="true">
            ▾
          </span>
        </Button>
        {showRejectedMenu && (
          <div className="tag-buttons__dropdown" role="menu" aria-label="부적합 사유">
            <p className="tag-buttons__dropdown-title" aria-hidden="true">
              부적합 사유
            </p>
            {REJECTED_REASONS.map((reason) => (
              <button
                key={reason}
                type="button"
                role="menuitem"
                className={`tag-buttons__dropdown-item ${
                  currentStatus === 'REJECTED' && currentReason === reason ? 'is-current' : ''
                }`}
                onClick={() => {
                  setShowRejectedMenu(false);
                  tag('REJECTED', reason);
                }}
              >
                {REJECTED_REASON_LABEL[reason]}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
