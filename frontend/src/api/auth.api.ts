// 인증 API 클라이언트 (docs/10-implementation-guide.md §6.3 로그인)

import type { LoginResponse } from '../types/auth';
import { apiFetch } from './client';

export interface LoginRequest {
  username: string;
  password: string;
}

export function login(request: LoginRequest): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', { method: 'POST', body: request });
}

/** 세션 연장 — 계정 정책상 연장 가능한 경우에만 새 토큰을 발급한다 */
export function refreshSession(): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/refresh', { method: 'POST' });
}
