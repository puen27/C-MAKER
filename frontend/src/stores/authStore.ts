// Zustand 스토어 — 클라이언트 전용 인증 상태 (NAME-F03)
// 서버 데이터(추천/브리프/태깅 등)는 여기 두지 않는다(PRIN-07). 로그인 토큰, 토큰 만료 시각과
// 화면 표시에 필요한 최소 사용자 정보(이름/역할/소속지점/세션 정책)만 보관한다.

import { create } from 'zustand';
import type { AuthUser } from '../types/auth';

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  /** 토큰 만료 시각(ISO 8601) — 세션 타이머 기준 */
  expiresAt: string | null;
  login: (token: string, user: AuthUser, expiresAt: string) => void;
  logout: () => void;
}

const TOKEN_STORAGE_KEY = 'cmaker.token';
const USER_STORAGE_KEY = 'cmaker.user';
const EXPIRES_STORAGE_KEY = 'cmaker.expiresAt';

function loadInitialState(): Pick<AuthState, 'token' | 'user' | 'expiresAt'> {
  try {
    const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    const userRaw = sessionStorage.getItem(USER_STORAGE_KEY);
    const expiresAt = sessionStorage.getItem(EXPIRES_STORAGE_KEY);
    const user = userRaw ? (JSON.parse(userRaw) as AuthUser) : null;
    // 만료된 세션은 복원하지 않는다.
    if (!token || !user || !expiresAt || Date.parse(expiresAt) <= Date.now()) {
      return { token: null, user: null, expiresAt: null };
    }
    return { token, user, expiresAt };
  } catch {
    return { token: null, user: null, expiresAt: null };
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  ...loadInitialState(),
  login: (token, user, expiresAt) => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    sessionStorage.setItem(EXPIRES_STORAGE_KEY, expiresAt);
    set({ token, user, expiresAt });
  },
  logout: () => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(USER_STORAGE_KEY);
    sessionStorage.removeItem(EXPIRES_STORAGE_KEY);
    set({ token: null, user: null, expiresAt: null });
  },
}));

export function getStoredToken(): string | null {
  return useAuthStore.getState().token;
}
