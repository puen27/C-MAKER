// 추천 카드 (NAME-F01) — docs/8-wireframe.md §3
// 점수는 배치 판단 레이어가 확정한 값을 읽기 전용으로만 표시한다.
// 탐색 슬롯 여부는 RULE-TARGET-04에 따라 이 카드에 노출하지 않는다(API도 내려주지 않음).

import type { MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { StatusBadge } from '../common/StatusBadge';
import { TagButtons } from './TagButtons';
import { TagStatusBadge } from './TagStatusBadge';
import type { Recommendation, RejectedReason, TagStatus } from '../../types/recommendation';
import './RankChip.css';
import './RecommendationCard.css';

interface RecommendationCardProps {
  recommendation: Recommendation;
  canTag: boolean;
  tagDisabled?: boolean;
  onTag: (recommendation: Recommendation, status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function RecommendationCard({ recommendation, canTag, tagDisabled, onTag }: RecommendationCardProps) {
  const navigate = useNavigate();
  const isTagged = recommendation.tagStatus !== 'UNTAGGED';

  function openBrief() {
    navigate(`/brief/${recommendation.id}`);
  }

  function stopPropagation(event: MouseEvent<HTMLElement>) {
    // 카드 클릭(상세 이동)과 태깅 버튼·링크 클릭이 겹치지 않도록 전파를 막는다.
    event.stopPropagation();
  }

  // 카드 전체 클릭은 마우스 편의용이고, 키보드·보조기기 사용자는 상호명 링크로 이동한다
  // (버튼을 포함한 카드 자체에 링크 역할을 주지 않는다 — 중첩 상호작용 요소 방지).
  // 순위 칩은 상단 명부 현황(ListStatusStrip)의 칸과 같은 형태·색을 쓴다: 미태깅은 점선, 태깅 완료는 상태색 채움.
  return (
    <article
      className={`rec-card ${isTagged ? 'is-tagged' : ''}`}
      onClick={openBrief}
      aria-labelledby={`rec-${recommendation.id}-name`}
    >
      <span className={`rank-chip rank-chip--${recommendation.tagStatus.toLowerCase()} rec-card__rank`}>
        {recommendation.rank}
        <span className="sr-only">위</span>
      </span>
      <div className="rec-card__body">
        <div className="rec-card__header">
          <StatusBadge tone="outline">{recommendation.industry}</StatusBadge>
          <Link
            id={`rec-${recommendation.id}-name`}
            to={`/brief/${recommendation.id}`}
            className="rec-card__name"
            onClick={stopPropagation}
          >
            {recommendation.businessName}
          </Link>
          {recommendation.carriedOverFromYesterday && <StatusBadge tone="hold">어제 미태깅</StatusBadge>}
        </div>
        <p className="rec-card__reason">
          사유: {recommendation.reasonSummary}
          {recommendation.reasonSourceTag && (
            <span className="rec-card__source-tag">[{recommendation.reasonSourceTag}]</span>
          )}
        </p>
      </div>
      <span className="rec-card__score">점수 {recommendation.score.toFixed(2)}</span>
      <div className="rec-card__actions" onClick={stopPropagation}>
        {canTag ? (
          <TagButtons
            currentStatus={recommendation.tagStatus}
            currentReason={recommendation.rejectedReason}
            disabled={tagDisabled}
            onTag={(status, reason) => onTag(recommendation, status, reason)}
          />
        ) : (
          <TagStatusBadge status={recommendation.tagStatus} reason={recommendation.rejectedReason} />
        )}
      </div>
    </article>
  );
}
