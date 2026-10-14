// 출처 태그("소스명·YYYY-MM-DD", RULE-BRIEF-01) 해석 유틸.
// 신호별 묶음은 출처명이 아니라 대표 신호 종류로 한다(utils/signal.ts).

export interface ParsedSourceTag {
  source: string;
  /** YYYY-MM-DD, 형식이 맞지 않으면 null */
  date: string | null;
}

const TAG_PATTERN = /^(.+)·(\d{4}-\d{2}-\d{2})$/;

export function parseSourceTag(tag: string | null | undefined): ParsedSourceTag | null {
  const trimmed = tag?.trim();
  if (!trimmed) return null;
  const match = TAG_PATTERN.exec(trimmed);
  return match ? { source: match[1].trim(), date: match[2] } : { source: trimmed, date: null };
}

/** YYYY-MM-DD → MM.DD */
export function shortDate(date: string | null | undefined): string {
  if (!date) return '—';
  const [, month, day] = date.split('-');
  return month && day ? `${month}.${day}` : date;
}
