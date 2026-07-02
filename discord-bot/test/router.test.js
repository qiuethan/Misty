import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dispatch } from '../src/router.js';
import { defineCommand } from '../src/defineCommand.js';

const publicCmd = defineCommand({
  name: 'ping',
  description: 'p',
  auth: 'public',
  handler: async () => ({ content: 'pong', ephemeral: true }),
});

const linkedCmd = defineCommand({
  name: 'me',
  description: 'm',
  auth: 'linked',
  handler: async ({ principal }) => ({ content: `hi ${principal.person.display_name}`, ephemeral: true }),
});

test('dispatch: unknown command → null', async () => {
  const out = await dispatch(
    { commandName: 'nope', options: {}, discordUserId: '1' },
    { commands: new Map(), appContext: {} },
  );
  assert.equal(out, null);
});

test('dispatch: public command runs without a principal', async () => {
  const out = await dispatch(
    { commandName: 'ping', options: {}, discordUserId: '1' },
    { commands: new Map([['ping', publicCmd]]), appContext: {} },
  );
  assert.equal(out.content, 'pong');
});

test('dispatch: unlinked user hitting a linked command → denied payload', async () => {
  const directory = {
    async getPersonByDiscordId() { return null; },
  };
  const out = await dispatch(
    { commandName: 'me', options: {}, discordUserId: '1' },
    { commands: new Map([['me', linkedCmd]]), appContext: { directory } },
  );
  assert.ok(out.content.includes('link'));
});

test('dispatch: linked user gets handler payload', async () => {
  const directory = {
    async getPersonByDiscordId() { return { id: 'p1', display_name: 'Alex' }; },
  };
  const out = await dispatch(
    { commandName: 'me', options: {}, discordUserId: '1' },
    { commands: new Map([['me', linkedCmd]]), appContext: { directory } },
  );
  assert.equal(out.content, 'hi Alex');
});

test('dispatch: DirectoryUnavailable → fail-closed payload', async () => {
  const { DirectoryUnavailable } = await import('../src/directoryClient.js');
  const directory = {
    async getPersonByDiscordId() { throw new DirectoryUnavailable('down'); },
  };
  const out = await dispatch(
    { commandName: 'me', options: {}, discordUserId: '1' },
    { commands: new Map([['me', linkedCmd]]), appContext: { directory } },
  );
  assert.ok(out.content.toLowerCase().includes('unavailable'));
});

test('dispatch: subcommand routes to the right handler', async () => {
  const cmd = defineCommand({
    name: 'team',
    description: 't',
    subcommands: [
      { name: 'list', handler: async () => ({ content: 'list', ephemeral: true }) },
      { name: 'create', auth: 'admin', handler: async () => ({ content: 'create', ephemeral: true }) },
    ],
    handler: async function (intent) {
      const sub = this.subcommands.find((s) => s.name === intent.subcommand);
      return sub.handler(intent);
    },
  });
  const directory = { async getPersonByDiscordId() { return { id: 'p1', display_name: 'A' }; } };
  const out = await dispatch(
    { commandName: 'team', options: {}, subcommand: 'list', discordUserId: '1' },
    { commands: new Map([['team', cmd]]), appContext: { directory } },
  );
  assert.equal(out.content, 'list');
});

test('dispatch: unknown/undefined non-DirectoryUnavailable authN error propagates', async () => {
  const directory = {
    async getPersonByDiscordId() { throw new Error('boom'); },
  };
  await assert.rejects(
    () => dispatch(
      { commandName: 'me', options: {}, discordUserId: '1' },
      { commands: new Map([['me', linkedCmd]]), appContext: { directory } },
    ),
    (e) => e instanceof Error && e.message === 'boom',
  );
});

test('dispatch: handler error is caught centrally with a generic reply', async () => {
  const cmd = defineCommand({
    name: 'boom',
    description: 'b',
    auth: 'public',
    handler: async () => { throw new Error('boom'); },
  });
  const out = await dispatch(
    { commandName: 'boom', options: {}, discordUserId: '1' },
    { commands: new Map([['boom', cmd]]), appContext: {} },
  );
  assert.match(out.content, /went wrong/i);
});

test('dispatch: admin subcommand denies a member', async () => {
  const cmd = defineCommand({
    name: 'team',
    description: 't',
    subcommands: [
      { name: 'create', auth: 'admin', handler: async () => ({ content: 'create', ephemeral: true }) },
    ],
    handler: async function (intent) {
      const sub = this.subcommands.find((s) => s.name === intent.subcommand);
      return sub.handler(intent);
    },
  });
  const directory = {
    async getPersonByDiscordId() { return { id: 'p1', display_name: 'A', access_level: 'member' }; },
  };
  const out = await dispatch(
    { commandName: 'team', options: {}, subcommand: 'create', discordUserId: '1' },
    { commands: new Map([['team', cmd]]), appContext: { directory } },
  );
  assert.match(out.content, /permission|allowed/i);
});

test('dispatch: auth-as-function is called with the intent and its return is the policy', async () => {
  let seenIntent = null;
  const cmd = defineCommand({
    name: 'team',
    description: 't',
    auth: (intent) => { seenIntent = intent; return 'public'; },
    handler: async () => ({ content: 'ran', ephemeral: true }),
  });
  const intent = { commandName: 'team', options: {}, discordUserId: '1' };
  const out = await dispatch(intent, { commands: new Map([['team', cmd]]), appContext: {} });
  assert.equal(seenIntent, intent);
  assert.equal(out.content, 'ran');
});

test('dispatch: auth-as-function returning nullish falls back to linked (fail-secure)', async () => {
  const cmd = defineCommand({
    name: 'team',
    description: 't',
    auth: () => null,
    handler: async () => ({ content: 'ran', ephemeral: true }),
  });
  const directory = { async getPersonByDiscordId() { return null; } };
  const out = await dispatch(
    { commandName: 'team', options: {}, discordUserId: '1' },
    { commands: new Map([['team', cmd]]), appContext: { directory } },
  );
  assert.ok(out.content.includes('link'));
});
