import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createRecorder } from '../src/meeting/recorder.js';

// A controllable clock + wait, so drain timing is deterministic rather than
// dependent on real timers.
function makeClock(onWait) {
  let t = 0;
  return {
    now: () => t,
    advance: (ms) => { t += ms; },
    // `onWait` runs on every poll of the drain loop. It is what lets a test
    // simulate audio still arriving DURING the drain -- a setInterval never
    // gets a turn here, because these awaits resolve as microtasks and the
    // loop finishes before the event loop reaches any macrotask.
    wait: async (ms) => { t += ms; if (onWait) onWait(); },
  };
}

function makeConnection() {
  const streams = new Map();
  const conn = {
    destroyed: false,
    destroyedAt: null,
    receiver: {
      speaking: new EventEmitter(),
      subscribe(userId) {
        const s = new EventEmitter();
        streams.set(userId, s);
        return s;
      },
    },
    destroy() { this.destroyed = true; },
  };
  conn.streams = streams;
  return conn;
}

function makeSink() {
  const frames = [];
  return { frames, sendControl() {}, sendFrame: (id, ts, p) => frames.push([id, ts, p]) };
}

async function startedRecorder(clock, conn, sink) {
  const recorder = createRecorder({
    sink,
    now: clock.now,
    wait: clock.wait,
    join: () => conn,
    ready: async () => {},
  });
  await recorder.start({ id: 'vc1', guild: { id: 'g1', voiceAdapterCreator: null, members: { cache: new Map() } } });
  return recorder;
}

test('stop drains in-flight audio before destroying the connection', async () => {
  const clock = makeClock();
  const conn = makeConnection();
  const sink = makeSink();
  const recorder = await startedRecorder(clock, conn, sink);

  conn.receiver.speaking.emit('start', 'u1');
  const stream = conn.streams.get('u1');
  stream.emit('data', Buffer.from('early'));

  // A packet still in Discord's receive buffer lands just after /record stop.
  // Destroying immediately discards it, clipping the last words of the meeting.
  const stopping = recorder.stop();
  stream.emit('data', Buffer.from('LAST'));
  await stopping;

  const payloads = sink.frames.map(([, , p]) => p.toString());
  assert.ok(payloads.includes('LAST'), `tail packet dropped; got ${JSON.stringify(payloads)}`);
  assert.equal(conn.destroyed, true);
});

test('stop stops forwarding once the connection is torn down', async () => {
  const clock = makeClock();
  const conn = makeConnection();
  const sink = makeSink();
  const recorder = await startedRecorder(clock, conn, sink);
  conn.receiver.speaking.emit('start', 'u1');
  const stream = conn.streams.get('u1');

  await recorder.stop();
  const before = sink.frames.length;
  stream.emit('data', Buffer.from('after-teardown'));

  assert.equal(sink.frames.length, before);
});

test('stop gives up draining if audio keeps arriving', { timeout: 5000 }, async () => {
  let onPoll = () => {};
  const clock = makeClock(() => onPoll());
  const conn = makeConnection();
  const sink = makeSink();
  const recorder = await startedRecorder(clock, conn, sink);
  conn.receiver.speaking.emit('start', 'u1');
  const stream = conn.streams.get('u1');

  // Someone talks straight through the stop: every poll delivers another
  // packet, so the quiet condition can NEVER be met and only the hard deadline
  // can end the drain. Without that deadline this loops forever and the test
  // times out -- which is the point of the timeout above.
  onPoll = () => stream.emit('data', Buffer.from('x'));

  await recorder.stop();

  assert.equal(conn.destroyed, true);
  assert.ok(clock.now() >= 2000, `drained only ${clock.now()}ms; the 2s bound did not apply`);
  assert.ok(clock.now() < 2500, `drained ${clock.now()}ms; the bound is not tight`);
});

test('stop is safe to call twice', async () => {
  const clock = makeClock();
  const conn = makeConnection();
  const recorder = await startedRecorder(clock, conn, makeSink());
  await recorder.stop();
  await assert.doesNotReject(() => recorder.stop());
});
