// 오늘 기록 패널 — NH-Campaigner-UI-proposal.html 변경 포인트 4 (점선 박스 1~20 대체)
// 오늘 명부의 처리 현황일 뿐 개인 성과 지표가 아니다(CLAUDE.md §0.7) — 비율·달성률로 표기하지 않는다.
// 어제 기록하지 않은 곳 수(UC-09)와 '내일 명부에 반영' 문구로 Learn 구조를 설명한다.
// 탐색 슬롯 여부는 구분하지 않는다(RULE-TARGET-04).

import type { Recommendation, TagStatus } from '../../types/recommendation';
import './TodayRecordPanel.css';

interface TodayRecordPanelProps {
  recommendations: Recommendation[];
  yesterdayUntaggedCount?: number;
}

const SEGMENTS: { status: Exclude<TagStatus, 'UNTAGGED'>; key: string; label: string }[] = [
  { status: 'VISITED', key: 'visited', label: '방문함' },
  { status: 'HOLD', key: 'hold', label: '보류' },
  { status: 'REJECTED', key: 'excluded', label: '부적합' },
];

export function TodayRecordPanel({ recommendations, yesterdayUntaggedCount = 0 }: TodayRecordPanelProps) {
  const total = recommendations.length;
  const count = (status: TagStatus) => recommendations.filter((rec) => rec.tagStatus === status).length;
  const untagged = count('UNTAGGED');
  const recorded = total - untagged;
  const description =
    `${total}곳 중 ${recorded}곳 기록: ` + SEGMENTS.map((seg) => `${seg.label} ${count(seg.status)}`).join(', ');

  return (
    <section className="record-panel" aria-labelledby="record-panel-title">
      <h2 className="record-panel__title" id="record-panel-title">
        오늘 기록
      </h2>
      <p className="record-panel__count">
        <b>{recorded}</b>/ {total}곳
      </p>
      <div className="record-panel__meter" role="img" aria-label={description}>
        {total > 0 &&
          SEGMENTS.map((seg) => {
            const n = count(seg.status);
            return n > 0 ? (
              <i key={seg.key} className={`record-panel__seg is-${seg.key}`} style={{ width: `${(n / total) * 100}%` }} />
            ) : null;
          })}
      </div>
      <ul className="record-panel__legend">
        {SEGMENTS.map((seg) => (
          <li key={seg.key}>
            <span className={`record-panel__swatch is-${seg.key}`} aria-hidden="true" />
            {seg.label}
            <b>{count(seg.status)}</b>
          </li>
        ))}
        <li>
          <span className="record-panel__swatch is-none" aria-hidden="true" />
          기록 전<b>{untagged}</b>
        </li>
      </ul>
      {yesterdayUntaggedCount > 0 && (
        <p className="record-panel__carry">
          <span className="record-panel__dot" aria-hidden="true" />
          어제 기록하지 않은 곳 <b>{yesterdayUntaggedCount}곳</b>
        </p>
      )}
      <p className={`record-panel__hint ${yesterdayUntaggedCount > 0 ? 'is-follow' : ''}`}>
        기록은 내일 명부에 반영됩니다.
      </p>
    </section>
  );
}
