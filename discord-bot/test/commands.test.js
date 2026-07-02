import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags, EmbedBuilder } from 'discord.js';
import * as link from '../src/commands/link.js';
import * as whoami from '../src/commands/whoami.js';
import * as seed from '../src/commands/seed.js';
import { PersonExists, DirectoryUnavailable } from '../src/directoryClient.js';
import { commands, partitionCommands } from '../src/commands/index.js';

function fakeInteraction({ email } = {}) {
  const replies = [];
  return {
    user: { id: '123', username: 'alex' },
    options: { getString: () => email },
    reply: async (payload) => { replies.push(payload); },
    replies,
  };
}

test('link is public and links via linkService', async () => {
  assert.equal(link.auth, 'public');
  const interaction = fakeInteraction({ email: 'alex@utmist.ca' });
  const ctx = {
    linkService: {
      linkByEmail: async (args) => {
        assert.equal(args.email, 'alex@utmist.ca');
        assert.equal(args.discordUserId, '123');
        assert.equal(args.discordHandle, 'alex');
        return { outcome: 'LINKED', person: { display_name: 'Alex' } };
      },
    },
  };
  await link.execute(interaction, ctx);
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
  assert.match(interaction.replies[0].content, /Alex/);
});

test('whoami is linked-gated and stable', () => {
  assert.equal(whoami.auth, 'linked');
  assert.equal(whoami.beta, false);
});

test('whoami replies with an ephemeral embed carrying person + identifiers', async () => {
  const person = { id: 'p1', display_name: 'Alex', primary_email: 'alex@utmist.ca', access_level: 'admin', active: true };
  const identifiers = [{ provider: 'discord', external_id: '123', handle: 'alex' }];
  const interaction = fakeInteraction();
  const ctx = {
    principal: { person },
    directory: { listIdentifiers: async (id) => { assert.equal(id, 'p1'); return identifiers; } },
  };
  await whoami.execute(interaction, ctx);
  const reply = interaction.replies[0];
  assert.equal(reply.flags, MessageFlags.Ephemeral);
  assert.equal(reply.embeds.length, 1);
  assert.ok(reply.embeds[0] instanceof EmbedBuilder);
  const data = reply.embeds[0].data;
  assert.equal(data.title, 'Alex');
  const byName = Object.fromEntries(data.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Email'], 'alex@utmist.ca');
  assert.equal(byName['Access level'], 'admin');
  assert.equal(byName['Status'], 'Active');
  assert.match(byName['Identities'], /discord: alex/);
});

test('whoami degrades gracefully when identifiers fetch fails', async () => {
  const person = { id: 'p1', display_name: 'Alex', primary_email: 'alex@utmist.ca', access_level: 'member', active: true };
  const interaction = fakeInteraction();
  const ctx = {
    principal: { person },
    directory: { listIdentifiers: async () => { throw new DirectoryUnavailable('down'); } },
  };
  await whoami.execute(interaction, ctx);
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
  const data = interaction.replies[0].embeds[0].data;
  const byName = Object.fromEntries(data.fields.map((f) => [f.name, f.value]));
  assert.equal(byName['Identities'], '_(unavailable)_');
});

test('whoami rethrows non-DirectoryUnavailable errors from listIdentifiers', async () => {
  const person = { id: 'p1', display_name: 'Alex', primary_email: 'alex@utmist.ca', access_level: 'member', active: true };
  const interaction = fakeInteraction();
  const ctx = {
    principal: { person },
    directory: { listIdentifiers: async () => { throw new Error('boom'); } },
  };
  await assert.rejects(() => whoami.execute(interaction, ctx), /boom/);
  assert.equal(interaction.replies.length, 0);
});

test('registry contains both commands keyed by name', () => {
  assert.equal(commands.get('link'), link);
  assert.equal(commands.get('whoami'), whoami);
});

test('partitionCommands splits stable (global) from beta (test-guild only)', () => {
  const a = { data: { name: 'a' } }; // no beta flag → stable
  const b = { data: { name: 'b' }, beta: false }; // explicit stable
  const c = { data: { name: 'c' }, beta: true }; // beta
  const { stable, beta } = partitionCommands([a, b, c]);
  assert.deepEqual(stable, [a, b]);
  assert.deepEqual(beta, [c]);
});

test('current commands are all stable (registered globally, none beta-exclusive)', () => {
  const { stable, beta } = partitionCommands([...commands.values()]);
  assert.equal(beta.length, 0);
  assert.equal(stable.length, commands.size);
  assert.equal(link.beta, false);
  assert.equal(whoami.beta, false);
});

function seedInteraction({ email, name, level } = {}) {
  const replies = [];
  return {
    user: { id: '123', username: 'admin' },
    options: { getString: (k) => ({ email, name, level }[k]) },
    reply: async (payload) => { replies.push(payload); },
    replies,
  };
}

const adminCtx = (directory) => ({ principal: { person: { access_level: 'admin' } }, directory });

test('seed is admin-gated and stable', () => {
  assert.equal(seed.auth, 'admin');
  assert.equal(seed.beta, false);
});

test('seed creates a member and replies ephemerally', async () => {
  const interaction = seedInteraction({ email: 'new@utmist.ca', name: 'New Person' });
  const directory = {
    createPerson: async (args) => {
      assert.equal(args.primaryEmail, 'new@utmist.ca');
      assert.equal(args.accessLevel, 'member');
      return { display_name: 'New Person', primary_email: 'new@utmist.ca', access_level: 'member' };
    },
  };
  await seed.execute(interaction, adminCtx(directory));
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
  assert.match(interaction.replies[0].content, /New Person/);
});

test('escalation guard: admin cannot grant superuser, and no create is attempted', async () => {
  let called = false;
  const interaction = seedInteraction({ email: 'x@utmist.ca', name: 'X', level: 'superuser' });
  const directory = { createPerson: async () => { called = true; return {}; } };
  await seed.execute(interaction, adminCtx(directory));
  assert.equal(called, false);
  assert.match(interaction.replies[0].content, /at or below your own/i);
});

test('seed surfaces PersonExists', async () => {
  const interaction = seedInteraction({ email: 'dup@utmist.ca', name: 'Dup' });
  const directory = { createPerson: async () => { throw new PersonExists('primary_email already exists'); } };
  await seed.execute(interaction, adminCtx(directory));
  assert.match(interaction.replies[0].content, /already/i);
});

test('seed surfaces directory outage', async () => {
  const interaction = seedInteraction({ email: 'd@utmist.ca', name: 'D' });
  const directory = { createPerson: async () => { throw new DirectoryUnavailable('down'); } };
  await seed.execute(interaction, adminCtx(directory));
  assert.match(interaction.replies[0].content, /unavailable|try again/i);
});

test('registry includes seed', () => {
  assert.equal(commands.get('seed'), seed);
});

test('admin can grant admin (equal rank is allowed)', async () => {
  const interaction = seedInteraction({ email: 'a@utmist.ca', name: 'A', level: 'admin' });
  let called = false;
  const directory = {
    createPerson: async () => {
      called = true;
      return { display_name: 'A', primary_email: 'a@utmist.ca', access_level: 'admin' };
    },
  };
  await seed.execute(interaction, adminCtx(directory));
  assert.equal(called, true);
  assert.match(interaction.replies[0].content, /A/);
});
