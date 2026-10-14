// 명부 한 줄 행 (NAME-F01) — docs/8-wireframe.md §3, NH-Campaigner-UI-proposal.html 변경 포인트 7·8
// 큰 카드 대신 한 줄 행으로 보여 한 화면에 6~7곳이 보이게 한다.
// 사유 아래에 출처 도장을 붙인다. API에 신호 코드가 없어 신호 칩 대신 출처 도장만 둔다.
// 점수 숫자는 표시하지 않고 순위만 둔다(변경 포인트 8).
// 어제 기록 전 여부는 행마다 배지로 붙이지 않고 '오늘 기록' 패널의 수로만 보여준다(변경 포인트 6).
// 탐색 슬롯 여부는 RULE-TARGET-04에 따라 노출하지 않는다(API도 내려주지 않음).

import type { MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { SourceStamp } from '../common/SourceStamp';
import { TagButtons } from './TagButtons';
import { TagStatusBadge } from './TagStatusBadge';
import { industryLeaf } from '../../utils/industry';
import type { Recommendation, RejectedReason, TagStatus } from '../../types/recommendation';
import './RecommendationCard.css';

interface RecommendationCardProps {
  recommendation: Recommendation;
  canTag: boolean;
  tagDisabled?: boolean;
  onTag: (recommendation: Recommendation, status: TagStatus, rejectedReason?: RejectedReason) => void;
}

export function RecommendationCard({ recommendation, canTag, tagDisabled, onTag }: RecommendationCardProps) {
  const navigate = useNavigate();

  function openBrief() {
    navigate(`/brief/${recommendation.id}`);
  }

  function stopPropagation(event: MouseEvent<HTMLElement>) {
    // 행 클릭(상세 이동)과 기록 버튼·링크 클릭이 겹치지 않도록 전파를 막는다.
    event.stopPropagation();
  }

  // 행 전체 클릭은 마우스 편의용이고, 키보드·보조기기 사용자는 상호명 링크로 이동한다
  // (버튼을 포함한 행 자체에 링크 역할을 주지 않는다 — 중첩 상호작용 요소 방지).
  // 왼쪽 3px 막대가 기록 상태 색(방문함 그린 · 보류 옐로우 · 부적합 회색)을 나타낸다.
  return (
    <article
      className={`rec-row rec-row--${recommendation.tagStatus.toLowerCase()}`}
      onClick={openBrief}
      aria-labelledby={`rec-${recommendation.id}-name`}
    >
      <span className="rec-row__rank">
        {recommendation.rank}
        <span className="sr-only">위</span>
      </span>
      <div className="rec-row__who">
        <Link
          id={`rec-${recommendation.id}-name`}
          to={`/brief/${recommendation.id}`}
          className="rec-row__name"
          onClick={stopPropagation}
        >
          {recommendation.businessName}
        </Link>
        <span className="rec-row__industry" title={recommendation.industry}>
          {industryLeaf(recommendation.industry)}
        </span>
      </div>
      <div className="rec-row__why">
        <p className="rec-row__reason" title={recommendation.reasonSummary}>
          {recommendation.reasonSummary}
        </p>
        {recommendation.reasonSourceTag && (
          <div className="rec-row__meta">
            <SourceStamp tag={recommendation.reasonSourceTag} />
          </div>
        )}
      </div>
      <div className="rec-row__actions" onClick={stopPropagation}>
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
