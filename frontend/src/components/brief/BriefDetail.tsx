// 상담 브리프 상세 콘텐츠 (NAME-F01) — docs/8-wireframe.md §4, RULE-BRIEF-01
import { useNavigate } from 'react-router-dom';
import { TagButtons } from '../recommendation/TagButtons';
import type { Brief } from '../../types/brief';
import type { RejectedReason, TagStatus } from '../../types/recommendation';
import './BriefDetail.css';

interface BriefDetailProps {
  brief: Brief;
  onTag: (status: TagStatus, rejectedReason?: RejectedReason) => void;
  tagPending?: boolean;
}

export function BriefDetail({ brief, onTag, tagPending }: BriefDetailProps) {
  const navigate = useNavigate();

  return (
    <div>
      <button type="button" className="brief-detail__back" onClick={() => navigate('/dashboard')}>
        ← 목록으로
      </button>

      <h1 className="brief-detail__title">
        {brief.businessName}
        <span className="brief-detail__distance">· {brief.distanceLabel}</span>
      </h1>

      <section className="brief-detail__section">
        <h2>선정 사유</h2>
        {brief.reasonFacts.map((fact, index) => (
          <p key={index} className="brief-detail__fact">
            {fact.text}
            <span className="brief-detail__source-tag">[{fact.sourceTag}]</span>
          </p>
        ))}
      </section>

      <section className="brief-detail__section">
        <h2>전화 화법</h2>
        <div className="brief-detail__script">
          {brief.scriptLines.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      </section>

      <section className="brief-detail__section">
        <h2>방문 체크리스트</h2>
        <ul className="brief-detail__checklist">
          {brief.checklist.map((item) => (
            <li key={item}>
              <input type="checkbox" readOnly /> {item}
            </li>
          ))}
        </ul>
      </section>

      <div className="brief-detail__actions">
        <TagButtons currentStatus={brief.tagStatus} disabled={tagPending} onTag={onTag} />
      </div>
    </div>
  );
}
