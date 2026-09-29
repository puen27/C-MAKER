// CRM 등록 파일 다운로드 (NAME-F01) — UC-08, REQ-07
// CSV/XLSX 중 선택해 내려받는다. 파일에는 공개 데이터 기반 사업체 정보만 담긴다(RULE-SEC-01).

import { useEffect, useRef, useState } from 'react';
import { Button } from '../common/Button';
import { toUserMessage } from '../../api/client';
import { useCrmExport } from '../../queries/useCrmExport';
import type { CrmFileFormat } from '../../types/recommendation';
import './TagButtons.css';

interface CrmDownloadButtonProps {
  date: string;
  disabled?: boolean;
}

const FORMATS: { value: CrmFileFormat; label: string }[] = [
  { value: 'csv', label: 'CSV' },
  { value: 'xlsx', label: 'Excel (XLSX)' },
];

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function CrmDownloadButton({ date, disabled }: CrmDownloadButtonProps) {
  const [open, setOpen] = useState(false);
  const exportMutation = useCrmExport();
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointer(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  function download(format: CrmFileFormat) {
    setOpen(false);
    exportMutation.mutate(
      { date, format },
      { onSuccess: ({ blob, filename }) => saveBlob(blob, filename) },
    );
  }

  const pending = exportMutation.isPending;
  const error = exportMutation.isError ? toUserMessage(exportMutation.error) : null;

  return (
    <div className="tag-buttons__rejected-wrap" ref={wrapRef}>
      <Button
        variant="outline-pill"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled || pending}
        onClick={() => setOpen((prev) => !prev)}
      >
        {pending ? (
          '파일 생성 중…'
        ) : (
          <>
            CRM 파일 다운로드
            <span className="btn__caret" aria-hidden="true">
              ▾
            </span>
          </>
        )}
      </Button>
      {open && (
        <div className="tag-buttons__dropdown crm-download__menu" role="menu" aria-label="파일 형식">
          {FORMATS.map((format) => (
            <button
              key={format.value}
              type="button"
              role="menuitem"
              className="tag-buttons__dropdown-item"
              onClick={() => download(format.value)}
            >
              {format.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p className="crm-download__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
