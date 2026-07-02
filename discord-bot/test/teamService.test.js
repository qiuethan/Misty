import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTeamService, llmSafe } from '../src/teamService.js';
import {
  TeamExists,
  TeamNotFound,
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
