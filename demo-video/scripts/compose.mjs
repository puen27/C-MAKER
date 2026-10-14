import { execFileSync, spawnSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';
import ffprobe from 'ffprobe-static';

const timeline = JSON.parse(await readFile('content/timeline.json', 'utf8'));
const duration = timeline.durationSeconds;
const rawVideo = path.resolve('artifacts', 'raw', 'c-maker-demo-raw.webm');
const outputDir = path.resolve('output');
const output = path.join(outputDir, 'C-MAKER-demo-3min.mp4');
await mkdir(outputDir, { recursive: true });

const rawDuration = Number(execFileSync(ffprobe.path, [
  '-v', 'error', '-show_entries', 'format=duration',
  '-of', 'default=noprint_wrappers=1:nokey=1', rawVideo,
], { encoding: 'utf8' }).trim());
const trimStart = Math.max(0, rawDuration - duration);

const args = ['-y', '-ss', trimStart.toFixed(3), '-i', rawVideo];
for (const segment of timeline.segments) {
  args.push('-i', path.resolve('artifacts', 'audio', `segment-${String(segment.id).padStart(2, '0')}.wav`));
}

const delayed = timeline.segments.map((segment, index) => {
  const delayMs = Math.round(segment.start * 1000);
  return `[${index + 1}:a]adelay=${delayMs}|${delayMs},volume=1.0[a${segment.id}]`;
});
const mixInputs = timeline.segments.map((segment) => `[a${segment.id}]`).join('');
const filter = [
  ...delayed,
  `${mixInputs}amix=inputs=${timeline.segments.length}:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.92,apad=pad_dur=${duration},atrim=duration=${duration}[aout]`,
].join(';');

args.push(
  '-filter_complex', filter,
  '-map', '0:v:0', '-map', '[aout]',
  '-t', String(duration),
  '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
  '-pix_fmt', 'yuv420p', '-r', '25',
  '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
  '-movflags', '+faststart',
  output,
);

const result = spawnSync(ffmpegPath, args, { stdio: 'inherit', windowsHide: true });
if (result.status !== 0) throw new Error(`FFmpeg 인코딩 실패: exit ${result.status}`);

const report = { rawVideo, rawDuration, trimStart, output, targetDuration: duration };
await writeFile(path.join(outputDir, 'compose-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
