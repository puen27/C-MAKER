// Zustand 스토어 — 클라이언트 전용 인증 상태 (NAME-F03)
// 서버 데이터(추천/브리프/태깅 등)는 여기 두지 않는다(PRIN-07). 로그인 토큰과
// 화면 표시에 필요한 최소 사용자 정보(이름/역할/소속지점)만 보관한다.

import { create } from 'zustand';
import type { AuthUser } from '../types/auth';

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
}

const TOKEN_STORAGE_KEY = 'branchsense.token';
const USER_STORAGE_KEY = 'branchsense.user';

function loadInitialState(): { token: string | null; user: AuthUser | null } {
  try {
    const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    const userRaw = sessionStorage.getItem(USER_STORAGE_KEY);
    const user = userRaw ? (JSON.parse(userRaw) as AuthUser) : null;
    return { token, user };
  } catch {
    return { token: null, user: null };
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  ...loadInitialState(),
  login: (token, user) => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    set({ token, user });
  },
  logout: () => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(USER_STORAGE_KEY);
    set({ token: null, user: null });
  },
}));

export function getStoredToken(): string | null {
  return useAuthStore.getState().token;
}
