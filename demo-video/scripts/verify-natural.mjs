import { execFileSync, spawnSync } from 'node:child_process';
import { stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';
import ffprobe from 'ffprobe-static';

const originalPath = path.resolve('output', 'C-MAKER-demo-3min.mp4');
const naturalPath = path.resolve('output', 'C-MAKER-demo-3min-natural.mp4');

function probe(file) {
  return JSON.parse(execFileSync(ffprobe.path, [
    '-v', 'error', '-show_streams', '-show_format', '-of', 'json', file,
  ], { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }));
}

function streamHash(file, selector) {
  const result = spawnSync(ffmpegPath, [
    '-v', 'error', '-i', file, '-map', selector, '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-',
  ], { encoding: 'utf8', windowsHide: true });
  if (result.status !== 0) throw new Error(`스트림 해시 실패: ${selector}`);
  return result.stdout.trim();
}

function volume(file) {
  const result = spawnSync(ffmpegPath, [
    '-i', file, '-map', '0:a:0', '-af', 'volumedetect', '-f', 'null', 'NUL',
  ], { encoding: 'utf8', windowsHide: true });
  const log = `${result.stdout ?? ''}\n${result.stderr ?? ''}`;
  return {
    mean: Number(log.match(/mean_volume:\s*(-?[\d.]+) dB/)?.[1]),
    max: Number(log.match(/max_volume:\s*(-?[\d.]+) dB/)?.[1]),
  };
}

const data = probe(naturalPath);
const video = data.streams.find((stream) => stream.codec_type === 'video');
const audio = data.streams.find((stream) => stream.codec_type === 'audio');
const file = await stat(naturalPath);
const levels = volume(naturalPath);
const originalVideoHash = streamHash(originalPath, '0:v:0');
const naturalVideoHash = streamHash(naturalPath, '0:v:0');
const originalAudioHash = streamHash(originalPath, '0:a:0');
const naturalAudioHash = streamHash(naturalPath, '0:a:0');

const checks = {
  durationIsThreeMinutes: Math.abs(Number(data.format.duration) - 180) <= 0.05,
  fullHd: video?.width === 1920 && video?.height === 1080,
  h264Video: video?.codec_name === 'h264',
  aacAudio: audio?.codec_name === 'aac',
  expectedFrameRate: video?.avg_frame_rate === '25/1',
  audioSampleRate: audio?.sample_rate === '48000',
  audioIsAudible: Number.isFinite(levels.mean) && levels.mean > -45 && Number.isFinite(levels.max) && levels.max <= 0,
  videoIsBitIdentical: originalVideoHash === naturalVideoHash,
  narrationWasReplaced: originalAudioHash !== naturalAudioHash,
  reasonableFileSize: file.size > 5 * 1024 * 1024,
};

const report = {
  videoPath: naturalPath,
  duration: Number(data.format.duration),
  sizeMiB: Number((file.size / 1024 / 1024).toFixed(2)),
  voice: 'ko-KR-SunHiNeural',
  rate: '-5%',
  video: { codec: video?.codec_name, width: video?.width, height: video?.height, frameRate: video?.avg_frame_rate, pixelFormat: video?.pix_fmt },
  audio: { codec: audio?.codec_name, sampleRate: audio?.sample_rate, channels: audio?.channels, meanVolumeDb: levels.mean, maxVolumeDb: levels.max },
  checks,
};
await writeFile(path.resolve('output', 'verification-natural-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
if (Object.values(checks).some((passed) => !passed)) process.exitCode = 1;
