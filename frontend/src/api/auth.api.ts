// 인증 API 클라이언트 (docs/4-project-principle.md §6)
//
// ⚠ 실제 API 연동 지점: 백엔드 준비 후 아래 mock 구현을 지우고
// apiFetch<LoginResponse>('/auth/login', { method: 'POST', body: { username, password } })
// 형태로 교체한다. 요청/응답 타입은 그대로 재사용 가능하도록 맞춰뒀다.

import type { AuthUser } from '../types/auth';
import { mockLogin } from './mockData';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

const MOCK_LATENCY_MS = 250;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export async function login(request: LoginRequest): Promise<LoginResponse> {
  // TODO(실제 API 연동): return apiFetch<LoginResponse>('/auth/login', { method: 'POST', body: request });
  const result = mockLogin(request.username, request.password);
  return delay(result);
}
