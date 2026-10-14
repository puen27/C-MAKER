const loginUrl = process.env.C_MAKER_BASE_URL;
const username = process.env.C_MAKER_RM_USER;
const password = process.env.C_MAKER_PASSWORD;
const recommendationId = process.env.C_MAKER_RECOMMENDATION_ID;
if (!loginUrl || !username || !password || !recommendationId) throw new Error('정리 환경변수가 필요합니다.');

const origin = new URL(loginUrl).origin;
const loginResponse = await fetch(`${origin}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password }),
});
if (!loginResponse.ok) throw new Error(`로그인 실패: HTTP ${loginResponse.status}`);
const { token } = await loginResponse.json();
if (!token) throw new Error('로그인 응답에 토큰이 없습니다.');

const deleteResponse = await fetch(`${origin}/api/recommendations/${recommendationId}/tag`, {
  method: 'DELETE',
  headers: { Authorization: `Bearer ${token}` },
});
if (!deleteResponse.ok) throw new Error(`태그 원복 실패: HTTP ${deleteResponse.status}`);

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
const listResponse = await fetch(`${origin}/api/recommendations?date=${today}`, {
  headers: { Authorization: `Bearer ${token}` },
});
if (!listResponse.ok) throw new Error(`원복 확인 조회 실패: HTTP ${listResponse.status}`);
const recommendations = await listResponse.json();
const target = recommendations.find((item) => String(item.id) === String(recommendationId));
if (!target) throw new Error('원복 확인 대상 추천을 찾을 수 없습니다.');
if (target.tagStatus !== 'UNTAGGED') throw new Error(`원복 후 상태가 ${target.tagStatus}입니다.`);
console.log(JSON.stringify({ recommendationId, deleteStatus: deleteResponse.status, verifiedStatus: target.tagStatus }));
