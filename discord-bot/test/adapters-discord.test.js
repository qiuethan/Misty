import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags } from 'discord.js';
import { defineCommand } from '../src/defineCommand.js';
import {
  interactionToIntent,
  payloadToDiscordReply,
  resolveEphemeral,
  wireDiscordClient,
} from '../src/adapters/discord.js';

// A minimal fake discord.js interaction that tracks the response lifecycle the
// way the real one does: deferReply() flips `deferred`, reply() flips `replied`.
function fakeInteraction({ commandName, subcommand = null, calls }) {
  const interaction = {
    commandName,
    user: { id: '1', username: 'alex' },
    deferred: false,
    replied: false,
    isChatInputCommand: () => true,
    options: {
      getString: () => null,
      getBoolean: () => null,
      getUser: () => null,
      getSubcommand: () => subcommand,
    },
    async deferReply(opts) {
      calls.push({ method: 'deferReply', opts });
      this.deferred = true;
    },
    async reply(payload) {
      calls.push({ method: 'reply', payload });
      this.replied = true;
    },
    async editReply(payload) {
      calls.push({ method: 'editReply', payload });
    },
    async followUp(payload) {
      calls.push({ method: 'followUp', payload });
    },
  };
  return interaction;
}

// Minimal EventEmitter-ish client stub capturing the interactionCreate handler.
function fakeClient() {
  let handler = null;
  return {
    on: (event, fn) => {
      if (event === 'interactionCreate') handler = fn;
    },
    emit: (interaction) => handler(interaction),
  };
}

const linkLike = defineCommand({
  name: 'link',
  description: 'x',
  options: [{ name: 'email', type: 'string', required: true, description: 'x' }],
  handler: async () => ({ content: 'ok', ephemeral: true }),
});

test('interactionToIntent extracts flat options', () => {
  const interaction = {
    commandName: 'link',
    user: { id: '1', username: 'alex' },
    options: {
      getString: (n) => (n === 'email' ? 'a@x' : null),
      getSubcommand: () => null,
    },
  };
  const intent = interactionToIntent(interaction, linkLike);
  assert.equal(intent.commandName, 'link');
  assert.equal(intent.options.email, 'a@x');
  assert.equal(intent.discordUserId, '1');
  assert.equal(intent.discordHandle, 'alex');
  assert.equal(intent.subcommand, null);
});

test('interactionToIntent extracts subcommand', () => {
  const teamLike = defineCommand({
    name: 'team',
    description: 't',
    subcommands: [
      { name: 'list', options: [], handler: async () => ({ content: 'l' }) },
      { name: 'create', options: [{ name: 'slug', type: 'string', required: true, description: 's' }], handler: async () => ({ content: 'c' }) },
    ],
    handler: async () => ({ content: '?' }),
  });
  const interaction = {
    commandName: 'team',
    user: { id: '1', username: 'alex' },
    options: {
      getString: (n) => (n === 'slug' ? 'ml' : null),
      getSubcommand: () => 'create',
    },
  };
  const intent = interactionToIntent(interaction, teamLike);
  assert.equal(intent.subcommand, 'create');
  assert.equal(intent.options.slug, 'ml');
});

test('payloadToDiscordReply converts content + ephemeral', () => {
  const out = payloadToDiscordReply({ content: 'hi', ephemeral: true });
  assert.equal(out.content, 'hi');
  assert.equal(out.flags, MessageFlags.Ephemeral);
});

test('payloadToDiscordReply passes embeds through', () => {
  const spec = { title: 'X', fields: [{ name: 'a', value: 'b' }] };
  const out = payloadToDiscordReply({ embeds: [spec], ephemeral: true });
  assert.equal(out.embeds.length, 1);
  // discord.js can accept plain objects; we don't need EmbedBuilder in the adapter
  // for basic titles/fields.
  assert.equal(out.embeds[0].title, 'X');
});

test('payloadToDiscordReply returns null for null/undefined payload', () => {
  assert.equal(payloadToDiscordReply(null), null);
  assert.equal(payloadToDiscordReply(undefined), null);
});

test('payloadToDiscordReply propagates empty-string content', () => {
  const out = payloadToDiscordReply({ content: '' });
  assert.equal(out.content, '');
});

test('resolveEphemeral falls back to command-level hint', () => {
  const cmd = defineCommand({
    name: 'whoami',
    description: 'x',
    ephemeral: true,
    handler: async () => ({ content: 'ok' }),
  });
  assert.equal(resolveEphemeral(cmd, null), true);
});

test('resolveEphemeral prefers the active subcommand hint', () => {
  const cmd = defineCommand({
    name: 'team',
    description: 'x',
    ephemeral: false,
    subcommands: [
      { name: 'roster', ephemeral: true, handler: async () => ({ content: 'ok' }) },
    ],
    handler: async () => ({ content: 'top' }),
  });
  assert.equal(resolveEphemeral(cmd, 'roster'), true);
  assert.equal(resolveEphemeral(cmd, null), false);
});

test('wireDiscordClient defers BEFORE running the handler (slow DB safe)', async () => {
  const calls = [];
  let handlerRan = false;
  let deferredWhenHandlerRan = null;
  const command = defineCommand({
    name: 'whoami',
    description: 'x',
    auth: 'public',
    ephemeral: true,
    handler: async () => {
      handlerRan = true;
      // Simulate a slow Neon cold-start query; capture defer state at this point.
      deferredWhenHandlerRan = calls.some((c) => c.method === 'deferReply');
      return { content: 'record', ephemeral: true };
    },
  });
  const commands = new Map([['whoami', command]]);
  const client = fakeClient();
  wireDiscordClient(client, { commands, appContext: {} });

  const interaction = fakeInteraction({ commandName: 'whoami', calls });
  await client.emit(interaction);

  assert.equal(handlerRan, true);
  assert.equal(deferredWhenHandlerRan, true, 'handler must run only AFTER deferReply');
  assert.equal(calls[0].method, 'deferReply', 'deferReply must be the very first call');
});

test('wireDiscordClient defers ephemerally per the resolved hint', async () => {
  const calls = [];
  const command = defineCommand({
    name: 'whoami',
    description: 'x',
    auth: 'public',
    ephemeral: true,
    handler: async () => ({ content: 'record' }),
  });
  const client = fakeClient();
  wireDiscordClient(client, { commands: new Map([['whoami', command]]), appContext: {} });

  await client.emit(fakeInteraction({ commandName: 'whoami', calls }));

  const defer = calls.find((c) => c.method === 'deferReply');
  assert.equal(defer.opts.flags, MessageFlags.Ephemeral);
});

test('wireDiscordClient edits the deferred reply with the payload', async () => {
  const calls = [];
  const command = defineCommand({
    name: 'whoami',
    description: 'x',
    auth: 'public',
    ephemeral: true,
    handler: async () => ({ content: 'the record' }),
  });
  const client = fakeClient();
  wireDiscordClient(client, { commands: new Map([['whoami', command]]), appContext: {} });

  await client.emit(fakeInteraction({ commandName: 'whoami', calls }));

  const edit = calls.find((c) => c.method === 'editReply');
  assert.ok(edit, 'a deferred reply should be delivered via editReply, not a second reply');
  assert.equal(edit.payload.content, 'the record');
});
