import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dispatchInteraction } from '../src/router.js';
import { DirectoryUnavailable } from '../src/directoryClient.js';

function fakeInteraction(commandName) {
  const replies = [];
  return {
    commandName,
    user: { id: '123', username: 'alex' },
    replied: false,
    deferred: false,
    reply: async (p) => { replies.push(p); },
    followUp: async (p) => { replies.push(p); },
    replies,
  };
}

function cmd(name, auth, execute) {
  return { data: { name }, auth, execute };
}

function ctxWith(getPersonByDiscordId) {
  return { appContext: { directory: { getPersonByDiscordId } } };
}

test('unknown command is a no-op', async () => {
  const interaction = fakeInteraction('nope');
  const commands = new Map();
  await dispatchInteraction(interaction, { commands, appContext: {} });
  assert.equal(interaction.replies.length, 0);
});

test('public command runs without authenticating', async () => {
  let ran = false;
  let authCalled = false;
  const interaction = fakeInteraction('link');
  const commands = new Map([['link', cmd('link', 'public', async () => { ran = true; })]]);
  const appContext = { directory: { getPersonByDiscordId: async () => { authCalled = true; return null; } } };
  await dispatchInteraction(interaction, { commands, appContext });
  assert.equal(ran, true);
  assert.equal(authCalled, false);
});

test('linked command runs for a linked user and receives the principal', async () => {
  const person = { id: 'p1', display_name: 'Alex' };
  let seen;
  const interaction = fakeInteraction('whoami');
  const commands = new Map([['whoami', cmd('whoami', 'linked', async (i, ctx) => { seen = ctx.principal; })]]);
  await dispatchInteraction(interaction, { commands, ...ctxWith(async () => person) });
  assert.deepEqual(seen, { person });
});

test('linked command is denied for an unlinked user and does not execute', async () => {
  let ran = false;
  const interaction = fakeInteraction('whoami');
  const commands = new Map([['whoami', cmd('whoami', 'linked', async () => { ran = true; })]]);
  await dispatchInteraction(interaction, { commands, ...ctxWith(async () => null) });
  assert.equal(ran, false);
  assert.match(interaction.replies[0].content, /link/i);
  assert.equal(interaction.replies[0].ephemeral, true);
});

test('omitted auth defaults to linked (fail-secure)', async () => {
  let ran = false;
  const interaction = fakeInteraction('secret');
  const commands = new Map([['secret', cmd('secret', undefined, async () => { ran = true; })]]);
  await dispatchInteraction(interaction, { commands, ...ctxWith(async () => null) });
  assert.equal(ran, false);
});

test('directory outage fails closed (deny, do not execute)', async () => {
  let ran = false;
  const interaction = fakeInteraction('whoami');
  const commands = new Map([['whoami', cmd('whoami', 'linked', async () => { ran = true; })]]);
  await dispatchInteraction(interaction, {
    commands,
    ...ctxWith(async () => { throw new DirectoryUnavailable('down'); }),
  });
  assert.equal(ran, false);
  assert.match(interaction.replies[0].content, /unavailable|try again/i);
});

test('handler error is caught centrally with a generic reply', async () => {
  const interaction = fakeInteraction('link');
  const commands = new Map([['link', cmd('link', 'public', async () => { throw new Error('boom'); })]]);
  await dispatchInteraction(interaction, { commands, appContext: {} });
  assert.match(interaction.replies[0].content, /went wrong/i);
});
