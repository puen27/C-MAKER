// 농협 공식 시그니처 자리 — NH-Campaigner-UI-proposal.html 변경 포인트 1
// 로고는 CI 매뉴얼 원본 파일을 변형 없이 그대로 쓴다. public/brand/nh-signature.svg 에 원본을 넣으면 표시되고,
// 파일이 없으면 자리 표시(점선 상자)만 보인다. 서비스명은 이 옆에 글자로 따로 둔다(로고와 합치지 않음).

import { useState } from 'react';
import './BrandSignature.css';

const SIGNATURE_SRC = '/brand/nh-signature.svg';

interface BrandSignatureProps {
  size?: 'md' | 'lg';
}

export function BrandSignature({ size = 'md' }: BrandSignatureProps) {
  const [missing, setMissing] = useState(false);

  if (missing) {
    return (
      <span className={`brand-signature brand-signature--${size} brand-signature--slot`} aria-hidden="true">
        공식 시그니처 자리
      </span>
    );
  }
  return (
    <img
      className={`brand-signature brand-signature--${size}`}
      src={SIGNATURE_SRC}
      alt="NH농협은행"
      onError={() => setMissing(true)}
    />
  );
}
