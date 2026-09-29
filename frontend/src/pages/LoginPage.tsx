// 로그인 화면 (NAME-F01) — docs/8-wireframe.md §2
// 계정은 운영자가 DB에 직접 등록한다(가입 화면 없음, REQ-01 재정의).

import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { useLoginMutation } from '../queries/useAuth';
import { useAuthStore } from '../stores/authStore';
import { toUserMessage } from '../api/client';
import { homePathFor } from '../utils/roles';
import './LoginPage.css';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const loginMutation = useLoginMutation();
  const user = useAuthStore((state) => state.user);
  const expired = (location.state as { reason?: string } | null)?.reason === 'expired';

  if (user && !loginMutation.isPending) {
    return <Navigate to={homePathFor(user.role)} replace />;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    loginMutation.mutate(
      { username: username.trim(), password },
      { onSuccess: (data) => navigate(homePathFor(data.user.role), { replace: true }) },
    );
  }

  return (
    <main className="login-page">
      <div className="login-page__column">
        <header className="login-page__brand">
          <h1 className="login-page__title">C-MAKER</h1>
          <p className="login-page__tagline">오늘 만날 사업장과 그 근거를 매일 아침 정리합니다.</p>
        </header>

        <form className="login-page__card" onSubmit={handleSubmit} aria-label="로그인">
          {expired && !loginMutation.isError && (
            <p className="login-page__notice" role="status">
              세션이 만료되어 로그아웃되었습니다. 다시 로그인해주세요.
            </p>
          )}

          <div className="login-page__field">
            <label htmlFor="login-username" className="login-page__label">
              아이디
            </label>
            <input
              id="login-username"
              className="input login-page__input"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="login-page__field">
            <label htmlFor="login-password" className="login-page__label">
              비밀번호
            </label>
            <input
              id="login-password"
              className="input login-page__input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {loginMutation.isError && (
            <p className="login-page__error" role="alert">
              {toUserMessage(loginMutation.error)}
            </p>
          )}

          <Button
            type="submit"
            variant="primary-pill"
            className="login-page__submit"
            disabled={loginMutation.isPending || !username.trim() || !password}
          >
            {loginMutation.isPending ? '로그인 중…' : '로그인'}
          </Button>
        </form>

        <p className="login-page__footnote">계정은 본부 운영 담당자가 발급합니다.</p>
      </div>
    </main>
  );
}
