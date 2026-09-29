// 인증 관련 타입 (NAME-F04) — 백엔드 common/schemas/auth.py와 1:1 대응

/** VAL-08 계정 역할. 본부는 마케팅/준법 하위 역할로 구분된다(RULE-CAMPAIGN-01 전제). */
export type UserRole = 'RM' | 'BRANCH_MANAGER' | 'HQ_MARKETING' | 'HQ_COMPLIANCE';

export const ROLE_LABEL: Record<UserRole, string> = {
  RM: 'RM',
  BRANCH_MANAGER: '지점장',
  HQ_MARKETING: '본부(마케팅)',
  HQ_COMPLIANCE: '본부(준법)',
};

export interface AuthUser {
  id: number;
  name: string;
  role: UserRole;
  /** 본부 역할은 소속 지점이 없다(CONST-03) */
  branchId: number | null;
  branchName: string | null;
  branchCode: string | null;
  sessionTimeoutMinutes: number;
  sessionExtendable: boolean;
}

export interface LoginResponse {
  token: string;
  /** 토큰 만료 시각(ISO 8601) — 상단 유틸리티 바 세션 타이머 기준 */
  expiresAt: string;
  user: AuthUser;
}
