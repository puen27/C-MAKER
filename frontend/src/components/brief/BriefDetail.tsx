// 상담 브리프 상세 콘텐츠 (NAME-F01) — docs/8-wireframe.md §4, RULE-BRIEF-01/02
// NH-Campaigner-UI-proposal.html P1 반영:
//   10 — 핵심 근거(첫 사실 문장)와 보조 근거(나머지)를 나눠 보여준다. 모든 문장에 출처 도장을 붙인다.
//   11 — 전화 화법을 인사·용건·약속 3단계로 나눠 오른쪽에 고정하고, AI 작성 여부를 표시한다.
// 근거 없는 문장은 배치의 검증 단계에서 이미 제거되어 여기 나타나지 않는다.

import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { SourceStamp } from '../common/SourceStamp';
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

// 배치 화법은 '인사·연락 사유 / 연락 목적 / 다음 행동 요청' 3문장 구조다(brief_generator.py).
// 검증에서 일부 문장이 빠지면 단계가 어긋나므로, 3문장이 모두 있을 때만 단계 이름을 붙인다.
const STEP_LABELS = ['인사', '용건', '약속'];

const Icon = {
  back: <path d="M10 3.5 5.5 8l4.5 4.5" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 5.5V3.8a1.3 1.3 0 0 0-1.3-1.3H3.8a1.3 1.3 0 0 0-1.3 1.3v5.4a1.3 1.3 0 0 0 1.3 1.3h1.7" />
    </>
  ),
};

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg className="brief-detail__icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export function BriefDetail({ brief, canTag, onTag, tagPending }: BriefDetailProps) {
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [keyFact, ...supportFacts] = brief.reasonFacts;
  const labeled = brief.scriptLines.length === STEP_LABELS.length;

  async function copyScript() {
    try {
      await navigator.clipboard.writeText(brief.scriptLines.join('\n'));
      setCopyNotice('화법을 복사했습니다.');
    } catch {
      setCopyNotice('복사하지 못했습니다. 화법을 직접 선택해 복사하세요.');
    }
  }

  return (
    <div className="brief-detail">
      <Link to="/dashboard" className="brief-detail__back">
        <Svg>{Icon.back}</Svg>
        오늘의 접촉
      </Link>

      <div className="brief-detail__layout">
        <div className="brief-detail__main">
          <header className="brief-detail__card">
            <h1 className="brief-detail__name">{brief.businessName}</h1>
            <dl className="brief-detail__facts-list">
              <div>
                <dt>업종</dt>
                <dd>{brief.industry}</dd>
              </div>
              <div>
                <dt>거리</dt>
                <dd>{brief.distanceLabel}</dd>
              </div>
              {brief.address && (
                <div>
                  <dt>주소</dt>
                  <dd>{brief.address}</dd>
                </div>
              )}
            </dl>
          </header>

          <section className="brief-detail__card" aria-labelledby="brief-reason">
            <h2 id="brief-reason" className="brief-detail__sec-title">
              왜 지금 연락하나요
            </h2>
            <p className="brief-detail__sec-sub">공공데이터를 기준으로 규칙이 고른 근거입니다.</p>
            {!keyFact ? (
              <p className="brief-detail__muted">선정 사유를 생성하는 중입니다.</p>
            ) : (
              <>
                <div className="brief-detail__key">
                  <span className="brief-detail__lbl">핵심 근거</span>
                  <p>{keyFact.text}</p>
                  <SourceStamp tag={keyFact.sourceTag} />
                </div>
                {supportFacts.length > 0 && (
                  <div className="brief-detail__more">
                    <span className="brief-detail__lbl">보조 근거</span>
                    <ul>
                      {supportFacts.map((fact, index) => (
                        <li key={index}>
                          <span>{fact.text}</span>
                          <SourceStamp tag={fact.sourceTag} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </section>

          {brief.checklist.length > 0 && (
            <section className="brief-detail__card" aria-labelledby="brief-checklist">
              <h2 id="brief-checklist" className="brief-detail__sec-title">
                방문 전 확인
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
          )}
        </div>

        <aside className="brief-detail__rail">
          <section className="brief-detail__panel" aria-labelledby="brief-script">
            <div className="brief-detail__call-head">
              <h2 id="brief-script" className="brief-detail__panel-title">
                전화 화법
                {brief.generationStatus === 'LLM' && <span className="brief-detail__ai">AI 작성</span>}
                {brief.generationStatus === 'TEMPLATE' && (
                  <span className="brief-detail__ai is-template">기본 화법</span>
                )}
              </h2>
              {brief.scriptLines.length > 0 && (
                <button type="button" className="brief-detail__btn-line" onClick={copyScript}>
                  <Svg>{Icon.copy}</Svg>
                  화법 복사
                </button>
              )}
            </div>
            {brief.scriptLines.length > 0 ? (
              <>
                <p className="brief-detail__call-sub">
                  {brief.generationStatus === 'TEMPLATE'
                    ? '문장 생성 서비스가 연결되지 않아 기본 화법을 보여줍니다.'
                    : '통화 전에 내용을 한 번 확인하세요.'}
                </p>
                <ol className="brief-detail__steps">
                  {brief.scriptLines.map((line, index) => (
                    <li key={index}>
                      <span className="brief-detail__step-k">{labeled ? STEP_LABELS[index] : index + 1}</span>
                      <p>{line}</p>
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <p className="brief-detail__call-sub">
                근거가 확인되지 않은 문장이 검증 단계에서 차단되어 선정 사유만 표시합니다.
              </p>
            )}
            {copyNotice && (
              <p className="brief-detail__copy-notice" role="status">
                {copyNotice}
              </p>
            )}
          </section>

          <section className="brief-detail__panel" aria-labelledby="brief-tagging">
            <h2 id="brief-tagging" className="brief-detail__panel-title">
              접촉 결과
            </h2>
            <div className="brief-detail__result">
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
            </div>
            <p className="brief-detail__hint">기록은 내일 명부에 반영됩니다.</p>
          </section>
        </aside>
      </div>

      <p className="brief-detail__foot">
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <circle cx="8" cy="8" r="5.8" />
          <path d="M8 7.2v3.6M8 5.1v.01" />
        </svg>
        대상과 사유는 공공데이터를 기준으로 규칙이 정하고, 전화 화법은 AI가 작성합니다. 고객 개인정보는 다루지
        않습니다.
      </p>
    </div>
  );
}
