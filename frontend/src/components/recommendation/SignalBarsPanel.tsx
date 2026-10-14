// 신호별 대상 패널 — NH-Campaigner-UI-proposal.html 변경 포인트 5 (Sense 단계 노출)
// 막대를 누르면 그 신호의 사업장만 목록에 보인다. 다시 누르면 해제한다.
// 대표 신호 종류(signalType)로 묶어 신호명으로 보여준다(utils/signal.ts).

import type { SignalGroup } from '../../utils/signal';
import './SignalBarsPanel.css';

interface SignalBarsPanelProps {
  groups: SignalGroup[];
  /** 선택된 신호 키(signalType). null이면 전체 */
  active: string | null;
  onSelect: (signalKey: string | null) => void;
}

export function SignalBarsPanel({ groups, active, onSelect }: SignalBarsPanelProps) {
  if (groups.length === 0) return null;
  const max = Math.max(...groups.map((group) => group.count));

  return (
    <section className="signal-panel" aria-labelledby="signal-panel-title">
      <h2 className="signal-panel__title" id="signal-panel-title">
        신호별 대상
      </h2>
      <p className="signal-panel__sub">오늘 명부를 만든 신호입니다. 누르면 그 사업장만 봅니다.</p>
      <ul className="signal-panel__bars">
        {groups.map((group) => {
          const pressed = active === group.key;
          return (
            <li key={group.key}>
              <button
                type="button"
                className="signal-panel__bar"
                aria-pressed={pressed}
                title={`${group.label} ${group.count}곳`}
                onClick={() => onSelect(pressed ? null : group.key)}
              >
                <span className="signal-panel__label">{group.label}</span>
                <span className="signal-panel__track" aria-hidden="true">
                  <span className="signal-panel__fill" style={{ width: `${(group.count / max) * 100}%` }} />
                </span>
                <span className="signal-panel__n">{group.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
