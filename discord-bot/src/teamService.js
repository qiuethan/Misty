import {
  TeamExists,
  TeamNotFound,
  MembershipInvalid,
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

  async function addMember(
    { discordSnowflake, teamSlug, roleKindId, isTeamAdmin },
    _opts,
  ) {
    try {
      const person = await directory.getPersonByDiscordId(discordSnowflake);
      if (!person) return { outcome: 'USER_NOT_LINKED' };
      const team = await directory.getTeamBySlug(teamSlug);
      if (!team) return { outcome: 'TEAM_NOT_FOUND' };
      const existing = await directory.listMemberships({
        teamId: team.id,
        personId: person.id,
        activeOnly: true,
      });
      if (existing.length > 0) return { outcome: 'ALREADY_ON_TEAM', person, team };
      try {
        const membership = await directory.createMembership({
          personId: person.id,
          teamId: team.id,
          roleKindId,
          isTeamAdmin,
        });
        return { outcome: 'ADDED', membership, person, team };
      } catch (e) {
        if (e instanceof MembershipInvalid) {
          return { outcome: 'ALREADY_ON_TEAM', person, team };
        }
        throw e;
      }
    } catch (e) {
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  async function removeMember({ discordSnowflake, teamSlug }, _opts) {
    try {
      const person = await directory.getPersonByDiscordId(discordSnowflake);
      if (!person) return { outcome: 'USER_NOT_LINKED' };
      const team = await directory.getTeamBySlug(teamSlug);
      if (!team) return { outcome: 'TEAM_NOT_FOUND' };
      const active = await directory.listMemberships({
        teamId: team.id,
        personId: person.id,
        activeOnly: true,
      });
      if (active.length === 0) return { outcome: 'NOT_ON_TEAM', person, team };
      await directory.endMembership(active[0].id, now());
      return { outcome: 'REMOVED', person, team };
    } catch (e) {
      if (e instanceof DirectoryUnavailable) return { outcome: 'DIRECTORY_DOWN' };
      throw e;
    }
  }

  return { createTeam, listTeams, renameTeam, addMember, removeMember, _now: now };
}
