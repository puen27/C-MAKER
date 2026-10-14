import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.C_MAKER_BASE_URL;
const password = process.env.C_MAKER_PASSWORD;
const users = (process.env.C_MAKER_INSPECT_USERS ?? '')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

if (!baseUrl || !password || users.length === 0) {
  throw new Error('C_MAKER_BASE_URL, C_MAKER_PASSWORD, C_MAKER_INSPECT_USERS 환경변수가 필요합니다.');
}

const artifactDir = path.resolve('artifacts', 'inspection');
await mkdir(artifactDir, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const report = { inspectedAt: new Date().toISOString(), baseUrl, users: [] };

try {
  for (const username of users) {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1,
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();
    const errors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(`console: ${message.text()}`);
    });
    page.on('pageerror', (error) => errors.push(`page: ${error.message}`));

    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30_000 });
    await page.getByLabel('아이디').fill(username);
    await page.getByLabel('비밀번호').fill(password);
    await page.getByRole('button', { name: '로그인', exact: true }).click();
    await page.waitForLoadState('networkidle');

    const safeName = username.replace(/[^a-zA-Z0-9_-]/g, '_');
    await page.screenshot({ path: path.join(artifactDir, `${safeName}-landing.png`), fullPage: true });

    const entry = {
      username,
      landingUrl: page.url(),
      title: await page.title(),
      bodyText: (await page.locator('body').innerText()).slice(0, 15_000),
      buttons: await page.getByRole('button').allTextContents(),
      links: await page.getByRole('link').allTextContents(),
      errors,
    };

    if (username.startsWith('rm')) {
      const recommendationLinks = page.locator('a[href^="/brief/"]');
      entry.recommendationCount = await recommendationLinks.count();
      if (entry.recommendationCount > 0) {
        await recommendationLinks.first().click();
        await page.waitForLoadState('networkidle');
        entry.firstBriefUrl = page.url();
        entry.firstBriefText = (await page.locator('body').innerText()).slice(0, 15_000);
        entry.briefButtons = await page.getByRole('button').allTextContents();
        await page.screenshot({ path: path.join(artifactDir, `${safeName}-brief.png`), fullPage: true });
      }
    }

    report.users.push(entry);
    await context.close();
  }
} finally {
  await browser.close();
}

await writeFile(path.join(artifactDir, 'report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report.users.map(({ username, landingUrl, recommendationCount, firstBriefUrl, errors }) => ({
  username,
  landingUrl,
  recommendationCount,
  firstBriefUrl,
  errorCount: errors.length,
})), null, 2));
