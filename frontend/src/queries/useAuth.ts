// TanStack Query 훅 — 로그인·세션 연장 (서버 상태: 인증 처리 결과)
// 로그인 성공 후 토큰/사용자 정보는 클라이언트 상태이므로 authStore(zustand)에 저장한다(PRIN-07).

import { useMutation } from '@tanstack/react-query';
import { login, refreshSession, type LoginRequest } from '../api/auth.api';
import { useAuthStore } from '../stores/authStore';

export function useLoginMutation() {
  const setAuth = useAuthStore((state) => state.login);

  return useMutation({
    mutationFn: (request: LoginRequest) => login(request),
    onSuccess: (data) => {
      setAuth(data.token, data.user, data.expiresAt);
    },
  });
}

export function useRefreshSessionMutation() {
  const setAuth = useAuthStore((state) => state.login);

  return useMutation({
    mutationFn: () => refreshSession(),
    onSuccess: (data) => {
      setAuth(data.token, data.user, data.expiresAt);
    },
  });
}
