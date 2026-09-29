// TanStack Query 훅 — CRM 등록 파일 다운로드 (UC-08)
// 컴포넌트가 API 클라이언트를 직접 호출하지 않도록 mutation으로 감싼다(4-project-principle.md §2).

import { useMutation } from '@tanstack/react-query';
import { downloadCrmFile } from '../api/recommendation.api';
import type { CrmFileFormat } from '../types/recommendation';

export function useCrmExport() {
  return useMutation({
    mutationFn: ({ date, format }: { date: string; format: CrmFileFormat }) => downloadCrmFile(date, format),
  });
}
