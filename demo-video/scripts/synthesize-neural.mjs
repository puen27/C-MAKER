import { EdgeTTS } from 'node-edge-tts';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

const timeline = JSON.parse(await readFile('content/timeline.json', 'utf8'));
const outputDir = path.resolve('artifacts', 'audio-neural');
const voice = process.env.C_MAKER_TTS_VOICE ?? 'ko-KR-SunHiNeural';
const rate = process.env.C_MAKER_TTS_RATE ?? '-5%';
await mkdir(outputDir, { recursive: true });

const files = [];
for (const segment of timeline.segments) {
  const file = path.join(outputDir, `segment-${String(segment.id).padStart(2, '0')}.mp3`);
  await rm(file, { force: true });
  const tts = new EdgeTTS({
    voice,
    lang: 'ko-KR',
    outputFormat: 'audio-24khz-96kbitrate-mono-mp3',
    rate,
    pitch: '+0%',
    volume: '+0%',
    timeout: 30_000,
  });
  await tts.ttsPromise(segment.text, file);
  files.push(file);
  console.log(`generated ${path.basename(file)}`);
}

const report = { voice, rate, files };
await writeFile(path.join(outputDir, 'generation-report.json'), JSON.stringify(report, null, 2), 'utf8');
console.log(JSON.stringify(report, null, 2));
