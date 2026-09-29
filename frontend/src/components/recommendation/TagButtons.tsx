// 태깅 버튼 3종 (NAME-F01) — docs/8-wireframe.md §3·§4, VAL-06
// DashboardPage 카드와 BriefDetailPage에서 동일하게 재사용한다(스타일가이드 §5.1).

import { useState } from 'react';
import { Button } from '../common/Button';
import {
  REJECTED_REASON_LABEL,
  type RejectedReason,
  type TagStatus,
} from '../../types/recommendation';
import './TagButtons.css';

const REJECTED_REASONS: RejectedReason[] = [
  'ALREADY_CUSTOMER',
  'NOT_TARGET',
  'INFO_ERROR',
  'UNREACHABLE',
];

interface TagButtonsProps {
  currentStatus: TagStatus;
  disabled?: boolean;
  onTag: (status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function TagButtons({ currentStatus, disabled, onTag }: TagButtonsProps) {
  const [showRejectedMenu, setShowRejectedMenu] = useState(false);

  return (
    <div className="tag-buttons">
      <Button
        type="button"
        variant="tag-visited"
        className={currentStatus === 'VISITED' ? 'is-active' : ''}
        disabled={disabled}
        onClick={() => onTag('VISITED')}
      >
        방문함
      </Button>
      <Button
        type="button"
        variant="tag-hold"
        className={currentStatus === 'HOLD' ? 'is-active' : ''}
        disabled={disabled}
        onClick={() => onTag('HOLD')}
      >
        보류
      </Button>
      <div className="tag-buttons__rejected-wrap">
        <Button
          type="button"
          variant="tag-rejected"
          className={currentStatus === 'REJECTED' ? 'is-active' : ''}
          disabled={disabled}
          onClick={() => setShowRejectedMenu((prev) => !prev)}
        >
          부적합 ▾
        </Button>
        {showRejectedMenu && (
          <div className="tag-buttons__dropdown">
            {REJECTED_REASONS.map((reason) => (
              <button
                key={reason}
                type="button"
                className="tag-buttons__dropdown-item"
                onClick={() => {
                  setShowRejectedMenu(false);
                  onTag('REJECTED', reason);
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
