// NH Campaigner 공식 시그니처 — NH-Campaigner-UI-proposal.html 변경 포인트 1
// 심볼 + 'NH Campaigner' 워드마크가 하나로 묶인 원본(public/brand/nh-campaigner.svg)을 변형 없이 쓴다.
// 워드마크가 시그니처에 들어 있으므로 옆에 서비스명을 글자로 다시 쓰지 않는다.
// 파일을 못 불러오면 서비스명을 글자로 대신 보여준다.

import { useState } from 'react';
import './BrandSignature.css';

const SIGNATURE_SRC = '/brand/nh-campaigner.svg';
const SIGNATURE_ALT = 'NH Campaigner';

interface BrandSignatureProps {
  size?: 'md' | 'lg';
}

export function BrandSignature({ size = 'md' }: BrandSignatureProps) {
  const [missing, setMissing] = useState(false);

  if (missing) {
    return (
      <span className={`brand-signature brand-signature--${size} brand-signature--fallback`}>
        {SIGNATURE_ALT}
      </span>
    );
  }
  return (
    <img
      className={`brand-signature brand-signature--${size}`}
      src={SIGNATURE_SRC}
      alt={SIGNATURE_ALT}
      onError={() => setMissing(true)}
    />
  );
}
