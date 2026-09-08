// 상태 배지 (NAME-F01) — docs/9-style-guide.md §5.3, §2.3 상태 색상 매핑
import type { ReactNode } from 'react';
import './StatusBadge.css';

export type BadgeTone = 'visited' | 'hold' | 'rejected' | 'info' | 'dashed' | 'outline';

interface StatusBadgeProps {
  tone: BadgeTone;
  children: ReactNode;
}

export function StatusBadge({ tone, children }: StatusBadgeProps) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
