// 상단 유틸리티 바 (NAME-F01) — docs/8-wireframe.md §1, docs/9-style-guide.md §5.8
// 로고 · 사용자명 · 세션 타이머(만료 5분 전 경고색) · 연장 · 로그아웃, 아래 줄에 보조 안내.
// 세션이 만료되면 자동으로 로그아웃한다(USER.session_timeout_minutes).

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { useRefreshSessionMutation } from '../../queries/useAuth';
import { formatCountdown } from '../../utils/date';
import './TopUtilityBar.css';

const WARNING_SECONDS = 5 * 60;

function secondsUntil(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.floor((Date.parse(iso) - Date.now()) / 1000));
}

export function TopUtilityBar() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const logout = useAuthStore((state) => state.logout);
  const refreshMutation = useRefreshSessionMutation();
  const [remaining, setRemaining] = useState(() => secondsUntil(expiresAt));

  useEffect(() => {
    const update = () => setRemaining(secondsUntil(expiresAt));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt]);

  useEffect(() => {
    if (user && expiresAt && remaining === 0) {
      logout();
      queryClient.clear();
      navigate('/login', { replace: true, state: { reason: 'expired' } });
    }
  }, [remaining, user, expiresAt, logout, queryClient, navigate]);

  function handleLogout() {
    logout();
    queryClient.clear();
    navigate('/login', { replace: true });
  }

  const isWarning = remaining <= WARNING_SECONDS;

  return (
    <header className="utility-bar">
      <div className="utility-bar__row">
        <span className="utility-bar__logo">C-MAKER</span>
        {user && (
          <div className="utility-bar__user">
            <span className="utility-bar__name">{user.name} 님</span>
            <span aria-hidden="true">·</span>
            <span
              className={`utility-bar__timer ${isWarning ? 'is-warning' : ''}`}
              role="timer"
              aria-label={`세션 남은 시간 ${formatCountdown(remaining)}`}
            >
              {isWarning && <span aria-hidden="true">⏱ </span>}
              {formatCountdown(remaining)}
            </span>
            {user.sessionExtendable && (
              <button
                type="button"
                className="utility-bar__link"
                onClick={() => refreshMutation.mutate()}
                disabled={refreshMutation.isPending}
              >
                연장
              </button>
            )}
            <span aria-hidden="true">·</span>
            <button type="button" className="utility-bar__link" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        )}
      </div>
      <div className="utility-bar__aux">고객센터 · 도움말</div>
    </header>
  );
}
