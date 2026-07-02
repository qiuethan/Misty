import {
  TeamExists,
  TeamNotFound,
  DirectoryUnavailable,
} from './directoryClient.js';

export const llmSafe = true;

const isoDateToday = () => new Date().toISOString().slice(0, 10);

export function createTeamService({ directory, now = isoDateToday } = {}) {
  async function createTeam({ slug, label, description }, _opts) {
    try {
      const team = await directory.createTeam({ slug, label, description });
      return { outcome: 'CREATED', team };
    } catch (e) {
      if (e instanceof TeamExists) return { outcome: 'SLUG_EXISTS', detail: e.detail };
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  async function listTeams({ activeOnly } = {}, _opts) {
    try {
      const teams = await directory.listTeams({ activeOnly });
      return { outcome: 'LISTED', teams };
    } catch (e) {
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  async function renameTeam({ slug, newLabel }, _opts) {
    try {
      const team = await directory.getTeamBySlug(slug);
      if (!team) return { outcome: 'TEAM_NOT_FOUND' };
      const updated = await directory.updateTeam(team.id, { label: newLabel });
      return { outcome: 'RENAMED', team: updated };
    } catch (e) {
      if (e instanceof TeamNotFound) return { outcome: 'TEAM_NOT_FOUND' };
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  return { createTeam, listTeams, renameTeam, _now: now };
}
