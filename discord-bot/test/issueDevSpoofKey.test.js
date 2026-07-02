import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseCliKeyOutput } from '../scripts/lib/issueDevSpoofKey.js';

test('parseCliKeyOutput extracts the tt_ prefixed key from stdout', () => {
  const stdout = 'tt_ABc12_secretsecretsecret\n';
  assert.equal(parseCliKeyOutput(stdout), 'tt_ABc12_secretsecretsecret');
});

test('parseCliKeyOutput throws when no key is present', () => {
  assert.throws(() => parseCliKeyOutput('nothing here'), /no key/);
});

test('parseCliKeyOutput trims whitespace', () => {
  assert.equal(parseCliKeyOutput('   tt_x_y   \n'), 'tt_x_y');
});
