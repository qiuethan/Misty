import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags } from 'discord.js';
import { dispatchInteraction } from '../src/router.js';
import { DirectoryUnavailable } from '../src/directoryClient.js';

function fakeInteraction(commandName) {
  const replies = [];
  const calls = [];
  return {
    commandName,
    user: { id: '123', username: 'alex' },
    replied: false,
    deferred: false,
    reply: async (p) => { replies.push(p); calls.push('reply'); },
    followUp: async (p) => { replies.push(p); calls.push('followUp'); },
    replies,
    calls,
  };
}

function cmd(name, auth, handler) {
  return { name, auth, handler, options: [], subcommands: [] };
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
  const commands = new Map([['whoami', cmd('whoami', 'linked', async (intent) => { seen = intent.principal; })]]);
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
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
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

test('non-DirectoryUnavailable authN error propagates and does not execute the command', async () => {
  let ran = false;
  const interaction = fakeInteraction('linked');
  const commands = new Map([['linked', cmd('linked', 'linked', async () => { ran = true; })]]);
  await assert.rejects(
    () => dispatchInteraction(interaction, {
      commands,
      ...ctxWith(async () => { throw new Error('boom'); }),
    }),
    (e) => e instanceof Error && e.message === 'boom',
  );
  assert.equal(ran, false);
});

test('safeReply routes through followUp when interaction already replied', async () => {
  let ran = false;
  const interaction = fakeInteraction('whoami');
  interaction.replied = true;
  const commands = new Map([['whoami', cmd('whoami', 'linked', async () => { ran = true; })]]);
  await dispatchInteraction(interaction, { commands, ...ctxWith(async () => null) });
  assert.equal(ran, false);
  assert.deepEqual(interaction.calls, ['followUp']);
  assert.match(interaction.replies[0].content, /link/i);
});

test('handler error is caught centrally with a generic reply', async () => {
  const interaction = fakeInteraction('link');
  const commands = new Map([['link', cmd('link', 'public', async () => { throw new Error('boom'); })]]);
  await dispatchInteraction(interaction, { commands, appContext: {} });
  assert.match(interaction.replies[0].content, /went wrong/i);
});

test('auth-as-function is called with the interaction and its return is the policy', async () => {
  let seenInteraction = null;
  let ran = false;
  const interaction = fakeInteraction('team');
  const commands = new Map([[
    'team',
    {
      name: 'team',
      auth: (i) => { seenInteraction = i; return 'public'; },
      handler: async () => { ran = true; },
      options: [],
      subcommands: [],
    },
  ]]);
  await dispatchInteraction(interaction, { commands, appContext: {} });
  assert.equal(seenInteraction, interaction);
  assert.equal(ran, true);
});

test('auth-as-function returning "admin" enforces admin', async () => {
  let ran = false;
  const interaction = fakeInteraction('team');
  const commands = new Map([[
    'team',
    {
      name: 'team',
      auth: () => 'admin',
      handler: async () => { ran = true; },
      options: [],
      subcommands: [],
    },
  ]]);
  const memberPerson = { id: 'p1', display_name: 'A', access_level: 'member' };
  await dispatchInteraction(interaction, {
    commands,
    ...ctxWith(async () => memberPerson),
  });
  assert.equal(ran, false);
  assert.match(interaction.replies[0].content, /don't have permission|not allowed/i);
});

test('auth-as-function returning nullish falls back to linked (fail-secure)', async () => {
  let ran = false;
  const interaction = fakeInteraction('team');
  const commands = new Map([[
    'team',
    {
      name: 'team',
      auth: () => null,
      handler: async () => { ran = true; },
      options: [],
      subcommands: [],
    },
  ]]);
  await dispatchInteraction(interaction, { commands, ...ctxWith(async () => null) });
  assert.equal(ran, false);
  assert.match(interaction.replies[0].content, /link/i);
});
