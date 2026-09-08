// 상담 브리프 상세 (NAME-F01) — docs/8-wireframe.md §4, UC-07
import { useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { BriefDetail } from '../components/brief/BriefDetail';
import { useBrief } from '../queries/useBrief';
import { useTagMutation } from '../queries/useTagMutation';
import { toUserMessage } from '../api/client';
import type { RejectedReason, TagStatus } from '../types/recommendation';

export function BriefDetailPage() {
  const { id } = useParams<{ id: string }>();
  const recommendationId = id ?? '';
  const { data: brief, isLoading, isError, error } = useBrief(recommendationId);
  const tagMutation = useTagMutation();

  function handleTag(status: TagStatus, rejectedReason?: RejectedReason) {
    tagMutation.mutate({ recommendationId, tagStatus: status, rejectedReason });
  }

  return (
    <Layout>
      {isLoading && <p>불러오는 중…</p>}
      {isError && <p style={{ color: 'var(--color-danger)' }}>{toUserMessage(error)}</p>}
      {brief && (
        <BriefDetail brief={brief} onTag={handleTag} tagPending={tagMutation.isPending} />
      )}
    </Layout>
  );
}
