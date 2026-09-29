// 본부(준법) 역할 안내 화면 — 캠페인 승인(UC-13)은 Phase 3 범위라 MVP에는 화면이 없다(CLAUDE.md §9).

import { Layout } from '../components/common/Layout';

export function PendingPage() {
  return (
    <Layout>
      <header className="page-header">
        <h1 className="page-title">안내</h1>
      </header>
      <p className="state-panel">
        본부(준법) 역할의 캠페인 승인 화면은 Phase 3에서 제공됩니다. 현재 단계(MVP)에서 이용할 수 있는 메뉴가 없습니다.
      </p>
    </Layout>
  );
}
