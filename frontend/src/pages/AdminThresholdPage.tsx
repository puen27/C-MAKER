// 임계치·운영 파라미터 관리 (NAME-F01) — docs/8-wireframe.md §6, UC-15
// 접근: 본부(마케팅)

import { Layout } from '../components/common/Layout';
import { ThresholdEditor } from '../components/admin/ThresholdEditor';
import { toUserMessage } from '../api/client';
import { useThresholds } from '../queries/useThresholds';

export function AdminThresholdPage() {
  const { data = [], isLoading, isError, error } = useThresholds();
  const signals = data.filter((item) => item.category === 'SIGNAL');
  const system = data.filter((item) => item.category === 'SYSTEM');

  return (
    <Layout>
      <header className="page-header">
        <h1 className="page-title">임계치 관리</h1>
        <p className="page-description">
          변경 즉시 저장되며 다음 일간 배치부터 적용됩니다. 모든 변경은 수정 계정·일시·이전값과 함께 이력으로 남습니다.
        </p>
      </header>
      {isLoading && <p className="state-message">임계치를 불러오는 중…</p>}
      {isError && <p className="state-message state-message--error">{toUserMessage(error)}</p>}
      {!isLoading && !isError && (
        <>
          <ThresholdEditor title="신호 승격 임계치" thresholds={signals} />
          <ThresholdEditor title="운영 파라미터" thresholds={system} />
        </>
      )}
    </Layout>
  );
}
