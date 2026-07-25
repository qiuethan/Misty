import { test } from 'node:test';
import assert from 'node:assert/strict';
import record from '../src/commands/record.js';

function findSub(name) { return record.subcommands.find((s) => s.name === name); }

test('record command has start/status/stop, linked auth, ephemeral', () => {
  assert.equal(record.name, 'record');
  assert.deepEqual(record.subcommands.map((s) => s.name).sort(), ['start', 'status', 'stop']);
  assert.equal(record.auth, 'linked');
  assert.equal(record.ephemeral, true);
});

test('start delegates to sessionManager.start and reports recording', async () => {
  let called = null;
  const ctx = {
    sessionManager: { start: (a) => { called = a; return { status: 'recording' }; } },
    guildId: 'g', voiceChannel: { id: 'v' }, textChannel: { id: 't' },
  };
  const payload = await findSub('start').handler({ ctx });
  assert.equal(called.guildId, 'g');
  assert.match(payload.content, /recording/i);
});

test('start without a voice channel tells the user to join one', async () => {
  const ctx = { sessionManager: { start: () => ({ status: 'recording' }) }, guildId: 'g', voiceChannel: null };
  const payload = await findSub('start').handler({ ctx });
  assert.match(payload.content, /join a voice channel/i);
});

test('stop reports stopped', async () => {
  const ctx = { sessionManager: { stop: async () => ({ status: 'stopped' }) }, guildId: 'g' };
  const payload = await findSub('stop').handler({ ctx });
  assert.match(payload.content, /processing|stopped|transcript/i);
});
