// 대표 신호(signalType) → 화면 신호명, 신호별 묶음 유틸.
// 출처명(지방행정인허가 등)으로 묶으면 같은 출처의 다른 신호(신규 개업·주변 상권 개업)가 섞이므로
// API가 내려주는 대표 신호 종류로 묶는다(NH Campaigner 수정 요청 10/13 ①).

import type { Recommendation } from '../types/recommendation';

export const SIGNAL_LABEL: Record<string, string> = {
  NEW_BUSINESS_OPENING: '신규 개업',
  INDUSTRY_NEW_OPENINGS: '같은 업종 개업',
  AREA_NEW_OPENINGS: '주변 상권 개업',
  FX_DAILY_CHANGE: '환율 변동',
  OIL_PRICE_CHANGE: '유가 변동',
  WEATHER_WARNING: '기상특보',
  TEMP_SHIFT_FORECAST: '기온 급변 예보',
  SEASON_SHIFT_FORECAST: '계절 전환 예보',
  FIRST_FREEZE_FORECAST: '첫 영하 예보',
  FIRST_HEAT_FORECAST: '첫 폭염 예보',
};

/** 기여 신호 없이(근접도·미접촉 기간 등으로만) 선정된 추천을 묶는 키 */
export const NO_SIGNAL_KEY = 'NO_SIGNAL';
const NO_SIGNAL_LABEL = '가까운 거리';
const UNKNOWN_SIGNAL_LABEL = '기타 신호';

export function signalKeyOf(rec: Recommendation): string {
  return rec.signalType || NO_SIGNAL_KEY;
}

export function signalLabel(key: string): string {
  if (key === NO_SIGNAL_KEY) return NO_SIGNAL_LABEL;
  return SIGNAL_LABEL[key] ?? UNKNOWN_SIGNAL_LABEL;
}

export interface SignalGroup {
  /** signalType 또는 NO_SIGNAL_KEY — 필터 값 */
  key: string;
  label: string;
  count: number;
}

/** 순위가 높은 추천의 신호부터 나오도록, 순위순으로 처음 나타난 순서대로 묶는다 */
export function groupBySignal(recommendations: Recommendation[]): SignalGroup[] {
  const groups = new Map<string, number>();
  [...recommendations]
    .sort((a, b) => a.rank - b.rank)
    .forEach((rec) => {
      const key = signalKeyOf(rec);
      groups.set(key, (groups.get(key) ?? 0) + 1);
    });
  return [...groups.entries()].map(([key, count]) => ({ key, label: signalLabel(key), count }));
}
