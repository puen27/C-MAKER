// 상담 브리프 상세 (NAME-F01) — docs/8-wireframe.md §4, UC-07
import { useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { BriefDetail } from '../components/brief/BriefDetail';
import { TagUndoToast } from '../components/recommendation/TagUndoToast';
import { useBrief } from '../queries/useBrief';
import { useTagWithUndo } from '../queries/useTagWithUndo';
import { useAuthStore } from '../stores/authStore';
import { toUserMessage } from '../api/client';
import type { RejectedReason, TagStatus } from '../types/recommendation';
import { canTag } from '../utils/roles';

export function BriefDetailPage() {
  const { id } = useParams<{ id: string }>();
  const recommendationId = Number(id);
  const user = useAuthStore((state) => state.user);
  const { data: brief, isLoading, isError, error } = useBrief(recommendationId);
  const tagging = useTagWithUndo();

  function handleTag(status: TagStatus, rejectedReason?: RejectedReason) {
    if (!brief) return;
    tagging.tag(
      {
        id: brief.recommendationId,
        businessName: brief.businessName,
        tagStatus: brief.tagStatus,
        rejectedReason: brief.rejectedReason,
      },
      status,
      rejectedReason,
    );
  }

  return (
    <Layout>
      {isLoading && <p className="state-message">브리프를 불러오는 중…</p>}
      {isError && <p className="state-message state-message--error">{toUserMessage(error)}</p>}
      {brief && (
        <BriefDetail
          brief={brief}
          canTag={user ? canTag(user.role) : false}
          onTag={handleTag}
          tagPending={tagging.isPending}
        />
      )}
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
