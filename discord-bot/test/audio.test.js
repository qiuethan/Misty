import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pcmToMono16kArgs, mixToMp3Args } from '../src/meeting/audio.js';

test('pcmToMono16kArgs declares raw 48k stereo in, 16k mono raw out', () => {
  const a = pcmToMono16kArgs('/tmp/a.pcm').join(' ');
  assert.match(a, /-f s16le/);
  assert.match(a, /-ar 48000/);
  assert.match(a, /-ac 2/);
  assert.match(a, /-i \/tmp\/a\.pcm/);
  assert.match(a, /-ar 16000/);
  assert.match(a, /-ac 1/);
});

test('mixToMp3Args maps N inputs with amix and writes mp3', () => {
  const a = mixToMp3Args(['/tmp/a.pcm', '/tmp/b.pcm'], '/tmp/out.mp3').join(' ');
  assert.match(a, /amix=inputs=2/);
  assert.match(a, /\/tmp\/out\.mp3/);
});
