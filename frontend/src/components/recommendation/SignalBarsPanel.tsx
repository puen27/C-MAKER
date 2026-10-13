// 신호별 대상 패널 — NH-Campaigner-UI-proposal.html 변경 포인트 5 (Sense 단계 노출)
// 막대를 누르면 그 신호의 사업장만 목록에 보인다. 다시 누르면 해제한다.
// API에 신호 코드가 없어 출처명으로 묶는다(utils/sourceTag.ts).

import type { SourceGroup } from '../../utils/sourceTag';
import './SignalBarsPanel.css';

interface SignalBarsPanelProps {
  groups: SourceGroup[];
  active: string | null;
  onSelect: (source: string | null) => void;
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
          const pressed = active === group.source;
          return (
            <li key={group.source}>
              <button
                type="button"
                className="signal-panel__bar"
                aria-pressed={pressed}
                title={`${group.source} 근거 ${group.count}곳`}
                onClick={() => onSelect(pressed ? null : group.source)}
              >
                <span className="signal-panel__label">{group.source}</span>
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
