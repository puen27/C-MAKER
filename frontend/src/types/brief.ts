// 상담 브리프(BRIEF) 관련 타입 (NAME-F04)
// 참고: docs/1-domain-definition.md BRIEF 엔티티, RULE-BRIEF-01~03

import type { RejectedReason, TagStatus } from './recommendation';

export interface BriefFact {
  /** 사실 문장 본문 — 배치가 공개 데이터로부터 결정론적으로 생성한다 */
  text: string;
  /** RULE-BRIEF-01: 모든 사실 문장은 출처 태그를 가져야 한다. 형식: "소스명·기준일" */
  sourceTag: string;
}

/**
 * LLM: 게이트웨이가 생성한 화법(그라운딩 검증 통과분) / TEMPLATE: LLM 미가용 시 정형 인사 화법 /
 * REASON_ONLY: 화법이 검증에서 전부 차단되어 사유만 표시(RULE-BRIEF-02)
 */
export type BriefGenerationStatus = 'LLM' | 'TEMPLATE' | 'REASON_ONLY';

export interface Brief {
  recommendationId: number;
  businessName: string;
  industry: string;
  address: string | null;
  distanceLabel: string;
  recommendedOn: string;
  /** 선정 사유 — 출처 태그가 붙은 사실 문장 목록(RULE-BRIEF-01) */
  reasonFacts: BriefFact[];
  /** 전화 화법 — 3문장 이내 */
  scriptLines: string[];
  /** 방문 체크리스트 */
  checklist: string[];
  generationStatus: BriefGenerationStatus;
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason | null;
}
