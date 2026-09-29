// 추천 리스트 (NAME-F01) — docs/8-wireframe.md §3
// 필터는 목록 순서(순위)를 바꾸지 않고 보기만 필터링한다.

import { RecommendationCard } from './RecommendationCard';
import type { Recommendation, RejectedReason, TagStatus } from '../../types/recommendation';

interface RecommendationListProps {
  recommendations: Recommendation[];
  canTag: boolean;
  tagDisabled?: boolean;
  emptyMessage?: string;
  onTag: (recommendation: Recommendation, status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function RecommendationList({
  recommendations,
  canTag,
  tagDisabled,
  emptyMessage = '표시할 항목이 없습니다.',
  onTag,
}: RecommendationListProps) {
  if (recommendations.length === 0) {
    return <p className="state-panel">{emptyMessage}</p>;
  }

  return (
    <ul className="rec-list">
      {recommendations.map((rec) => (
        <li key={rec.id}>
          <RecommendationCard recommendation={rec} canTag={canTag} tagDisabled={tagDisabled} onTag={onTag} />
        </li>
      ))}
    </ul>
  );
}
