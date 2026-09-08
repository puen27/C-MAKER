// 상담 브리프(BRIEF) 관련 타입 (NAME-F04)
// 참고: docs/1-domain-definition.md BRIEF 엔티티, RULE-BRIEF-01~03

import type { RejectedReason, TagStatus } from './recommendation';

export interface BriefFact {
  /** 사실 문장 본문 */
  text: string;
  /** RULE-BRIEF-01: 모든 사실 문장은 출처 태그를 가져야 한다. 형식: "소스명·기준일" */
  sourceTag: string;
}

export interface Brief {
  recommendationId: string;
  businessName: string;
  industry: string;
  distanceLabel: string;
  /** 선정 사유 — 출처 태그가 붙은 사실 문장 목록(RULE-BRIEF-01) */
  reasonFacts: BriefFact[];
  /** 전화 화법 — 3문장 이내(CLAUDE.md F-2 규칙) */
  scriptLines: string[];
  /** 방문 체크리스트 */
  checklist: string[];
  tagStatus: TagStatus;
  rejectedReason?: RejectedReason;
}
