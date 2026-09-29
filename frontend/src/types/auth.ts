// 인증 관련 타입 (NAME-F04)

export type UserRole = 'RM' | 'BRANCH_MANAGER';

export interface AuthUser {
  id: string;
  name: string;
  role: UserRole;
  branchId: string;
  branchName: string;
}
