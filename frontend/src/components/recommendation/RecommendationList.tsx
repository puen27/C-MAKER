// 추천 리스트 (NAME-F01) — docs/8-wireframe.md §3
// 필터는 목록 순서(순위)를 바꾸지 않고 보기만 필터링한다.

import { RecommendationCard } from './RecommendationCard';
import type { Recommendation, RejectedReason, TagStatus } from '../../types/recommendation';

interface RecommendationListProps {
  recommendations: Recommendation[];
  onTag: (id: string, status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function RecommendationList({ recommendations, onTag }: RecommendationListProps) {
  if (recommendations.length === 0) {
    return <p>표시할 항목이 없습니다.</p>;
  }

  return (
    <div>
      {recommendations.map((rec) => (
        <RecommendationCard key={rec.id} recommendation={rec} onTag={onTag} />
      ))}
    </div>
  );
}
