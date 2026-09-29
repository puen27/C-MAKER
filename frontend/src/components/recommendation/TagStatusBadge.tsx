// 태깅 상태 배지 (NAME-F01) — docs/9-style-guide.md §2.3 상태 색상 매핑
// 태깅 권한이 없는 역할(지점장)에게 현재 태깅 결과를 읽기 전용으로 보여준다.

import { StatusBadge, type BadgeTone } from '../common/StatusBadge';
import {
  REJECTED_REASON_LABEL,
  TAG_STATUS_LABEL,
  type RejectedReason,
  type TagStatus,
} from '../../types/recommendation';

const TONE: Record<TagStatus, BadgeTone> = {
  UNTAGGED: 'dashed',
  VISITED: 'visited',
  HOLD: 'hold',
  REJECTED: 'rejected',
};

interface TagStatusBadgeProps {
  status: TagStatus;
  reason?: RejectedReason | null;
}

export function TagStatusBadge({ status, reason }: TagStatusBadgeProps) {
  const label = status === 'REJECTED' && reason ? `부적합 · ${REJECTED_REASON_LABEL[reason]}` : TAG_STATUS_LABEL[status];
  return <StatusBadge tone={TONE[status]}>{label}</StatusBadge>;
}
