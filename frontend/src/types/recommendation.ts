// 추천(RECOMMENDATION) 관련 타입 (NAME-F04) — 백엔드 common/schemas/recommendation.py와 대응
// 참고: docs/1-domain-definition.md RECOMMENDATION 엔티티, VAL-06, RULE-TARGET-04

export type TagStatus = 'UNTAGGED' | 'VISITED' | 'HOLD' | 'REJECTED';

/** 부적합 태깅 사유 4종 (VAL-06) — 정확히 1개 필수 선택 */
export type RejectedReason =
  | 'ALREADY_CUSTOMER' // 이미 거래중
  | 'NOT_TARGET' // 대상 아님
  | 'INFO_ERROR' // 정보 오류
  | 'UNREACHABLE'; // 접촉 불가

export const REJECTED_REASON_LABEL: Record<RejectedReason, string> = {
  ALREADY_CUSTOMER: '이미 거래중',
  NOT_TARGET: '대상 아님',
  INFO_ERROR: '정보 오류',
  UNREACHABLE: '접촉 불가',
};

export const TAG_STATUS_LABEL: Record<TagStatus, string> = {
  UNTAGGED: '미태깅',
  VISITED: '방문함',
  HOLD: '보류',
  REJECTED: '부적합',
};

/**
 * 오늘의 접촉 명부 1건. 탐색 슬롯 여부(RULE-TARGET-03)는 API가 내려주지 않는다 —
 * RULE-TARGET-04에 따라 화면에서 구분할 수 없어야 하기 때문이다.
 */
export interface Recommendation {
  id: number;
  /** TOP 20 내 순위. 필터링으로만 화면을 바꾸며 이 값 자체는 클라이언트에서 변경하지 않는다 */
  rank: number;
  businessName: string;
  /** 스코어링에 쓰인 업종 분류 — 정보용 표기, 필터 조건 아님(8-wireframe.md §3) */
  industry: string;
  /** 판정 레이어(배치)가 확정한 점수. 프론트는 읽기 전용으로만 표시한다 */
  score: number;
  /** 선정 사유 1줄 */
  reasonSummary: string;
  /** RULE-BRIEF-01 출처 태그, 형식: "소스명·기준일" */
  reasonSourceTag: string;
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason | null;
  /** 직전 명부에서 미태깅으로 이어진 항목인지(UC-09 예외 흐름) */
  carriedOverFromYesterday: boolean;
}

/** 명부 상단 배너용 요약 (UC-09, RULE-TARGET-06, RULE-SENSE-02) */
export interface RecommendationSummary {
  date: string;
  total: number;
  untaggedCount: number;
  yesterdayUntaggedCount: number;
  areaReasonRatio: number;
  areaReasonRatioLimit: number;
  areaReasonRatioExceeded: boolean;
  activeEventCount: number;
  trimmedEventCount: number;
}

export interface TagResult {
  recommendationId: number;
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason | null;
}

export type CrmFileFormat = 'csv' | 'xlsx';
