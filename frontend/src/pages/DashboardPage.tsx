// 오늘의 접촉 TOP 20 (NAME-F01) — docs/8-wireframe.md §3, UC-06
import { useMemo } from 'react';
import { Layout } from '../components/common/Layout';
import { Tabs, type TabItem } from '../components/common/Tabs';
import { RecommendationList } from '../components/recommendation/RecommendationList';
import { Button } from '../components/common/Button';
import { useAuthStore } from '../stores/authStore';
import { useFilterStore, type DashboardFilter } from '../stores/filterStore';
import { useRecommendations } from '../queries/useRecommendations';
import { useTagMutation } from '../queries/useTagMutation';
import { MOCK_TODAY } from '../api/mockData';
import { toUserMessage } from '../api/client';
import type { RejectedReason, TagStatus } from '../types/recommendation';
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
  const branchId = user?.branchId ?? '';
  const { data: recommendations = [], isLoading, isError, error } = useRecommendations(
    branchId,
    MOCK_TODAY,
  );
  const dashboardFilter = useFilterStore((state) => state.dashboardFilter);
  const setDashboardFilter = useFilterStore((state) => state.setDashboardFilter);
  const tagMutation = useTagMutation();

  const untaggedCount = useMemo(
    () => recommendations.filter((rec) => rec.tagStatus === 'UNTAGGED').length,
    [recommendations],
  );

  const carriedOverUntaggedCount = useMemo(
    () =>
      recommendations.filter((rec) => rec.carriedOverFromYesterday && rec.tagStatus === 'UNTAGGED')
        .length,
    [recommendations],
  );

  const filteredRecommendations = useMemo(() => {
    if (dashboardFilter === 'ALL') return recommendations;
    return recommendations.filter((rec) => rec.tagStatus === dashboardFilter);
  }, [recommendations, dashboardFilter]);

  const tabItems: TabItem<DashboardFilter>[] = FILTER_ITEMS.map((item) => ({
    ...item,
  }));

  function handleTag(id: string, tagStatus: TagStatus, rejectedReason?: RejectedReason) {
    tagMutation.mutate({ recommendationId: id, tagStatus, rejectedReason });
  }

  function handleCrmDownload() {
    // CRM 다운로드 버튼은 자리만 마련한다 (REQ-07 실제 파일 생성은 백엔드 준비 후 연동).
    window.alert('CRM 등록 파일 다운로드는 준비 중입니다.');
  }

  return (
    <Layout>
      <div className="dashboard-page">
        <div className="dashboard-page__header">
          <h1 className="dashboard-page__title">오늘의 접촉 ({MOCK_TODAY})</h1>
          <Button variant="outline-pill" onClick={handleCrmDownload}>
            CRM 파일 다운로드
          </Button>
        </div>

        {carriedOverUntaggedCount > 0 && (
          <div className="dashboard-page__banner">
            ⚠ 어제 미태깅 {carriedOverUntaggedCount}건
          </div>
        )}

        <div className="dashboard-page__filter-row">
          <Tabs items={tabItems} activeValue={dashboardFilter} onChange={setDashboardFilter} />
          <span className="dashboard-page__filter-summary">
            {recommendations.length}건 중 {untaggedCount}건 미태깅
          </span>
        </div>

        {isLoading && <p>불러오는 중…</p>}
        {isError && <p className="dashboard-page__error">{toUserMessage(error)}</p>}
        {!isLoading && !isError && (
          <RecommendationList recommendations={filteredRecommendations} onTag={handleTag} />
        )}
      </div>
    </Layout>
  );
}
