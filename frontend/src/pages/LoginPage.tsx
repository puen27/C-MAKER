// 로그인 화면 (NAME-F01) — docs/8-wireframe.md §2
// mock: 실제 백엔드 인증 없이 값이 입력되면 useLoginMutation(mock)이 성공 처리한다.

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { useLoginMutation } from '../queries/useAuth';
import { toUserMessage } from '../api/client';
import './LoginPage.css';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const loginMutation = useLoginMutation();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    loginMutation.mutate(
      { username, password },
      {
        onSuccess: () => navigate('/dashboard', { replace: true }),
      },
    );
  }

  return (
    <div className="login-page">
      <form className="login-page__card" onSubmit={handleSubmit}>
        <h1 className="login-page__title">BranchSense</h1>

        <div className="login-page__field">
          <input
            className="login-page__input"
            type="text"
            placeholder="아이디"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="login-page__field">
          <input
            className="login-page__input"
            type="password"
            placeholder="비밀번호"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </div>

        {loginMutation.isError && (
          <p className="login-page__error">{toUserMessage(loginMutation.error)}</p>
        )}

        <Button
          type="submit"
          variant="primary-pill"
          className="login-page__submit"
          disabled={loginMutation.isPending}
        >
          {loginMutation.isPending ? '로그인 중…' : '로그인'}
        </Button>
      </form>
    </div>
  );
}
