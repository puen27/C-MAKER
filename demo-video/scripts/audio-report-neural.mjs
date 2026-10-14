import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import ffprobe from 'ffprobe-static';

const timeline = JSON.parse(await readFile('content/timeline.json', 'utf8'));
const report = timeline.segments.map((segment) => {
  const file = path.resolve('artifacts', 'audio-neural', `segment-${String(segment.id).padStart(2, '0')}.mp3`);
  const duration = Number(execFileSync(ffprobe.path, [
    '-v', 'error', '-show_entries', 'format=duration',
    '-of', 'default=noprint_wrappers=1:nokey=1', file,
  ], { encoding: 'utf8' }).trim());
  const slot = segment.end - segment.start;
  return { id: segment.id, duration: Number(duration.toFixed(3)), slot, margin: Number((slot - duration).toFixed(3)), fits: duration <= slot - 0.25 };
});
await writeFile(path.resolve('artifacts', 'audio-neural', 'duration-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.table(report);
if (report.some((item) => !item.fits)) process.exitCode = 1;
