// 백엔드 API 준비 전까지 사용하는 in-memory mock 데이터 저장소.
//
// ⚠ 실제 API 연동 지점: 백엔드가 준비되면 이 파일 전체를 제거하고,
// api/recommendation.api.ts / api/brief.api.ts / api/tag.api.ts / api/auth.api.ts에서
// apiFetch()로 실제 엔드포인트를 호출하도록 교체한다.
//
// 개인 고객정보를 담지 않는다 — 상호명은 전부 공개 데이터 성격의 placeholder이며
// 실제 사업자와 무관한 가상의 예시명이다.

import type { Recommendation } from '../types/recommendation';
import type { Brief } from '../types/brief';
import type { AuthUser } from '../types/auth';

export const MOCK_BRANCH: { id: string; name: string } = {
  id: 'branch-001',
  name: '강남중앙지점',
};

export const MOCK_TODAY = '2026-08-26';

interface RecommendationSeed {
  businessName: string;
  industry: string;
  score: number;
  reasonSummary: string;
  reasonSourceTag: string;
  isExplorationSlot?: boolean;
  carriedOverFromYesterday?: boolean;
}

// 20건 시드 데이터 (docs/8-wireframe.md §3 예시 형식을 따름). 탐색 슬롯 3건 포함(RULE-TARGET-03).
const SEEDS: RecommendationSeed[] = [
  { businessName: '○○떡볶이', industry: '요식업', score: 92, reasonSummary: '인근 상권 신규 개업 3건 감지', reasonSourceTag: '지방행정인허가·2026-08-25' },
  { businessName: '△△세탁소', industry: '세탁업', score: 88, reasonSummary: '유동인구 12% 증가', reasonSourceTag: '지하철승하차·2026-08-24', carriedOverFromYesterday: true },
  { businessName: '□□마트', industry: '소매업', score: 85, reasonSummary: '인근 상권 신규 개업 2건 감지', reasonSourceTag: '지방행정인허가·2026-08-25' },
  { businessName: '◇◇미용실', industry: '미용업', score: 83, reasonSummary: '업종 평균 대비 유동인구 8% 증가', reasonSourceTag: '지하철승하차·2026-08-24' },
  { businessName: '☆☆편의점', industry: '편의점업', score: 81, reasonSummary: '폭염특보 발효로 냉방·음료 수요 증가 예상', reasonSourceTag: '기상청특보·2026-08-26' },
  { businessName: '◎◎카페', industry: '카페업', score: 79, reasonSummary: '인근 상권 신규 개업 2건 감지', reasonSourceTag: '지방행정인허가·2026-08-24', carriedOverFromYesterday: true },
  { businessName: '▽▽어학원', industry: '학원업', score: 77, reasonSummary: '업종 평균 대비 신규 개업 밀도 높음', reasonSourceTag: '지방행정인허가·2026-08-23' },
  { businessName: '◁◁공인중개사', industry: '부동산중개업', score: 75, reasonSummary: '상권 내 신규 개업 활력 상승', reasonSourceTag: '지방행정인허가·2026-08-25' },
  { businessName: '▷▷정비소', industry: '자동차정비업', score: 73, reasonSummary: '유가 변동으로 정비 수요 변화 예상', reasonSourceTag: 'ECOS·2026-08-25' },
  { businessName: '◆◆약국', industry: '약국업', score: 71, reasonSummary: '폭염특보 발효로 방문객 증가 예상', reasonSourceTag: '기상청특보·2026-08-26' },
  { businessName: '◈◈빨래방', industry: '세탁업', score: 69, reasonSummary: '업종 평균 대비 유동인구 증가', reasonSourceTag: '지하철승하차·2026-08-24' },
  { businessName: '★★분식', industry: '요식업', score: 67, reasonSummary: '인근 상권 신규 개업 1건 감지', reasonSourceTag: '지방행정인허가·2026-08-25' },
  { businessName: '✪✪네일샵', industry: '미용업', score: 65, reasonSummary: '업종 평균 대비 유동인구 증가', reasonSourceTag: '지하철승하차·2026-08-23' },
  { businessName: '❖❖문구점', industry: '소매업', score: 63, reasonSummary: '인근 상권 신규 개업 1건 감지', reasonSourceTag: '지방행정인허가·2026-08-24', carriedOverFromYesterday: true },
  { businessName: '❈❈베이커리', industry: '요식업', score: 61, reasonSummary: '상권 활력 지수 상승', reasonSourceTag: '지방행정인허가·2026-08-22', isExplorationSlot: true },
  { businessName: '❉❉헬스장', industry: '스포츠업', score: 58, reasonSummary: '상권 활력 지수 상승', reasonSourceTag: '지방행정인허가·2026-08-21', isExplorationSlot: true },
  { businessName: '❂❂꽃집', industry: '소매업', score: 55, reasonSummary: '상권 활력 지수 상승', reasonSourceTag: '지방행정인허가·2026-08-20', isExplorationSlot: true },
  { businessName: '❁❁철물점', industry: '소매업', score: 52, reasonSummary: '업종 평균 대비 신규 개업 밀도 높음', reasonSourceTag: '지방행정인허가·2026-08-19' },
  { businessName: '✿✿한식당', industry: '요식업', score: 49, reasonSummary: '유동인구 소폭 증가', reasonSourceTag: '지하철승하차·2026-08-22' },
  { businessName: '❀❀서점', industry: '소매업', score: 46, reasonSummary: '인근 상권 신규 개업 1건 감지', reasonSourceTag: '지방행정인허가·2026-08-18' },
];

function buildScript(businessName: string): string[] {
  return [
    `안녕하세요, ○○은행 ${MOCK_BRANCH.name}입니다.`,
    `최근 ${businessName} 인근 상권에 변화가 감지되어 안내드리고자 연락드렸습니다.`,
    '잠시 방문드려 필요하신 부분을 확인해도 괜찮을까요?',
  ];
}

function buildChecklist(): string[] {
  return ['사업자등록증 확인', '현재 거래 은행 확인', '카드단말기 사용 현황 확인'];
}

let recommendationsSeed: Recommendation[] | null = null;

/** in-memory mock "서버" 상태를 초기화하거나 이미 있으면 그대로 반환한다. */
function getRecommendationsStore(): Recommendation[] {
  if (!recommendationsSeed) {
    recommendationsSeed = SEEDS.map((seed, index) => ({
      id: `rec-${index + 1}`,
      branchId: MOCK_BRANCH.id,
      rank: index + 1,
      businessName: seed.businessName,
      industry: seed.industry,
      score: seed.score,
      reasonSummary: seed.reasonSummary,
      reasonSourceTag: seed.reasonSourceTag,
      tagStatus: 'UNTAGGED',
      carriedOverFromYesterday: seed.carriedOverFromYesterday ?? false,
      isExplorationSlot: seed.isExplorationSlot ?? false,
    }));
  }
  return recommendationsSeed;
}

export function mockFetchRecommendations(): Recommendation[] {
  return getRecommendationsStore().map((rec) => ({ ...rec }));
}

export function mockFetchRecommendationById(id: string): Recommendation | undefined {
  return getRecommendationsStore().find((rec) => rec.id === id);
}

export function mockUpdateTag(
  id: string,
  tagStatus: Recommendation['tagStatus'],
  rejectedReason?: Recommendation['rejectedReason'],
): Recommendation {
  const store = getRecommendationsStore();
  const target = store.find((rec) => rec.id === id);
  if (!target) {
    throw new Error(`추천 항목을 찾을 수 없습니다: ${id}`);
  }
  target.tagStatus = tagStatus;
  target.rejectedReason = tagStatus === 'REJECTED' ? rejectedReason : undefined;
  target.carriedOverFromYesterday = false;
  return { ...target };
}

export function mockFetchBrief(recommendationId: string): Brief {
  const rec = mockFetchRecommendationById(recommendationId);
  if (!rec) {
    throw new Error(`추천 항목을 찾을 수 없습니다: ${recommendationId}`);
  }
  return {
    recommendationId: rec.id,
    businessName: rec.businessName,
    industry: rec.industry,
    distanceLabel: '인근 상권 5분 거리',
    reasonFacts: [
      { text: rec.reasonSummary, sourceTag: rec.reasonSourceTag },
    ],
    scriptLines: buildScript(rec.businessName),
    checklist: buildChecklist(),
    tagStatus: rec.tagStatus,
    rejectedReason: rec.rejectedReason,
  };
}

export function mockLogin(username: string, password: string): { token: string; user: AuthUser } {
  if (!username.trim() || !password.trim()) {
    throw new Error('아이디와 비밀번호를 입력해주세요.');
  }
  return {
    token: `mock-token-${username}-${Date.now()}`,
    user: {
      id: `user-${username}`,
      name: '한서영',
      role: 'RM',
      branchId: MOCK_BRANCH.id,
      branchName: MOCK_BRANCH.name,
    },
  };
}
