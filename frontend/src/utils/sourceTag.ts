// 출처 태그("소스명·YYYY-MM-DD", RULE-BRIEF-01) 해석 유틸.
// API가 신호 코드를 내려주지 않으므로, 신호별 묶음은 출처명으로 대신한다
// (NH-Campaigner-UI-proposal.html '개발 전달용': 코드가 없으면 출처명으로 묶는다).

import type { Recommendation } from '../types/recommendation';

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

/** 출처 태그가 비어 있는(사유 생성 전) 추천을 묶는 키 */
export const UNKNOWN_SOURCE = '출처 확인 중';

export function sourceOf(rec: Recommendation): string {
  return parseSourceTag(rec.reasonSourceTag)?.source ?? UNKNOWN_SOURCE;
}

export interface SourceGroup {
  source: string;
  count: number;
}

/** 순위가 높은 추천의 출처부터 나오도록, 순위순으로 처음 나타난 순서대로 묶는다 */
export function groupBySource(recommendations: Recommendation[]): SourceGroup[] {
  const groups = new Map<string, number>();
  [...recommendations]
    .sort((a, b) => a.rank - b.rank)
    .forEach((rec) => {
      const source = sourceOf(rec);
      groups.set(source, (groups.get(source) ?? 0) + 1);
    });
  return [...groups.entries()].map(([source, count]) => ({ source, count }));
}
