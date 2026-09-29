// 오늘 명부 현황 스트립 — docs/8-wireframe.md §3 "N건 중 M건 미태깅"의 시각화
// 순위별 칸 하나가 추천 1건이며, 칸 색은 태깅 상태를 나타낸다(보기 전용, 조작 없음).
// 오늘 명부의 처리 현황일 뿐 개인 성과 지표가 아니다(CLAUDE.md §0.7) — 비율·달성률로 표기하지 않는다.
// 탐색 슬롯 여부는 구분하지 않는다(RULE-TARGET-04, API도 내려주지 않음).

import { TAG_STATUS_LABEL, type Recommendation } from '../../types/recommendation';
import './RankChip.css';
import './ListStatusStrip.css';

interface ListStatusStripProps {
  recommendations: Recommendation[];
}

export function ListStatusStrip({ recommendations }: ListStatusStripProps) {
  if (recommendations.length === 0) return null;

  const byRank = [...recommendations].sort((a, b) => a.rank - b.rank);
  const untagged = byRank.filter((rec) => rec.tagStatus === 'UNTAGGED').length;
  const count = (status: Recommendation['tagStatus']) => byRank.filter((rec) => rec.tagStatus === status).length;
  const description =
    `오늘 명부 ${byRank.length}건 중 방문함 ${count('VISITED')}건, 보류 ${count('HOLD')}건, ` +
    `부적합 ${count('REJECTED')}건, 미태깅 ${untagged}건`;

  return (
    <div className="list-strip">
      <div className="list-strip__cells" role="img" aria-label={description}>
        {byRank.map((rec) => (
          <span
            key={rec.id}
            className={`rank-chip rank-chip--${rec.tagStatus.toLowerCase()} list-strip__cell`}
            title={`${rec.rank}위 ${rec.businessName} · ${TAG_STATUS_LABEL[rec.tagStatus]}`}
            aria-hidden="true"
          >
            {rec.rank}
          </span>
        ))}
      </div>
      <p className="list-strip__summary" aria-hidden="true">
        {byRank.length}건 중 <strong>{untagged}건</strong> 미태깅
      </p>
    </div>
  );
}
