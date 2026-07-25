import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSessionManager } from '../src/meeting/sessionManager.js';

function deps(posted) {
  return {
    now: () => 1000,
    maxRecordingMs: 3_600_000,
    tmpRoot: '/tmp',
    makeRecorder: () => ({
      async start() {},
      async stop() {
        return { startedAt: 0, endedAt: 60_000,
          tracks: [{ userId: 'u1', displayName: 'alice', pcmPath: '/tmp/u1.pcm' }] };
      },
    }),
    audio: {
      pcmToMono16kArgs: () => [],
      mixToMp3Args: () => [],
      runFfmpeg: async () => Buffer.from([]),
    },
    transcribeClient: {
      async transcribePcm() { return { text: 'hello', words: [{ text: 'hello', startMs: 0 }] }; },
    },
    reportService: {
      async buildReport({ segments }) {
        return { transcript: 'T', minutes: { summary: 's' }, pdfBuffer: Buffer.from('%PDF-1'), _segments: segments };
      },
    },
    poster: async (args) => posted.push(args),
  };
}

test('start then stop runs pipeline and posts a report', async () => {
  const posted = [];
  const mgr = createSessionManager(deps(posted));
  const started = mgr.start({ guildId: 'g', voiceChannel: { id: 'v' }, textChannel: { id: 't' } });
  assert.equal(started.status, 'recording');
  const stopped = await mgr.stop('g');
  assert.equal(stopped.status, 'stopped');
  assert.equal(posted.length, 1);
  assert.ok(Buffer.isBuffer(posted[0].pdfBuffer));
});

test('double start on same guild is rejected', () => {
  const mgr = createSessionManager(deps([]));
  mgr.start({ guildId: 'g', voiceChannel: { id: 'v' }, textChannel: { id: 't' } });
  assert.equal(mgr.start({ guildId: 'g', voiceChannel: { id: 'v' }, textChannel: { id: 't' } }).status, 'already-recording');
});

test('stop with no active session returns not-recording', async () => {
  const mgr = createSessionManager(deps([]));
  assert.equal((await mgr.stop('nope')).status, 'not-recording');
});
