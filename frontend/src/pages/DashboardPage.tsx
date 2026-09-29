// 오늘의 접촉 TOP 20 (NAME-F01) — docs/8-wireframe.md §3, UC-06
// 접근: RM, 지점장. 태깅·CRM 다운로드는 RM만(docs/10-implementation-guide.md §6.1).

import { useMemo } from 'react';
import { Layout } from '../components/common/Layout';
import { Banner } from '../components/common/Banner';
import { Tabs, type TabItem } from '../components/common/Tabs';
import { RecommendationList } from '../components/recommendation/RecommendationList';
import { CrmDownloadButton } from '../components/recommendation/CrmDownloadButton';
import { ListStatusStrip } from '../components/recommendation/ListStatusStrip';
import { TagUndoToast } from '../components/recommendation/TagUndoToast';
import { useAuthStore } from '../stores/authStore';
import { useFilterStore, type DashboardFilter } from '../stores/filterStore';
import { useRecommendations, useRecommendationSummary } from '../queries/useRecommendations';
import { useTagWithUndo } from '../queries/useTagWithUndo';
import { toUserMessage } from '../api/client';
import type { Recommendation, RejectedReason, TagStatus } from '../types/recommendation';
import { formatWeekdayKst, todayKst } from '../utils/date';
import { canExportCrm, canTag } from '../utils/roles';
import './DashboardPage.css';

const FILTER_ITEMS: { value: DashboardFilter; label: string }[] = [
  { value: 'ALL', label: '전체' },
  { value: 'UNTAGGED', label: '미태깅' },
  { value: 'VISITED', label: '방문함' },
  { value: 'HOLD', label: '보류' },
  { value: 'REJECTED', label: '부적합' },
];

export function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const branchId = user?.branchId ?? null;
  const today = todayKst();
  const weekday = formatWeekdayKst(today);
  const { data: recommendations = [], isLoading, isError, error } = useRecommendations(branchId, today);
  const { data: summary } = useRecommendationSummary(branchId, today);
  const dashboardFilter = useFilterStore((state) => state.dashboardFilter);
  const setDashboardFilter = useFilterStore((state) => state.setDashboardFilter);
  const tagging = useTagWithUndo();

  const userCanTag = user ? canTag(user.role) : false;

  const filteredRecommendations = useMemo(() => {
    if (dashboardFilter === 'ALL') return recommendations;
    return recommendations.filter((rec) => rec.tagStatus === dashboardFilter);
  }, [recommendations, dashboardFilter]);

  const tabItems: TabItem<DashboardFilter>[] = FILTER_ITEMS.map((item) => ({
    ...item,
    count:
      recommendations.length === 0
        ? undefined
        : item.value === 'ALL'
          ? recommendations.length
          : recommendations.filter((rec) => rec.tagStatus === item.value).length,
  }));

  function handleTag(rec: Recommendation, status: TagStatus, rejectedReason?: RejectedReason) {
    tagging.tag(
      { id: rec.id, businessName: rec.businessName, tagStatus: rec.tagStatus, rejectedReason: rec.rejectedReason },
      status,
      rejectedReason,
    );
  }

  return (
    <Layout>
      <div className="dashboard-page">
        <header className="dashboard-page__header">
          <div className="dashboard-page__title-row">
            <h1 className="page-title">
              오늘의 접촉
              <span className="dashboard-page__date">
                {today}
                {weekday && ` (${weekday})`}
              </span>
            </h1>
            {user && canExportCrm(user.role) && (
              <CrmDownloadButton date={today} disabled={recommendations.length === 0} />
            )}
          </div>
          {summary && summary.trimmedEventCount > 0 && (
            <p className="dashboard-page__note">
              오늘 감지된 이벤트 {summary.activeEventCount}건 외 {summary.trimmedEventCount}건
            </p>
          )}
          <ListStatusStrip recommendations={recommendations} />
        </header>

        {summary && summary.yesterdayUntaggedCount > 0 && (
          <Banner>⚠ 어제 미태깅 {summary.yesterdayUntaggedCount}건</Banner>
        )}
        {summary?.areaReasonRatioExceeded && (
          <Banner tone="info">
            오늘 명부의 {summary.areaReasonRatio}%가 상권 공통 사유만으로 선정되었습니다(기준{' '}
            {summary.areaReasonRatioLimit}% 초과).
          </Banner>
        )}

        <div className="dashboard-page__filter-row">
          <Tabs
            items={tabItems}
            activeValue={dashboardFilter}
            onChange={setDashboardFilter}
            label="태깅 상태로 보기"
          />
        </div>

        {isLoading && <p className="state-message">오늘의 명부를 불러오는 중…</p>}
        {isError && <p className="state-message state-message--error">{toUserMessage(error)}</p>}
        {!isLoading && !isError && (
          <RecommendationList
            recommendations={filteredRecommendations}
            canTag={userCanTag}
            tagDisabled={tagging.isPending}
            emptyMessage={
              recommendations.length === 0
                ? '오늘의 접촉 명부가 아직 생성되지 않았습니다. 일간 배치 완료 후 표시됩니다.'
                : '이 조건에 해당하는 항목이 없습니다.'
            }
            onTag={handleTag}
          />
        )}
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
