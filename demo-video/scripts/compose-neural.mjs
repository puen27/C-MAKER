import { spawnSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';

const timeline = JSON.parse(await readFile('content/timeline.json', 'utf8'));
const duration = timeline.durationSeconds;
const sourceVideo = path.resolve('output', 'C-MAKER-demo-3min.mp4');
const outputDir = path.resolve('output');
const output = path.join(outputDir, 'C-MAKER-demo-3min-natural.mp4');
await mkdir(outputDir, { recursive: true });

const args = ['-y', '-i', sourceVideo];
for (const segment of timeline.segments) {
  args.push('-i', path.resolve('artifacts', 'audio-neural', `segment-${String(segment.id).padStart(2, '0')}.mp3`));
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
  '-c:v', 'copy',
  '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
  '-movflags', '+faststart',
  output,
);

const result = spawnSync(ffmpegPath, args, { stdio: 'inherit', windowsHide: true });
if (result.status !== 0) throw new Error(`신경망 나레이션 합성 실패: exit ${result.status}`);

const report = {
  sourceVideo,
  output,
  targetDuration: duration,
  voice: 'ko-KR-SunHiNeural',
  rate: '-5%',
  videoCopiedWithoutReencoding: true,
};
await writeFile(path.join(outputDir, 'compose-natural-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
