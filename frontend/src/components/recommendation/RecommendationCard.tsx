// 추천 카드 (NAME-F01) — docs/8-wireframe.md §3
// 점수는 백엔드 판단 레이어가 확정한 값을 읽기 전용으로만 표시한다.
// 탐색 슬롯 여부는 RULE-TARGET-04에 따라 이 카드에 노출하지 않는다.

import type { MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { StatusBadge } from '../common/StatusBadge';
import { TagButtons } from './TagButtons';
import type { Recommendation, RejectedReason, TagStatus } from '../../types/recommendation';
import './RecommendationCard.css';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onTag: (id: string, status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function RecommendationCard({ recommendation, onTag }: RecommendationCardProps) {
  const navigate = useNavigate();
  const isTagged = recommendation.tagStatus !== 'UNTAGGED';

  function handleCardClick() {
    navigate(`/brief/${recommendation.id}`);
  }

  function handleActionsClick(event: MouseEvent<HTMLDivElement>) {
    // 카드 클릭(상세 이동)과 태깅 버튼 클릭이 겹치지 않도록 전파를 막는다.
    event.stopPropagation();
  }

  return (
    <div
      className={`rec-card ${isTagged ? 'is-tagged' : ''}`}
      onClick={handleCardClick}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter') handleCardClick();
      }}
    >
      <div className="rec-card__header">
        <span className="rec-card__rank">{recommendation.rank}</span>
        <StatusBadge tone="outline">({recommendation.industry})</StatusBadge>
        <span className="rec-card__name">{recommendation.businessName}</span>
        <span className="rec-card__score">점수 {recommendation.score}</span>
      </div>
      <p className="rec-card__reason">
        사유: {recommendation.reasonSummary}
        <span className="rec-card__source-tag">[{recommendation.reasonSourceTag}]</span>
      </p>
      <div className="rec-card__actions" onClick={handleActionsClick}>
        <TagButtons
          currentStatus={recommendation.tagStatus}
          onTag={(status, reason) => onTag(recommendation.id, status, reason)}
        />
      </div>
    </div>
  );
}
