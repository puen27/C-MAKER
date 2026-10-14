import { chromium } from 'playwright';
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

const loginUrl = process.env.C_MAKER_BASE_URL;
const rmUser = process.env.C_MAKER_RM_USER;
const hqUser = process.env.C_MAKER_HQ_USER;
const password = process.env.C_MAKER_PASSWORD;

if (!loginUrl || !rmUser || !hqUser || !password) {
  throw new Error('C_MAKER_BASE_URL, C_MAKER_RM_USER, C_MAKER_HQ_USER, C_MAKER_PASSWORD 환경변수가 필요합니다.');
}

const timeline = JSON.parse(await readFile('content/timeline.json', 'utf8'));
const captions = new Map(timeline.segments.map((segment) => [segment.id, segment.text]));
const rawDir = path.resolve('artifacts', 'raw');
const downloadDir = path.resolve('artifacts', 'downloads');
await mkdir(rawDir, { recursive: true });
await mkdir(downloadDir, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
  ignoreHTTPSErrors: true,
  acceptDownloads: true,
  recordVideo: {
    dir: rawDir,
    size: { width: 1920, height: 1080 },
  },
});
const page = await context.newPage();
const video = page.video();
let recommendationId = null;
let rmToken = null;
let createdVisitedTag = false;
let downloadedFile = null;
const runtimeErrors = [];

page.on('pageerror', (error) => runtimeErrors.push(`page: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`);
});

function titleCard({ eyebrow, title, subtitle, points = [], caption = '' }) {
  const pointHtml = points.map((point) => `<div class="point"><span></span>${point}</div>`).join('');
  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;width:100vw;height:100vh;overflow:hidden;font-family:"Malgun Gothic","Noto Sans KR",sans-serif;background:linear-gradient(135deg,#f4f8fb 0%,#edf5f2 100%);color:#102a43}
.frame{height:100%;display:flex;align-items:center;justify-content:center;position:relative}.frame:before{content:"";position:absolute;left:0;top:0;right:0;height:8px;background:#0066b3}
.brand{position:absolute;left:72px;top:54px;display:flex;align-items:center;gap:16px;font-weight:700;font-size:25px}.mark{width:38px;height:38px;border:5px solid #0066b3;border-radius:9px;position:relative}.mark:after{content:"";position:absolute;width:10px;height:10px;border-radius:50%;background:#49a942;left:9px;top:9px}
.content{width:1500px;padding:90px 80px 160px}.eyebrow{font-size:26px;color:#0066b3;font-weight:700;letter-spacing:.04em;margin-bottom:24px}.title{font-size:70px;line-height:1.25;letter-spacing:-.04em;margin:0 0 28px}.subtitle{font-size:35px;color:#486581;line-height:1.55;margin:0}.points{display:flex;gap:24px;margin-top:50px}.point{background:white;border:1px solid #cbd8e5;border-radius:18px;padding:24px 32px;font-size:25px;box-shadow:0 10px 30px rgba(16,42,67,.08)}.point span{display:inline-block;width:10px;height:10px;background:#49a942;border-radius:50%;margin-right:12px}
.caption{position:fixed;z-index:999999;left:50%;bottom:28px;transform:translateX(-50%);width:min(1640px,calc(100vw - 120px));padding:18px 34px;border-radius:14px;background:rgba(6,31,54,.92);color:white;text-align:center;font-size:29px;font-weight:600;line-height:1.45;box-shadow:0 12px 35px rgba(0,0,0,.24)}
</style></head><body><div class="frame"><div class="brand"><span class="mark"></span>NH Campaigner</div><main class="content"><div class="eyebrow">${eyebrow}</div><h1 class="title">${title}</h1><p class="subtitle">${subtitle}</p><div class="points">${pointHtml}</div></main><div class="caption" id="demo-caption">${caption}</div></div></body></html>`;
}

async function installOverlay() {
  await page.evaluate(() => {
    let style = document.getElementById('demo-overlay-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'demo-overlay-style';
      style.textContent = `
        #demo-caption{position:fixed!important;z-index:2147483647!important;left:50%!important;bottom:26px!important;transform:translateX(-50%)!important;width:min(1640px,calc(100vw - 120px))!important;padding:17px 32px!important;border-radius:14px!important;background:rgba(6,31,54,.93)!important;color:#fff!important;text-align:center!important;font-family:"Malgun Gothic",sans-serif!important;font-size:28px!important;font-weight:600!important;line-height:1.45!important;letter-spacing:-.015em!important;box-shadow:0 12px 35px rgba(0,0,0,.24)!important;pointer-events:none!important}
        #demo-cursor{position:fixed!important;z-index:2147483647!important;width:26px!important;height:26px!important;border:4px solid #ffb000!important;border-radius:50%!important;background:rgba(255,255,255,.92)!important;box-shadow:0 2px 10px rgba(0,0,0,.4)!important;transform:translate(-50%,-50%)!important;transition:left .55s ease,top .55s ease!important;pointer-events:none!important}
        .demo-highlight{outline:4px solid #ffb000!important;outline-offset:5px!important;box-shadow:0 0 0 10px rgba(255,176,0,.16)!important;transition:outline .25s ease,box-shadow .25s ease!important}
      `;
      document.head.appendChild(style);
    }
    if (!document.getElementById('demo-caption')) {
      const caption = document.createElement('div');
      caption.id = 'demo-caption';
      document.body.appendChild(caption);
    }
    if (!document.getElementById('demo-cursor')) {
      const cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      cursor.style.left = '1660px';
      cursor.style.top = '120px';
      document.body.appendChild(cursor);
    }
  });
}

async function showCaption(id) {
  await installOverlay();
  await page.evaluate((text) => {
    document.getElementById('demo-caption').textContent = text;
  }, captions.get(id));
}

async function moveCursor(locator) {
  const target = locator.first();
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (!box) return;
  await installOverlay();
  await page.evaluate(({ x, y }) => {
    const cursor = document.getElementById('demo-cursor');
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  await page.waitForTimeout(650);
}

async function highlight(locator) {
  await page.evaluate(() => document.querySelectorAll('.demo-highlight').forEach((node) => node.classList.remove('demo-highlight')));
  const target = locator.first();
  await target.scrollIntoViewIfNeeded();
  await target.evaluate((node) => node.classList.add('demo-highlight'));
}

let startedAt;
const elapsed = () => (Date.now() - startedAt) / 1000;
async function sleepUntil(second) {
  const remaining = second - elapsed();
  if (remaining > 0) await page.waitForTimeout(remaining * 1000);
}

try {
  await page.setContent(titleCard({
    eyebrow: 'C-MAKER 3분 시연',
    title: '공공데이터를<br>오늘의 영업 기회로',
    subtitle: '설명 가능한 추천과 근거 있는 AI 화법으로<br>영업점의 다음 행동을 연결합니다.',
    points: ['개인 고객정보 비의존', '영업점별 오늘의 TOP 20', '1클릭 결과 기록'],
  }));
  startedAt = Date.now();
  await showCaption(1);

  await sleepUntil(12);
  await page.setContent(titleCard({
    eyebrow: '현장의 문제',
    title: '누구를, 왜 오늘<br>만나야 할까요?',
    subtitle: '늦은 명부와 설명하기 어려운 선정 근거를<br>매일 갱신되는 공공데이터 신호로 바꿉니다.',
    points: ['사업체 상태 확인', '변화 신호 감지', '접촉 근거 제공'],
  }));
  await showCaption(2);

  await sleepUntil(24);
  await page.goto(loginUrl, { waitUntil: 'networkidle', timeout: 30_000 });
  await showCaption(3);
  await moveCursor(page.getByLabel('아이디'));
  await page.getByLabel('아이디').fill(rmUser);
  await sleepUntil(28);
  await moveCursor(page.getByLabel('비밀번호'));
  await page.getByLabel('비밀번호').fill(password);
  await sleepUntil(31);
  await moveCursor(page.getByRole('button', { name: '로그인', exact: true }));
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForLoadState('networkidle');
  rmToken = await page.evaluate(() => sessionStorage.getItem('cmaker.token'));
  await showCaption(3);

  await sleepUntil(36);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await showCaption(4);
  await highlight(page.locator('.dashboard-page__hero'));

  await sleepUntil(49);
  await showCaption(5);
  const freshness = page.locator('.dashboard-page__basis');
  await highlight(freshness);
  await moveCursor(freshness);

  await sleepUntil(62);
  await showCaption(6);
  const signalHeading = page.getByText('신호별 대상', { exact: true });
  await highlight(signalHeading.locator('..'));
  await moveCursor(page.getByRole('button', { name: /환율 변동/ }));

  await sleepUntil(75);
  await showCaption(7);
  const openingSignal = page.locator('button').filter({ hasText: '신규 개업' }).first();
  await moveCursor(openingSignal);
  await openingSignal.click();
  await page.waitForTimeout(900);
  await highlight(page.getByText(/신규 개업만 보는 중/).locator('..'));

  await sleepUntil(87);
  await showCaption(8);
  const firstRecommendation = page.locator('a[href^="/brief/"]').first();
  const firstBusinessName = (await firstRecommendation.innerText()).trim();
  recommendationId = (await firstRecommendation.getAttribute('href'))?.split('/').pop() ?? null;
  await moveCursor(firstRecommendation);
  await firstRecommendation.click();
  await page.waitForLoadState('networkidle');
  await showCaption(8);
  await highlight(page.getByRole('heading', { name: firstBusinessName }).locator('..'));

  await sleepUntil(100);
  await showCaption(9);
  const coreEvidence = page.getByText('핵심 근거', { exact: true }).locator('..');
  await highlight(coreEvidence);
  await moveCursor(coreEvidence);

  await sleepUntil(113);
  await showCaption(10);
  const supportHeading = page.getByText('보조 근거', { exact: true });
  await supportHeading.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy({ top: 190, behavior: 'smooth' }));
  await page.waitForTimeout(900);
  await highlight(supportHeading.locator('..'));

  await sleepUntil(126);
  await showCaption(11);
  const productsHeading = page.getByText('추천상품', { exact: true });
  await productsHeading.scrollIntoViewIfNeeded();
  await page.waitForTimeout(700);
  await highlight(productsHeading.locator('..'));

  await sleepUntil(139);
  await showCaption(12);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await page.waitForTimeout(900);
  const copyButton = page.getByRole('button', { name: '화법 복사', exact: true });
  await highlight(copyButton.locator('..'));
  await moveCursor(copyButton);

  await sleepUntil(152);
  await showCaption(13);
  const visitedButton = page.getByRole('group', { name: '접촉 결과 태깅' }).getByRole('button', { name: '방문함' });
  const wasVisited = await visitedButton.getAttribute('aria-pressed') === 'true';
  if (!wasVisited) {
    await moveCursor(visitedButton);
    const responsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/recommendations/') && response.url().endsWith('/tag') && response.request().method() === 'POST',
    );
    await visitedButton.click();
    const response = await responsePromise;
    if (!response.ok()) throw new Error(`방문함 태깅 실패: HTTP ${response.status()}`);
    createdVisitedTag = true;
  }
  await page.waitForTimeout(900);
  const dashboardLink = page.getByRole('link', { name: '오늘의 접촉', exact: true }).first();
  await dashboardLink.click();
  await page.waitForLoadState('networkidle');
  await showCaption(13);
  const visitedTab = page.getByRole('tab', { name: /방문함/ });
  await moveCursor(visitedTab);
  await visitedTab.click();
  const crmButton = page.getByRole('button', { name: /CRM 등록 파일 받기/ });
  await moveCursor(crmButton);
  await crmButton.click();
  const csvItem = page.getByRole('menuitem', { name: 'CSV', exact: true });
  await moveCursor(csvItem);
  const downloadPromise = page.waitForEvent('download', { timeout: 10_000 });
  await csvItem.click();
  const download = await downloadPromise;
  downloadedFile = path.join(downloadDir, await download.suggestedFilename());
  await download.saveAs(downloadedFile);

  await sleepUntil(164);
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.waitForURL(/\/login/);
  await showCaption(14);
  await page.getByLabel('아이디').fill(hqUser);
  await page.getByLabel('비밀번호').fill(password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForLoadState('networkidle');
  await showCaption(14);
  await highlight(page.getByRole('heading', { name: '임계치 관리' }).locator('..'));
  const firstHistory = page.getByRole('button', { name: /변경 이력/ }).first();
  await moveCursor(firstHistory);
  await firstHistory.click();

  await sleepUntil(174);
  await page.setContent(titleCard({
    eyebrow: 'C-MAKER',
    title: '개인정보 없이<br>현장의 행동까지',
    subtitle: '공공데이터 기반 대상 선정 · 설명 가능한 근거 · AI 상담 화법',
    points: ['오늘의 TOP 20', '출처와 신선도', '결과 기록과 CRM 연결'],
    caption: captions.get(15),
  }));
  await showCaption(15);

  await sleepUntil(180);
} finally {
  await context.close();
  await browser.close();
}

const recordedPath = await video.path();
const targetPath = path.join(rawDir, 'c-maker-demo-raw.webm');
if (path.resolve(recordedPath) !== path.resolve(targetPath)) {
  await rm(targetPath, { force: true });
  await rename(recordedPath, targetPath);
}

let cleanup = { attempted: false, status: null };
if (createdVisitedTag && recommendationId && rmToken) {
  cleanup.attempted = true;
  const origin = new URL(loginUrl).origin;
  const response = await fetch(`${origin}/api/recommendations/${recommendationId}/tag`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${rmToken}` },
  });
  cleanup.status = response.status;
  if (!response.ok()) runtimeErrors.push(`cleanup: 방문 태그 원복 실패 HTTP ${response.status}`);
}

const report = {
  durationTargetSeconds: timeline.durationSeconds,
  rawVideo: targetPath,
  downloadedFile,
  recommendationId,
  createdVisitedTag,
  cleanup,
  runtimeErrors,
};
await writeFile(path.join(rawDir, 'record-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
if (runtimeErrors.length) process.exitCode = 1;
