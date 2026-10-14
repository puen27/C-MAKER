import { chromium } from 'playwright';

const loginUrl = process.env.C_MAKER_BASE_URL;
const rmUser = process.env.C_MAKER_RM_USER;
const hqUser = process.env.C_MAKER_HQ_USER;
const password = process.env.C_MAKER_PASSWORD;
if (!loginUrl || !rmUser || !hqUser || !password) throw new Error('데모 환경변수가 필요합니다.');

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, acceptDownloads: true });
const page = await context.newPage();
const checks = [];

async function visible(name, locator) {
  await locator.first().waitFor({ state: 'visible', timeout: 15_000 });
  checks.push(name);
  return locator.first();
}

try {
  await page.goto(loginUrl, { waitUntil: 'networkidle' });
  await page.getByLabel('아이디').fill(rmUser);
  await page.getByLabel('비밀번호').fill(password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForLoadState('networkidle');

  await visible('dashboard hero', page.locator('.dashboard-page__hero'));
  await visible('freshness', page.locator('.dashboard-page__basis'));
  const opening = await visible('opening signal', page.locator('button').filter({ hasText: '신규 개업' }));
  await opening.click();
  await visible('active signal chip', page.getByText(/신규 개업만 보는 중/));

  const firstLink = await visible('recommendation link', page.locator('a[href^="/brief/"]'));
  const businessName = (await firstLink.innerText()).trim();
  await firstLink.click();
  await page.waitForLoadState('networkidle');
  await visible('business heading', page.getByRole('heading', { name: businessName }));
  await visible('core evidence', page.getByText('핵심 근거', { exact: true }));
  await visible('supporting evidence', page.getByText('보조 근거', { exact: true }));
  await visible('recommended products', page.getByText('추천상품', { exact: true }));
  await visible('copy script', page.getByRole('button', { name: '화법 복사', exact: true }));
  await visible('visited tag', page.getByRole('group', { name: '접촉 결과 태깅' }).getByRole('button', { name: '방문함' }));

  await page.getByRole('link', { name: '오늘의 접촉', exact: true }).first().click();
  await page.waitForLoadState('networkidle');
  await visible('visited tab', page.getByRole('tab', { name: /방문함/ }));
  const crm = await visible('CRM menu button', page.getByRole('button', { name: /CRM 등록 파일 받기/ }));
  await crm.click();
  await visible('CSV item', page.getByRole('menuitem', { name: 'CSV', exact: true }));
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.waitForURL(/\/login/);
  await page.getByLabel('아이디').fill(hqUser);
  await page.getByLabel('비밀번호').fill(password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForLoadState('networkidle');
  await visible('threshold heading', page.getByRole('heading', { name: '임계치 관리' }));
  await visible('history button', page.getByRole('button', { name: /변경 이력/ }));

  console.log(JSON.stringify({ ok: true, businessName, checks }, null, 2));
} finally {
  await context.close();
  await browser.close();
}
