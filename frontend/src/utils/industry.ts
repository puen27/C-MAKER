// 업종명 표시 — 원본은 대·중·소분류를 '·'로 이어 붙인 값이라 화면에는 마지막 단계만 보여준다.
// 예: '시설관리·임대·여행사·보조·여행사' → '여행사' (NH Campaigner 수정 요청 10/13 ①)

export function industryLeaf(industry: string | null | undefined): string {
  const parts = (industry ?? '')
    .split('·')
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : (industry ?? '');
}
