import { test } from 'node:test';
import assert from 'node:assert/strict';
import record from '../src/commands/record.js';
import { commands, partitionCommands } from '../src/commands/index.js';

test('record command is beta with start/status/stop subcommands', () => {
  assert.equal(record.name, 'record');
  assert.equal(record.beta, true);
  const names = record.subcommands.map((s) => s.name).sort();
  assert.deepEqual(names, ['start', 'status', 'stop']);
});

test('record is registered in the command registry', () => {
  assert.equal(commands.get('record'), record);
});

test('record is the sole beta command (testing-guild only)', () => {
  const { beta } = partitionCommands([...commands.values()]);
  assert.deepEqual(beta.map((c) => c.name), ['record']);
});

test('record handler is a guard that is never reached via the neutral path (adapter intercepts)', async () => {
  const payload = await record.handler({});
  assert.equal(payload.ephemeral, true);
  assert.match(payload.content, /voice surface/i);
});

test('record subcommand handlers are also guards', async () => {
  for (const sub of record.subcommands) {
    const payload = await sub.handler({});
    assert.equal(payload.ephemeral, true);
    assert.match(payload.content, /voice surface/i);
  }
});
