import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolvePrincipal } from '../src/auth/principal.js';
import { authorize } from '../src/auth/policy.js';
import { DirectoryUnavailable } from '../src/directoryClient.js';

test('resolvePrincipal returns { person } when linked', async () => {
  const person = { id: 'p1', display_name: 'Alex' };
  const principal = await resolvePrincipal({ getPersonByDiscordId: async () => person }, '123');
  assert.deepEqual(principal, { person });
});

test('resolvePrincipal returns null when unlinked', async () => {
  const principal = await resolvePrincipal({ getPersonByDiscordId: async () => null }, '123');
  assert.equal(principal, null);
});

test('resolvePrincipal propagates DirectoryUnavailable', async () => {
  await assert.rejects(
    () => resolvePrincipal({ getPersonByDiscordId: async () => { throw new DirectoryUnavailable('down'); } }, '123'),
    DirectoryUnavailable,
  );
});

test('authorize public is always ok', () => {
  assert.deepEqual(authorize('public', null), { ok: true });
  assert.deepEqual(authorize('public', { person: {} }), { ok: true });
});

test('authorize linked requires a principal', () => {
  assert.deepEqual(authorize('linked', { person: {} }), { ok: true });
  assert.deepEqual(authorize('linked', null), { ok: false, reason: 'not_linked' });
});

test('authorize denies unknown policy (fail closed)', () => {
  assert.deepEqual(authorize('superadmin', { person: {} }), { ok: false, reason: 'unknown_policy' });
});
