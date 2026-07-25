import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTranscribeClient } from '../src/meeting/stt.js';

// Fake TranscriptResultStream yielding one partial then one final result.
function fakeSdk() {
  const events = [
    { TranscriptEvent: { Transcript: { Results: [
      { IsPartial: true, Alternatives: [{ Transcript: 'hel' }] },
    ] } } },
    { TranscriptEvent: { Transcript: { Results: [
      { IsPartial: false, Alternatives: [{
        Transcript: 'hello there',
        Items: [
          { Type: 'pronunciation', Content: 'hello', StartTime: 0.5 },
          { Type: 'pronunciation', Content: 'there', StartTime: 1.0 },
        ],
      }] },
    ] } } },
  ];
  return {
    StartStreamTranscriptionCommand: class { constructor(input) { this.input = input; } },
    client: { async send() { return { TranscriptResultStream: (async function* () { yield* events; })() }; } },
  };
}

test('transcribePcm accumulates only final results with word timestamps', async () => {
  const { StartStreamTranscriptionCommand, client } = fakeSdk();
  const stt = createTranscribeClient({ region: 'us-east-1', sdk: { client, StartStreamTranscriptionCommand } });
  async function* pcm() { yield Buffer.from([0, 0, 0, 0]); }
  const out = await stt.transcribePcm({ pcmChunks: pcm() });
  assert.equal(out.text, 'hello there');
  assert.deepEqual(out.words, [
    { text: 'hello', startMs: 500 },
    { text: 'there', startMs: 1000 },
  ]);
});

test('transcribePcm splits a single large buffer into frame-sized AudioEvents', async () => {
  let frameCount = 0;
  const client = {
    async send(command) {
      for await (const _event of command.input.AudioStream) {
        frameCount += 1;
      }
      return { TranscriptResultStream: (async function* () {})() };
    },
  };
  const StartStreamTranscriptionCommand = class { constructor(input) { this.input = input; } };
  const stt = createTranscribeClient({ region: 'us-east-1', sdk: { client, StartStreamTranscriptionCommand } });
  async function* pcm() { yield Buffer.alloc(8000); }
  await stt.transcribePcm({ pcmChunks: pcm() });
  assert.equal(frameCount, Math.ceil(8000 / 3200));
  assert.equal(frameCount, 3);
});
