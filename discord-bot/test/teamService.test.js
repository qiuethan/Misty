import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTeamService, llmSafe } from '../src/teamService.js';
import {
  TeamExists,
  TeamNotFound,
  MembershipInvalid,
  DirectoryUnavailable,
} from '../src/directoryClient.js';

const admin = { id: 'a', display_name: 'A', access_level: 'admin' };

test('llmSafe is true', () => {
  assert.equal(llmSafe, true);
});

test('createTeam returns CREATED on success', async () => {
  const svc = createTeamService({
    directory: {
      createTeam: async (args) => {
        assert.equal(args.slug, 'ml');
        assert.equal(args.label, 'ML');
        assert.equal(args.description, 'Machine Learning');
        return { id: 't1', slug: 'ml', label: 'ML' };
      },
    },
  });
  const res = await svc.createTeam(
    { slug: 'ml', label: 'ML', description: 'Machine Learning' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'CREATED');
  assert.equal(res.team.id, 't1');
});

test('createTeam returns SLUG_EXISTS on TeamExists', async () => {
  const svc = createTeamService({
    directory: {
      createTeam: async () => { throw new TeamExists('slug already exists'); },
    },
  });
  const res = await svc.createTeam({ slug: 'ml', label: 'ML' }, { caller: admin });
  assert.equal(res.outcome, 'SLUG_EXISTS');
  assert.equal(res.detail, 'slug already exists');
});

test('createTeam returns DIRECTORY_DOWN on DirectoryUnavailable', async () => {
  const svc = createTeamService({
    directory: {
      createTeam: async () => { throw new DirectoryUnavailable('down'); },
    },
  });
  const res = await svc.createTeam({ slug: 'ml', label: 'ML' }, { caller: admin });
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});

test('listTeams returns LISTED with teams array', async () => {
  const svc = createTeamService({
    directory: {
      listTeams: async ({ activeOnly }) => {
        assert.equal(activeOnly, true);
        return [{ id: 't1', slug: 'ml', label: 'ML' }];
      },
    },
  });
  const res = await svc.listTeams({ activeOnly: true }, { caller: admin });
  assert.equal(res.outcome, 'LISTED');
  assert.equal(res.teams.length, 1);
});

test('listTeams returns DIRECTORY_DOWN when directory is unavailable', async () => {
  const svc = createTeamService({
    directory: {
      listTeams: async () => { throw new DirectoryUnavailable('down'); },
    },
  });
  const res = await svc.listTeams({ activeOnly: true }, { caller: admin });
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});

test('renameTeam returns RENAMED after slug lookup + updateTeam', async () => {
  const svc = createTeamService({
    directory: {
      getTeamBySlug: async (slug) => {
        assert.equal(slug, 'ml');
        return { id: 't1', slug: 'ml', label: 'ML' };
      },
      updateTeam: async (teamId, patch) => {
        assert.equal(teamId, 't1');
        assert.deepEqual(patch, { label: 'Machine Learning Group' });
        return { id: 't1', slug: 'ml', label: 'Machine Learning Group' };
      },
    },
  });
  const res = await svc.renameTeam(
    { slug: 'ml', newLabel: 'Machine Learning Group' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'RENAMED');
  assert.equal(res.team.label, 'Machine Learning Group');
});

test('renameTeam returns TEAM_NOT_FOUND when slug does not resolve', async () => {
  const svc = createTeamService({
    directory: {
      getTeamBySlug: async () => null,
      updateTeam: async () => { throw new Error('should not be called'); },
    },
  });
  const res = await svc.renameTeam({ slug: 'missing', newLabel: 'X' }, { caller: admin });
  assert.equal(res.outcome, 'TEAM_NOT_FOUND');
});

test('renameTeam returns DIRECTORY_DOWN on outage during lookup', async () => {
  const svc = createTeamService({
    directory: {
      getTeamBySlug: async () => { throw new DirectoryUnavailable('down'); },
      updateTeam: async () => ({}),
    },
  });
  const res = await svc.renameTeam({ slug: 'ml', newLabel: 'X' }, { caller: admin });
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});

function mkDir(overrides = {}) {
  return {
    getPersonByDiscordId: async () => null,
    getTeamBySlug: async () => null,
    listMemberships: async () => [],
    createMembership: async () => ({ id: 'm1' }),
    endMembership: async () => ({ id: 'm1', ended_at: '2026-07-01' }),
    ...overrides,
  };
}

test('addMember returns USER_NOT_LINKED when snowflake does not resolve', async () => {
  const svc = createTeamService({ directory: mkDir() });
  const res = await svc.addMember(
    { discordSnowflake: '999', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'USER_NOT_LINKED');
});

test('addMember returns TEAM_NOT_FOUND when slug does not resolve', async () => {
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => ({ id: 'p1', display_name: 'A' }),
      getTeamBySlug: async () => null,
    }),
  });
  const res = await svc.addMember(
    { discordSnowflake: '123', teamSlug: 'missing' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'TEAM_NOT_FOUND');
});

test('addMember returns ALREADY_ON_TEAM when active membership exists', async () => {
  const person = { id: 'p1', display_name: 'A' };
  const team = { id: 't1', slug: 'ml', label: 'ML' };
  let created = false;
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => person,
      getTeamBySlug: async () => team,
      listMemberships: async (args) => {
        assert.equal(args.teamId, 't1');
        assert.equal(args.personId, 'p1');
        assert.equal(args.activeOnly, true);
        return [{ id: 'm-existing' }];
      },
      createMembership: async () => { created = true; return {}; },
    }),
  });
  const res = await svc.addMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'ALREADY_ON_TEAM');
  assert.equal(res.person, person);
  assert.equal(res.team, team);
  assert.equal(created, false);
});

test('addMember returns ADDED with role and admin flag forwarded', async () => {
  const person = { id: 'p1', display_name: 'A' };
  const team = { id: 't1', slug: 'ml', label: 'ML' };
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => person,
      getTeamBySlug: async () => team,
      listMemberships: async () => [],
      createMembership: async (args) => {
        assert.equal(args.personId, 'p1');
        assert.equal(args.teamId, 't1');
        assert.equal(args.roleKindId, 'lead');
        assert.equal(args.isTeamAdmin, true);
        return { id: 'm1', person_id: 'p1', team_id: 't1' };
      },
    }),
  });
  const res = await svc.addMember(
    { discordSnowflake: '123', teamSlug: 'ml', roleKindId: 'lead', isTeamAdmin: true },
    { caller: admin },
  );
  assert.equal(res.outcome, 'ADDED');
  assert.equal(res.membership.id, 'm1');
  assert.equal(res.person, person);
  assert.equal(res.team, team);
});

test('addMember returns DIRECTORY_DOWN on outage during person lookup', async () => {
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => { throw new DirectoryUnavailable('down'); },
    }),
  });
  const res = await svc.addMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});

test('addMember maps MembershipInvalid to ALREADY_ON_TEAM (defense-in-depth for API race)', async () => {
  const person = { id: 'p1', display_name: 'A' };
  const team = { id: 't1', slug: 'ml', label: 'ML' };
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => person,
      getTeamBySlug: async () => team,
      listMemberships: async () => [],
      createMembership: async () => { throw new MembershipInvalid('active membership already exists'); },
    }),
  });
  const res = await svc.addMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'ALREADY_ON_TEAM');
});

test('removeMember returns USER_NOT_LINKED when snowflake does not resolve', async () => {
  const svc = createTeamService({ directory: mkDir() });
  const res = await svc.removeMember(
    { discordSnowflake: '999', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'USER_NOT_LINKED');
});

test('removeMember returns TEAM_NOT_FOUND when slug does not resolve', async () => {
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => ({ id: 'p1', display_name: 'A' }),
      getTeamBySlug: async () => null,
    }),
  });
  const res = await svc.removeMember(
    { discordSnowflake: '123', teamSlug: 'missing' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'TEAM_NOT_FOUND');
});

test('removeMember returns NOT_ON_TEAM when there is no active membership', async () => {
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => ({ id: 'p1', display_name: 'A' }),
      getTeamBySlug: async () => ({ id: 't1', slug: 'ml', label: 'ML' }),
      listMemberships: async () => [],
    }),
  });
  const res = await svc.removeMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'NOT_ON_TEAM');
});

test('removeMember ends the active membership with injected now() and returns REMOVED', async () => {
  const person = { id: 'p1', display_name: 'A' };
  const team = { id: 't1', slug: 'ml', label: 'ML' };
  let endedWith = null;
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => person,
      getTeamBySlug: async () => team,
      listMemberships: async () => [{ id: 'm1', person_id: 'p1', team_id: 't1' }],
      endMembership: async (id, endedAt) => {
        endedWith = { id, endedAt };
        return { id, ended_at: endedAt };
      },
    }),
    now: () => '2026-07-01',
  });
  const res = await svc.removeMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'REMOVED');
  assert.equal(res.person, person);
  assert.equal(res.team, team);
  assert.deepEqual(endedWith, { id: 'm1', endedAt: '2026-07-01' });
});

test('removeMember returns DIRECTORY_DOWN on outage during team lookup', async () => {
  const svc = createTeamService({
    directory: mkDir({
      getPersonByDiscordId: async () => ({ id: 'p1', display_name: 'A' }),
      getTeamBySlug: async () => { throw new DirectoryUnavailable('down'); },
    }),
  });
  const res = await svc.removeMember(
    { discordSnowflake: '123', teamSlug: 'ml' },
    { caller: admin },
  );
  assert.equal(res.outcome, 'DIRECTORY_DOWN');
});
