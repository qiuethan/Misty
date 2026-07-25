import { spawn } from 'node:child_process';

const RAW_IN = ['-f', 's16le', '-ar', '48000', '-ac', '2'];

export function pcmToMono16kArgs(inputPath) {
  return [...RAW_IN, '-i', inputPath, '-ar', '16000', '-ac', '1', '-f', 's16le', 'pipe:1'];
}

export function mixToMp3Args(inputPaths, outputPath) {
  const inputs = inputPaths.flatMap((p) => [...RAW_IN, '-i', p]);
  const filter = `amix=inputs=${inputPaths.length}:normalize=0`;
  return [...inputs, '-filter_complex', filter, '-codec:a', 'libmp3lame', '-q:a', '5', '-y', outputPath];
}

export function runFfmpeg(args, { input } = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn('ffmpeg', args, { stdio: ['pipe', 'pipe', 'pipe'] });
    const out = [];
    const err = [];
    proc.stdout.on('data', (d) => out.push(d));
    proc.stderr.on('data', (d) => err.push(d));
    proc.on('error', reject);
    proc.on('close', (code) => {
      if (code === 0) resolve(Buffer.concat(out));
      else reject(new Error(`ffmpeg exited ${code}: ${Buffer.concat(err).toString().slice(-500)}`));
    });
    if (input) { proc.stdin.write(input); proc.stdin.end(); }
  });
}
