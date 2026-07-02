import { test } from 'node:test';
import assert from 'node:assert/strict';
import { defineCommand } from '../src/defineCommand.js';

test('defineCommand normalizes defaults', () => {
  const cmd = defineCommand({
    name: 'foo',
    description: 'Foo',
    handler: async () => ({ content: 'ok' }),
  });
  assert.equal(cmd.auth, 'linked');
  assert.equal(cmd.beta, false);
  assert.deepEqual(cmd.options, []);
});

test('defineCommand preserves explicit values', () => {
  const cmd = defineCommand({
    name: 'foo',
    description: 'Foo',
    auth: 'public',
    beta: true,
    options: [{ name: 'x', type: 'string', required: true, description: 'X' }],
    handler: async () => ({ content: 'ok' }),
  });
  assert.equal(cmd.auth, 'public');
  assert.equal(cmd.beta, true);
  assert.equal(cmd.options[0].name, 'x');
});

test('defineCommand throws on missing name', () => {
  assert.throws(
    () => defineCommand({ description: 'x', handler: async () => ({}) }),
    /name/,
  );
});

test('defineCommand throws on missing handler', () => {
  assert.throws(
    () => defineCommand({ name: 'x', description: 'x' }),
    /handler/,
  );
});

test('defineCommand normalizes subcommands', () => {
  const cmd = defineCommand({
    name: 'foo',
    description: 'x',
    auth: 'admin',
    subcommands: [
      { name: 'bar', description: 'b', handler: async () => ({ content: 'ok' }) },
    ],
    handler: async () => ({ content: 'top' }),
  });
  assert.equal(cmd.subcommands.length, 1);
  assert.equal(cmd.subcommands[0].auth, 'admin'); // inherited from parent
});
