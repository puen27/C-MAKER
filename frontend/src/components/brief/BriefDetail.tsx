// 상담 브리프 상세 콘텐츠 (NAME-F01) — docs/8-wireframe.md §4, RULE-BRIEF-01/02
// 모든 사실 문장 옆에 [소스명·기준일] 출처 태그를 붙인다. 근거 없는 문장은 배치의 검증 단계에서
// 이미 제거되어 여기 나타나지 않는다.
// 데스크톱에서는 읽을 내용(사유·화법)과 할 일(체크리스트·태깅)을 좌우로 나눠, 태깅 버튼이 늘 보이게 한다.

import { Link } from 'react-router-dom';
import { StatusBadge } from '../common/StatusBadge';
import { TagButtons } from '../recommendation/TagButtons';
import { TagStatusBadge } from '../recommendation/TagStatusBadge';
import type { Brief } from '../../types/brief';
import type { RejectedReason, TagStatus } from '../../types/recommendation';
import './BriefDetail.css';

interface BriefDetailProps {
  brief: Brief;
  canTag: boolean;
  onTag: (status: TagStatus, rejectedReason?: RejectedReason) => void;
  tagPending?: boolean;
}

export function BriefDetail({ brief, canTag, onTag, tagPending }: BriefDetailProps) {
  return (
    <div className="brief-detail">
      <Link to="/dashboard" className="brief-detail__back">
        <span aria-hidden="true">←</span> 목록으로
      </Link>

      <header className="brief-detail__header">
        <h1 className="page-title">{brief.businessName}</h1>
        <div className="brief-detail__meta">
          <StatusBadge tone="outline">{brief.industry}</StatusBadge>
          <span>{brief.distanceLabel}</span>
          {brief.address && <span className="brief-detail__address">{brief.address}</span>}
        </div>
      </header>

      <div className="brief-detail__layout">
        <article className="brief-detail__sheet">
          <section className="brief-detail__section" aria-labelledby="brief-reason">
            <h2 id="brief-reason" className="brief-detail__heading">
              선정 사유
            </h2>
            {brief.reasonFacts.length === 0 ? (
              <p className="brief-detail__muted">선정 사유를 생성하는 중입니다.</p>
            ) : (
              <ul className="brief-detail__facts">
                {brief.reasonFacts.map((fact, index) => (
                  <li key={index} className="brief-detail__fact">
                    {fact.text}
                    <span className="brief-detail__source-tag">[{fact.sourceTag}]</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="brief-detail__section" aria-labelledby="brief-script">
            <h2 id="brief-script" className="brief-detail__heading">
              전화 화법
            </h2>
            {brief.scriptLines.length > 0 ? (
              <blockquote className="brief-detail__script">
                {brief.scriptLines.map((line, index) => (
                  <p key={index}>{line}</p>
                ))}
              </blockquote>
            ) : (
              <p className="brief-detail__muted">
                근거가 확인되지 않은 문장이 검증 단계에서 차단되어 선정 사유만 표시합니다.
              </p>
            )}
            {brief.generationStatus === 'TEMPLATE' && (
              <p className="brief-detail__muted">기본 인사 화법입니다(문장 생성 서비스 미연결).</p>
            )}
          </section>
        </article>

        <aside className="brief-detail__aside">
          <section className="brief-detail__panel" aria-labelledby="brief-checklist">
            <h2 id="brief-checklist" className="brief-detail__heading">
              방문 체크리스트
            </h2>
            <ul className="brief-detail__checklist">
              {brief.checklist.map((item) => (
                <li key={item}>
                  <label className="brief-detail__check">
                    <input type="checkbox" />
                    <span>{item}</span>
                  </label>
                </li>
              ))}
            </ul>
          </section>

          <section className="brief-detail__panel" aria-labelledby="brief-tagging">
            <h2 id="brief-tagging" className="brief-detail__heading">
              접촉 결과
            </h2>
            {canTag ? (
              <TagButtons
                currentStatus={brief.tagStatus}
                currentReason={brief.rejectedReason}
                disabled={tagPending}
                onTag={onTag}
              />
            ) : (
              <TagStatusBadge status={brief.tagStatus} reason={brief.rejectedReason} />
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
