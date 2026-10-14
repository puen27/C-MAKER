import { readdir, stat, access } from 'node:fs/promises';
import path from 'node:path';

const rawDir = path.resolve('artifacts', 'raw');
const reportPath = path.join(rawDir, 'record-report.json');

async function report() {
  const files = (await readdir(rawDir)).filter((name) => name.endsWith('.webm'));
  const sizes = [];
  for (const file of files) {
    const info = await stat(path.join(rawDir, file));
    sizes.push(`${file}:${info.size}`);
  }
  console.log(`${new Date().toISOString()} recording ${sizes.join(',')}`);
}

await report();
setInterval(report, 15_000);
