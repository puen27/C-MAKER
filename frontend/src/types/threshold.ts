// 임계치·운영 파라미터(THRESHOLD_CONFIG) 타입 (REQ-14, UC-15, VAL-05)

/** SIGNAL = 신호 승격 임계치, SYSTEM = 쿨다운·상한 등 운영 파라미터 */
export type ThresholdCategory = 'SIGNAL' | 'SYSTEM';

export interface Threshold {
  id: number;
  signalType: string;
  category: ThresholdCategory;
  label: string;
  description: string;
  thresholdValue: number;
  unit: string;
  /** UI에서 변경할 수 없는 항목(예: 기상특보 발효 즉시) */
  isFixed: boolean;
  integerOnly: boolean;
  minValue: number | null;
  maxValue: number | null;
  updatedByName: string | null;
  updatedAt: string;
}

export interface ThresholdHistoryItem {
  id: number;
  changedByName: string | null;
  changedAt: string;
  // 감사 로그 원본(JSONB)이라 snake_case 키로 온다
  beforeValue: { threshold_value: number; unit: string } | null;
  afterValue: { threshold_value: number; unit: string } | null;
}
