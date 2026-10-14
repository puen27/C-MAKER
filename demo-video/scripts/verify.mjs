import { execFileSync, spawnSync } from 'node:child_process';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import ffmpegPath from 'ffmpeg-static';
import ffprobe from 'ffprobe-static';

const videoPath = path.resolve('output', 'C-MAKER-demo-3min.mp4');
const frameDir = path.resolve('output', 'verification-frames');
await mkdir(frameDir, { recursive: true });

const probe = JSON.parse(execFileSync(ffprobe.path, [
  '-v', 'error', '-show_streams', '-show_format', '-of', 'json', videoPath,
], { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }));
const video = probe.streams.find((stream) => stream.codec_type === 'video');
const audio = probe.streams.find((stream) => stream.codec_type === 'audio');
const duration = Number(probe.format.duration);
const file = await stat(videoPath);

const volumeResult = spawnSync(ffmpegPath, [
  '-i', videoPath, '-map', '0:a:0', '-af', 'volumedetect', '-f', 'null', 'NUL',
], { encoding: 'utf8', windowsHide: true });
const volumeLog = `${volumeResult.stdout ?? ''}\n${volumeResult.stderr ?? ''}`;
const meanVolume = Number(volumeLog.match(/mean_volume:\s*(-?[\d.]+) dB/)?.[1]);
const maxVolume = Number(volumeLog.match(/max_volume:\s*(-?[\d.]+) dB/)?.[1]);

const frameTimes = [5, 30, 45, 80, 95, 108, 132, 145, 158, 169, 176, 179];
const frames = [];
for (const second of frameTimes) {
  const output = path.join(frameDir, `frame-${String(second).padStart(3, '0')}s.jpg`);
  const result = spawnSync(ffmpegPath, [
    '-y', '-ss', String(second), '-i', videoPath, '-frames:v', '1', '-q:v', '2', output,
  ], { stdio: 'ignore', windowsHide: true });
  if (result.status !== 0) throw new Error(`${second}초 대표 프레임 추출 실패`);
  frames.push(output);
}

const checks = {
  durationIsThreeMinutes: Math.abs(duration - 180) <= 0.05,
  fullHd: video?.width === 1920 && video?.height === 1080,
  h264Video: video?.codec_name === 'h264',
  aacAudio: audio?.codec_name === 'aac',
  expectedFrameRate: video?.avg_frame_rate === '25/1',
  audioSampleRate: audio?.sample_rate === '48000',
  audioIsAudible: Number.isFinite(meanVolume) && meanVolume > -45 && Number.isFinite(maxVolume) && maxVolume <= 0,
  reasonableFileSize: file.size > 5 * 1024 * 1024,
  representativeFramesExtracted: frames.length === frameTimes.length,
};

const report = {
  videoPath,
  duration,
  sizeBytes: file.size,
  sizeMiB: Number((file.size / 1024 / 1024).toFixed(2)),
  video: {
    codec: video?.codec_name,
    width: video?.width,
    height: video?.height,
    frameRate: video?.avg_frame_rate,
    pixelFormat: video?.pix_fmt,
  },
  audio: {
    codec: audio?.codec_name,
    sampleRate: audio?.sample_rate,
    channels: audio?.channels,
    meanVolumeDb: meanVolume,
    maxVolumeDb: maxVolume,
  },
  checks,
  frames,
};
await writeFile(path.resolve('output', 'verification-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
if (Object.values(checks).some((passed) => !passed)) process.exitCode = 1;
