// 배너 (NAME-F01) — docs/9-style-guide.md §5.10 (데이터 지연 · 미태깅 상기)
// 우측 액션 슬롯(.banner__action)에는 outline pill 버튼을 둔다.

import type { ReactNode } from 'react';
import './Banner.css';

interface BannerProps {
  children: ReactNode;
  action?: ReactNode;
  tone?: 'warning' | 'info';
}

export function Banner({ children, action, tone = 'warning' }: BannerProps) {
  return (
    <div className={`banner banner--${tone}`} role={tone === 'warning' ? 'alert' : 'status'}>
      <div className="banner__text">{children}</div>
      {action && <div className="banner__action">{action}</div>}
    </div>
  );
}
