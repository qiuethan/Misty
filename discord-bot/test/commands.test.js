import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageFlags, EmbedBuilder } from 'discord.js';
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

test('link and whoami are stable (registered globally, not beta-exclusive)', () => {
  const { stable } = partitionCommands([...commands.values()]);
  assert.ok(stable.includes(link));
  assert.ok(stable.includes(whoami));
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

import * as teamCmd from '../src/commands/team.js';
import * as myTeamsCmd from '../src/commands/my-teams.js';

function teamInteraction({ subcommand, ...options }) {
  const replies = [];
  return {
    user: { id: '123', username: 'admin' },
    options: {
      getSubcommand: () => subcommand,
      getString: (k) => options[k] ?? null,
      getBoolean: (k) => (k in options ? options[k] : null),
      getUser: (k) => options[k] ?? null,
    },
    reply: async (payload) => { replies.push(payload); },
    replies,
  };
}

test('/team is beta and its auth function returns per-subcommand policy', () => {
  assert.equal(teamCmd.beta, true);
  assert.equal(typeof teamCmd.auth, 'function');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'create' } }), 'admin');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'add' } }), 'admin');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'remove' } }), 'admin');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'rename' } }), 'admin');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'list' } }), 'linked');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'roster' } }), 'linked');
  assert.equal(teamCmd.auth({ options: { getSubcommand: () => 'nonsense' } }), 'linked');
});

test('/team create dispatches teamService.createTeam with options and caller', async () => {
  const interaction = teamInteraction({
    subcommand: 'create', slug: 'ml', label: 'ML', description: 'Machine Learning',
  });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    teamService: {
      createTeam: async (args, opts) => {
        seen = { args, opts };
        return { outcome: 'CREATED', team: { slug: 'ml', label: 'ML' } };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.deepEqual(seen.args, { slug: 'ml', label: 'ML', description: 'Machine Learning' });
  assert.equal(seen.opts.caller.access_level, 'admin');
  assert.match(interaction.replies[0].content, /ML|ml/);
  assert.equal(interaction.replies[0].flags, MessageFlags.Ephemeral);
});

test('/team list defaults active_only to true and calls teamService.listTeams', async () => {
  const interaction = teamInteraction({ subcommand: 'list' });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'member' } },
    teamService: {
      listTeams: async (args, opts) => {
        seen = { args, opts };
        return { outcome: 'LISTED', teams: [] };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.equal(seen.args.activeOnly, true);
  assert.match(interaction.replies[0].content, /no teams/i);
});

test('/team list forwards active_only=false when explicitly provided', async () => {
  const interaction = teamInteraction({ subcommand: 'list', active_only: false });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'member' } },
    teamService: {
      listTeams: async (args) => { seen = args; return { outcome: 'LISTED', teams: [] }; },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.equal(seen.activeOnly, false);
});

test('/team rename dispatches renameTeam', async () => {
  const interaction = teamInteraction({ subcommand: 'rename', slug: 'ml', new_label: 'New ML' });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    teamService: {
      renameTeam: async (args) => {
        seen = args;
        return { outcome: 'RENAMED', team: { slug: 'ml', label: 'New ML' } };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.deepEqual(seen, { slug: 'ml', newLabel: 'New ML' });
  assert.match(interaction.replies[0].content, /New ML/);
});

test('/team add dispatches addMember using the mentioned user snowflake', async () => {
  const interaction = teamInteraction({
    subcommand: 'add', user: { id: '555' }, team: 'ml', role: 'lead', team_admin: true,
  });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    teamService: {
      addMember: async (args) => {
        seen = args;
        return {
          outcome: 'ADDED',
          person: { display_name: 'Alex' },
          team: { label: 'ML' },
          membership: { id: 'm1' },
        };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.deepEqual(seen, {
    discordSnowflake: '555', teamSlug: 'ml', roleKindId: 'lead', isTeamAdmin: true,
  });
  assert.match(interaction.replies[0].content, /Alex/);
});

test('/team add omits role/team_admin when not provided', async () => {
  const interaction = teamInteraction({
    subcommand: 'add', user: { id: '555' }, team: 'ml',
  });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    teamService: {
      addMember: async (args) => {
        seen = args;
        return {
          outcome: 'ADDED',
          person: { display_name: 'Alex' },
          team: { label: 'ML' },
          membership: { id: 'm1' },
        };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.equal(seen.roleKindId, undefined);
  assert.equal(seen.isTeamAdmin, undefined);
});

test('/team remove dispatches removeMember using the mentioned user snowflake', async () => {
  const interaction = teamInteraction({ subcommand: 'remove', user: { id: '555' }, team: 'ml' });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'admin' } },
    teamService: {
      removeMember: async (args) => {
        seen = args;
        return { outcome: 'REMOVED', person: { display_name: 'Alex' }, team: { label: 'ML' } };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.deepEqual(seen, { discordSnowflake: '555', teamSlug: 'ml' });
  assert.match(interaction.replies[0].content, /Alex/);
});

test('/team roster dispatches getRoster', async () => {
  const interaction = teamInteraction({ subcommand: 'roster', team: 'ml' });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'member' } },
    teamService: {
      getRoster: async (args) => {
        seen = args;
        return {
          outcome: 'ROSTER',
          team: { slug: 'ml', label: 'ML' },
          members: [{ person: { display_name: 'Alex' }, role_kind_id: 'member', is_team_admin: false }],
        };
      },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.equal(seen.teamSlug, 'ml');
  assert.match(interaction.replies[0].content, /Alex/);
});

test('/team roster forwards as_of when provided', async () => {
  const interaction = teamInteraction({ subcommand: 'roster', team: 'ml', as_of: '2026-01-01' });
  let seen = null;
  const ctx = {
    principal: { person: { access_level: 'member' } },
    teamService: {
      getRoster: async (args) => { seen = args; return { outcome: 'ROSTER', team: { slug: 'ml', label: 'ML' }, members: [] }; },
    },
  };
  await teamCmd.execute(interaction, ctx);
  assert.equal(seen.asOf, '2026-01-01');
});

test('/my-teams is linked-gated, beta, and dispatches getMyTeams with caller person id', async () => {
  assert.equal(myTeamsCmd.auth, 'linked');
  assert.equal(myTeamsCmd.beta, true);
  const interaction = teamInteraction({ subcommand: 'x' }); // no options used
  let seen = null;
  const ctx = {
    principal: { person: { id: 'p1', display_name: 'Alex', access_level: 'member' } },
    teamService: {
      getMyTeams: async (args) => { seen = args; return { outcome: 'MY_TEAMS', memberships: [] }; },
    },
  };
  await myTeamsCmd.execute(interaction, ctx);
  assert.equal(seen.personId, 'p1');
  assert.match(interaction.replies[0].content, /not on any/i);
});

test('registry includes team and my-teams', () => {
  assert.equal(commands.get('team'), teamCmd);
  assert.equal(commands.get('my-teams'), myTeamsCmd);
});

test('team and my-teams are the only beta-channel commands', () => {
  const { stable, beta } = partitionCommands([...commands.values()]);
  assert.deepEqual(new Set(beta.map((c) => c.data.name)), new Set(['team', 'my-teams']));
  assert.equal(stable.length, commands.size - 2);
});
