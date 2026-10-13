// 출처 도장 — "출처명 MM.DD" (NH-Campaigner-UI-proposal.html .stamp)
// 데이터 기준 도장, 명부 행, 브리프 근거에서 같은 모양으로 쓴다.

import type { ReactNode } from 'react';
import { parseSourceTag, shortDate } from '../../utils/sourceTag';
import './SourceStamp.css';

interface SourceStampProps {
  /** 직접 지정하지 않으면 tag("소스명·기준일")에서 읽는다 */
  tag?: string;
  source?: string;
  date?: string | null;
  /** 날짜 자리를 대신할 글자(예: '미수집') */
  dateLabel?: string;
  title?: string;
  className?: string;
  children?: ReactNode;
}

export function SourceStamp({ tag, source, date, dateLabel, title, className = '', children }: SourceStampProps) {
  const parsed = tag !== undefined ? parseSourceTag(tag) : null;
  const name = source ?? parsed?.source;
  if (!name) return null;
  const asOf = date !== undefined ? date : (parsed?.date ?? null);

  return (
    <span className={`data-stamp ${className}`} title={title}>
      <svg className="data-stamp__icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M4 2.5h5.3L12 5.2v8.3H4z" />
        <path d="M9.3 2.5v2.7H12" />
        <path d="M6 8.2h4M6 10.6h3" />
      </svg>
      {name}
      {(dateLabel || asOf) && <b className="data-stamp__date">{dateLabel ?? shortDate(asOf)}</b>}
      {children}
    </span>
  );
}
