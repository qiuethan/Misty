import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags } from 'discord.js';
import * as link from '../src/commands/link.js';
import * as whoami from '../src/commands/whoami.js';
import * as seed from '../src/commands/seed.js';
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

test('whoami is linked-gated and renders the principal person', async () => {
  assert.equal(whoami.auth, 'linked');
  const interaction = fakeInteraction();
  await whoami.execute(interaction, { principal: { person: { display_name: 'Alex' } } });
  assert.match(interaction.replies[0].content, /Alex/);
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
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

test('seed is admin-gated and stable', () => {
  assert.equal(seed.auth, 'admin');
  assert.equal(seed.beta, false);
});

test('seed adapter passes options + caller into seedService and renders outcome', async () => {
  const interaction = seedInteraction({ email: 'new@utmist.ca', name: 'New Person', level: 'admin' });
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    seedService: {
      seedPerson: async (args, opts) => {
        assert.deepEqual(args, { email: 'new@utmist.ca', displayName: 'New Person', level: 'admin' });
        assert.equal(opts.caller.access_level, 'admin');
        return {
          outcome: 'SEEDED',
          person: { display_name: 'New Person', primary_email: 'new@utmist.ca', access_level: 'admin' },
        };
      },
    },
  };
  await seed.execute(interaction, ctx);
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
  assert.match(interaction.replies[0].content, /New Person/);
});

test('seed adapter defaults level to member when option missing', async () => {
  const interaction = seedInteraction({ email: 'a@utmist.ca', name: 'A' });
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    seedService: {
      seedPerson: async (args) => {
        assert.equal(args.level, 'member');
        return { outcome: 'SEEDED', person: { display_name: 'A', primary_email: 'a@utmist.ca', access_level: 'member' } };
      },
    },
  };
  await seed.execute(interaction, ctx);
  assert.match(interaction.replies[0].content, /A/);
});

test('registry includes seed', () => {
  assert.equal(commands.get('seed'), seed);
});
