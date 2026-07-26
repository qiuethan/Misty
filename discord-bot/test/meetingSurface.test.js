import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createMeetingSurface } from '../src/meeting/meetingSurface.js';

function makeFakes({ stopImpl, posterImpl } = {}) {
  const openStreamCalls = [];
  const closeCalls = [];
  const stopCalls = [];
  const makeRecorderCalls = [];
  const recorderStartCalls = [];
  const recorderStopCalls = [];
  const posterCalls = [];

  const stream = {
    close: (...args) => closeCalls.push(args),
  };

  const meetingClient = {
    openStream: (sessionId, opts) => {
      openStreamCalls.push({ sessionId, opts });
      return stream;
    },
    stop: async (sessionId) => {
      stopCalls.push(sessionId);
      if (stopImpl) return stopImpl(sessionId);
      return { transcript: 't', minutes: 'm', pdf_b64: 'p', audio_b64: 'a' };
    },
  };

  const recorder = {
    start: async (voiceChannel) => {
      recorderStartCalls.push(voiceChannel);
    },
    stop: async () => {
      recorderStopCalls.push(true);
    },
  };

  const makeRecorder = (args) => {
    makeRecorderCalls.push(args);
    return recorder;
  };

  const poster = async (args) => {
    posterCalls.push(args);
    if (posterImpl) return posterImpl(args);
  };

  return {
    meetingClient,
    makeRecorder,
    poster,
    stream,
    recorder,
    openStreamCalls,
    closeCalls,
    stopCalls,
    makeRecorderCalls,
    recorderStartCalls,
    recorderStopCalls,
    posterCalls,
  };
}

test('start opens a stream, starts the recorder, and returns recording + sessionId', async () => {
  const fakes = makeFakes();
  const genId = () => 'sess-1';
  const surface = createMeetingSurface({ ...fakes, genId });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  const result = surface.start({ guildId: 'g1', voiceChannel, textChannel });

  assert.deepEqual(result, { status: 'recording', sessionId: 'sess-1' });
  assert.equal(fakes.openStreamCalls.length, 1);
  assert.deepEqual(fakes.openStreamCalls[0], { sessionId: 'sess-1', opts: { guildId: 'g1' } });
  assert.equal(fakes.makeRecorderCalls.length, 1);
  assert.equal(fakes.makeRecorderCalls[0].sink, fakes.stream);
  // allow the fire-and-forget recorder.start promise to settle
  await Promise.resolve();
  assert.deepEqual(fakes.recorderStartCalls, [voiceChannel]);
});

test('double start for the same guild returns already-recording and does not open a second stream', async () => {
  const fakes = makeFakes();
  let n = 0;
  const genId = () => `sess-${++n}`;
  const surface = createMeetingSurface({ ...fakes, genId });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  const first = surface.start({ guildId: 'g1', voiceChannel, textChannel });
  const second = surface.start({ guildId: 'g1', voiceChannel, textChannel });

  assert.equal(first.status, 'recording');
  assert.deepEqual(second, { status: 'already-recording' });
  assert.equal(fakes.openStreamCalls.length, 1);
});

test('stop calls recorder.stop, stream.close, meetingClient.stop, then poster with the report, and returns stopped', async () => {
  const fakes = makeFakes();
  const genId = () => 'sess-1';
  const surface = createMeetingSurface({ ...fakes, genId });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  surface.start({ guildId: 'g1', voiceChannel, textChannel });

  const result = await surface.stop('g1');

  assert.deepEqual(result, { status: 'stopped' });
  assert.equal(fakes.recorderStopCalls.length, 1);
  assert.equal(fakes.closeCalls.length, 1);
  assert.deepEqual(fakes.stopCalls, ['sess-1']);
  assert.equal(fakes.posterCalls.length, 1);
  assert.equal(fakes.posterCalls[0].channel, textChannel);
  assert.deepEqual(fakes.posterCalls[0].report, {
    transcript: 't',
    minutes: 'm',
    pdf_b64: 'p',
    audio_b64: 'a',
  });
});

test('stop with no active session returns not-recording', async () => {
  const fakes = makeFakes();
  const surface = createMeetingSurface({ ...fakes, genId: () => 'sess-1' });
  const result = await surface.stop('unknown-guild');
  assert.deepEqual(result, { status: 'not-recording' });
});

test('a throwing meetingClient.stop clears the session (subsequent start succeeds) and returns error', async () => {
  const fakes = makeFakes({
    stopImpl: async () => {
      throw new Error('boom');
    },
  });
  let n = 0;
  const genId = () => `sess-${++n}`;
  const surface = createMeetingSurface({ ...fakes, genId });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  surface.start({ guildId: 'g1', voiceChannel, textChannel });

  const result = await surface.stop('g1');
  assert.deepEqual(result, { status: 'error' });

  // session should be cleared: a fresh start for the same guild succeeds
  const second = surface.start({ guildId: 'g1', voiceChannel, textChannel });
  assert.equal(second.status, 'recording');
});

test('a throwing poster clears the session (subsequent start succeeds) and returns error', async () => {
  const fakes = makeFakes({
    posterImpl: async () => {
      throw new Error('poster failed');
    },
  });
  let n = 0;
  const genId = () => `sess-${++n}`;
  const surface = createMeetingSurface({ ...fakes, genId });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  surface.start({ guildId: 'g1', voiceChannel, textChannel });

  const result = await surface.stop('g1');
  assert.deepEqual(result, { status: 'error' });

  const second = surface.start({ guildId: 'g1', voiceChannel, textChannel });
  assert.equal(second.status, 'recording');
});

test('status returns recording + elapsedMs while active, not-recording otherwise', async () => {
  let t = 1000;
  const now = () => t;
  const fakes = makeFakes();
  const surface = createMeetingSurface({ ...fakes, now, genId: () => 'sess-1' });

  assert.deepEqual(surface.status('g1'), { status: 'not-recording' });

  const voiceChannel = { id: 'vc1' };
  const textChannel = { id: 'tc1' };
  surface.start({ guildId: 'g1', voiceChannel, textChannel });

  t = 1500;
  const active = surface.status('g1');
  assert.equal(active.status, 'recording');
  assert.equal(active.elapsedMs, 500);

  await surface.stop('g1');
  assert.deepEqual(surface.status('g1'), { status: 'not-recording' });
});

test('a rejected recorder.start does not crash the process (logged via console.error)', async () => {
  const fakes = makeFakes();
  fakes.recorder.start = async () => {
    throw new Error('join failed');
  };
  const surface = createMeetingSurface({ ...fakes, genId: () => 'sess-1' });

  const originalError = console.error;
  const errors = [];
  console.error = (...args) => errors.push(args);
  try {
    const result = surface.start({ guildId: 'g1', voiceChannel: { id: 'vc1' }, textChannel: { id: 'tc1' } });
    assert.equal(result.status, 'recording');
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
    assert.ok(errors.length >= 1);
  } finally {
    console.error = originalError;
  }
});
