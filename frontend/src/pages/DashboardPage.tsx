// 오늘의 접촉 TOP 20 (NAME-F01) — docs/8-wireframe.md §3, UC-06
// 접근: RM, 지점장. 태깅·CRM 다운로드는 RM만(docs/10-implementation-guide.md §6.1).
// NH-Campaigner-UI-proposal.html 반영:
//   P0 — 데이터 기준 도장(3), 오늘 기록 패널(4), 기록 상태 탭·파일 받기 버튼 위치(6), 기록 버튼 색(8), 투명성 문구(9)
//   P1 — 아침 브리핑 문장(2), 신호별 대상 막대(5), 한 줄 명부 행(7)

import { useMemo } from 'react';
import { Layout } from '../components/common/Layout';
import { Banner } from '../components/common/Banner';
import { DataFreshnessStamps } from '../components/common/DataFreshnessStamps';
import { Tabs, type TabItem } from '../components/common/Tabs';
import { RecommendationList } from '../components/recommendation/RecommendationList';
import { CrmDownloadButton } from '../components/recommendation/CrmDownloadButton';
import { SignalBarsPanel } from '../components/recommendation/SignalBarsPanel';
import { TodayRecordPanel } from '../components/recommendation/TodayRecordPanel';
import { TagUndoToast } from '../components/recommendation/TagUndoToast';
import { useAuthStore } from '../stores/authStore';
import { useFilterStore, type DashboardFilter } from '../stores/filterStore';
import { useRecommendations, useRecommendationSummary } from '../queries/useRecommendations';
import { useTagWithUndo } from '../queries/useTagWithUndo';
import { toUserMessage } from '../api/client';
import type { Recommendation, RejectedReason, TagStatus } from '../types/recommendation';
import { formatWeekdayKst, todayKst } from '../utils/date';
import { canExportCrm, canTag } from '../utils/roles';
import { groupBySignal, NO_SIGNAL_KEY, signalKeyOf, signalLabel } from '../utils/signal';
import './DashboardPage.css';

const FILTER_ITEMS: { value: DashboardFilter; label: string }[] = [
  { value: 'ALL', label: '전체' },
  { value: 'UNTAGGED', label: '기록 전' },
  { value: 'VISITED', label: '방문함' },
  { value: 'HOLD', label: '보류' },
  { value: 'REJECTED', label: '부적합' },
];

/** YYYY-MM-DD → "10월 12일 월요일" */
function formatHeroDate(date: string, weekday: string): string {
  const [, month, day] = date.split('-');
  if (!month || !day) return date;
  return `${Number(month)}월 ${Number(day)}일${weekday ? ` ${weekday}요일` : ''}`;
}

export function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const branchId = user?.branchId ?? null;
  const today = todayKst();
  const weekday = formatWeekdayKst(today);
  const { data: recommendations = [], isLoading, isError, error } = useRecommendations(branchId, today);
  const { data: summary } = useRecommendationSummary(branchId, today);
  const dashboardFilter = useFilterStore((state) => state.dashboardFilter);
  const setDashboardFilter = useFilterStore((state) => state.setDashboardFilter);
  const signalFilter = useFilterStore((state) => state.signalFilter);
  const setSignalFilter = useFilterStore((state) => state.setSignalFilter);
  const tagging = useTagWithUndo();

  const userCanTag = user ? canTag(user.role) : false;
  const signalGroups = useMemo(() => groupBySignal(recommendations), [recommendations]);

  const filteredRecommendations = useMemo(
    () =>
      recommendations.filter(
        (rec) =>
          (dashboardFilter === 'ALL' || rec.tagStatus === dashboardFilter) &&
          (!signalFilter || signalKeyOf(rec) === signalFilter),
      ),
    [recommendations, dashboardFilter, signalFilter],
  );

  const tabItems: TabItem<DashboardFilter>[] = FILTER_ITEMS.map((item) => ({
    ...item,
    count:
      recommendations.length === 0
        ? undefined
        : item.value === 'ALL'
          ? recommendations.length
          : recommendations.filter((rec) => rec.tagStatus === item.value).length,
  }));

  // 아침 브리핑 문장(변경 포인트 2): "오늘 만날 {전체 수}곳을 선정했습니다." "{1순위 신호} {그 신호 수}곳이 먼저입니다."
  // 1순위 추천의 대표 신호명을 쓴다. 기여 신호 없이 선정된 묶음이 맨 앞이면 둘째 줄은 생략한다.
  const topGroup = signalGroups[0];
  const headline =
    recommendations.length > 0 ? `오늘 만날 ${recommendations.length}곳을 선정했습니다` : '오늘의 접촉';
  const lede =
    topGroup && signalGroups.length > 1 && topGroup.key !== NO_SIGNAL_KEY
      ? `${topGroup.label} ${topGroup.count}곳이 먼저입니다.`
      : null;

  function handleTag(rec: Recommendation, status: TagStatus, rejectedReason?: RejectedReason) {
    tagging.tag(
      { id: rec.id, businessName: rec.businessName, tagStatus: rec.tagStatus, rejectedReason: rec.rejectedReason },
      status,
      rejectedReason,
    );
  }

  return (
    <Layout showDataDelayBanner={false}>
      <div className="dashboard-page">
        <div className="dashboard-page__band">
          <header className="dashboard-page__hero">
            <p className="dashboard-page__date">
              <time dateTime={today}>{formatHeroDate(today, weekday)}</time>
            </p>
            <h1 className="dashboard-page__headline">{headline}</h1>
            {lede && <p className="dashboard-page__lede">{lede}</p>}
            {summary && summary.trimmedEventCount > 0 && (
              <p className="dashboard-page__note">
                오늘 감지된 이벤트 {summary.activeEventCount}건 외 {summary.trimmedEventCount}건
              </p>
            )}
            <div className="dashboard-page__basis">
              <DataFreshnessStamps />
            </div>
          </header>
          {recommendations.length > 0 && (
            <>
              <TodayRecordPanel
                recommendations={recommendations}
                yesterdayUntaggedCount={summary?.yesterdayUntaggedCount ?? 0}
              />
              <SignalBarsPanel groups={signalGroups} active={signalFilter} onSelect={setSignalFilter} />
            </>
          )}
        </div>

        {/* 오늘 명부가 없으면 TodayRecordPanel이 숨겨지므로 어제 미기록 안내(UC-09)를 따로 보여준다 */}
        {recommendations.length === 0 && (summary?.yesterdayUntaggedCount ?? 0) > 0 && (
          <Banner tone="info">어제 명부에서 기록하지 않은 곳이 {summary?.yesterdayUntaggedCount}곳 있습니다.</Banner>
        )}

        {summary?.areaReasonRatioExceeded && (
          <Banner tone="info">
            오늘 명부의 {summary.areaReasonRatio}%가 상권 공통 사유만으로 선정되었습니다(기준{' '}
            {summary.areaReasonRatioLimit}% 초과).
          </Banner>
        )}

        <section className="dashboard-page__sheet" aria-label="오늘의 접촉 명부">
          <div className="dashboard-page__filter-row">
            <Tabs
              items={tabItems}
              activeValue={dashboardFilter}
              onChange={setDashboardFilter}
              label="기록 상태로 보기"
            />
            <div className="dashboard-page__tools">
              {signalFilter && (
                <span className="dashboard-page__chip">
                  {signalLabel(signalFilter)}만 보는 중
                  <button type="button" aria-label="신호 필터 해제" onClick={() => setSignalFilter(null)}>
                    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                      <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
                    </svg>
                  </button>
                </span>
              )}
              {user && canExportCrm(user.role) && (
                <CrmDownloadButton date={today} disabled={recommendations.length === 0} />
              )}
            </div>
          </div>

          {isLoading && <p className="state-message dashboard-page__state">오늘의 명부를 불러오는 중…</p>}
          {isError && (
            <p className="state-message state-message--error dashboard-page__state">{toUserMessage(error)}</p>
          )}
          {!isLoading && !isError && (
            <RecommendationList
              recommendations={filteredRecommendations}
              canTag={userCanTag}
              tagDisabled={tagging.isPending}
              emptyMessage={
                recommendations.length === 0
                  ? '오늘의 접촉 명부가 아직 생성되지 않았습니다. 일간 배치 완료 후 표시됩니다.'
                  : '이 조건에 맞는 사업장이 없습니다.'
              }
              onTag={handleTag}
            />
          )}
        </section>

        <p className="dashboard-page__foot">
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <circle cx="8" cy="8" r="5.8" />
            <path d="M8 7.2v3.6M8 5.1v.01" />
          </svg>
          대상과 사유는 공공데이터를 기준으로 규칙이 정하고, 전화 화법은 AI가 작성합니다. 고객 개인정보는 다루지
          않습니다.
        </p>
      </div>
      <TagUndoToast
        lastChange={tagging.lastChange}
        error={tagging.error}
        pending={tagging.isPending}
        onUndo={tagging.undo}
        onDismiss={tagging.dismiss}
      />
    </Layout>
  );
}
