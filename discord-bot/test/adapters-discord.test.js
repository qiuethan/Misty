import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags } from 'discord.js';
import { defineCommand } from '../src/defineCommand.js';
import { interactionToIntent, payloadToDiscordReply } from '../src/adapters/discord.js';

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
