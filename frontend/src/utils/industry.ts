// 업종명 표시 — 원본은 대·중·소분류를 '·'로 이어 붙인 값이라 화면에는 마지막 단계만 보여준다.
// 예: '시설관리·임대·여행사·보조·여행사' → '여행사' (NH Campaigner 수정 요청 10/13 ①)
// 마지막 단계가 '백화점'이면 앞 단계와 합친다: '…·휴게음식점·백화점' → '휴게음식점(백화점 내)' (10/14 테스트 결과 8번)
// 배치 근거 문장(fact_builder.py _industry_leaf)과 같은 규칙이다.

const IN_STORE_LEAVES = new Set(['백화점']);

export function industryLeaf(industry: string | null | undefined): string {
  const parts = (industry ?? '')
    .split('·')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return industry ?? '';
  const leaf = parts[parts.length - 1];
  if (IN_STORE_LEAVES.has(leaf) && parts.length >= 2) {
    return `${parts[parts.length - 2]}(${leaf} 내)`;
  }
  return leaf;
}
