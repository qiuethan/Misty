export const authMessages = {
  unavailable: () =>
    "I can't verify you right now — the directory is unavailable. Please try again shortly.",
  denied: (reason) =>
    reason === 'not_linked'
      ? 'You need to link your account first. Run `/link` to identify yourself, then try again.'
      : reason === 'forbidden'
        ? "You don't have permission to do that."
        : "You're not allowed to do that.",
  internalError: () => 'Something went wrong. Please try again.',
};

export function renderLinkResult(result) {
  switch (result.outcome) {
    case 'LINKED':
      return `✅ Linked! You're now identified as **${result.person.display_name}**.`;
    case 'NOT_A_MEMBER':
      return "I couldn't find that email in the directory. Ask an exec to add you, then run `/link` again.";
    case 'ALREADY_LINKED':
      return `That link couldn't be created: ${result.detail}`;
    case 'DIRECTORY_DOWN':
      return 'The directory is temporarily unavailable. Please try again shortly.';
    default:
      return 'Something went wrong. Please try again.';
  }
}

export function buildWhoamiEmbed(person, identifiers) {
  return {
    title: person.display_name,
    fields: [
      { name: 'Email', value: person.primary_email },
      { name: 'Access level', value: person.access_level },
      { name: 'Status', value: person.active ? 'Active' : 'Inactive' },
      { name: 'Identities', value: formatIdentities(identifiers) },
    ],
  };
}

function formatIdentities(identifiers) {
  if (identifiers === null) return '_(unavailable)_';
  if (identifiers.length === 0) return '_(none)_';
  const sorted = [...identifiers].sort((a, b) => a.provider.localeCompare(b.provider));
  return sorted
    .map((i) => (i.handle ? `${i.provider}: ${i.handle} (${i.external_id})` : `${i.provider}: ${i.external_id}`))
    .join('\n');
}

export function renderSeedResult(result) {
  switch (result.outcome) {
    case 'SEEDED':
      return `✅ Added **${result.person.display_name}** (${result.person.primary_email}) as ${result.person.access_level}. They can now \`/link\`.`;
    case 'EXISTS':
      return `That email is already in the directory: ${result.detail}`;
    case 'ESCALATION_DENIED':
      return `You can only grant levels at or below your own (${result.callerLevel}).`;
    case 'DIRECTORY_DOWN':
      return 'The directory is temporarily unavailable. Please try again shortly.';
    default:
      return 'Something went wrong. Please try again.';
  }
}

const FALLBACK = 'Something went wrong. Please try again.';
const DIRECTORY_DOWN_MSG = 'The directory is temporarily unavailable. Please try again shortly.';
const USER_NOT_LINKED_MSG =
  "That user hasn't linked their directory account yet. Ask them to run `/link` first, then try again.";

export function renderCreateTeamResult(result) {
  switch (result.outcome) {
    case 'CREATED':
      return `✅ Created team **${result.team.label}** (\`${result.team.slug}\`).`;
    case 'SLUG_EXISTS':
      return `A team with that slug already exists: ${result.detail}`;
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderListTeamsResult(result) {
  switch (result.outcome) {
    case 'LISTED':
      if (result.teams.length === 0) return 'There are no teams yet.';
      return result.teams
        .map((t) => `• **${t.label}** (\`${t.slug}\`)`)
        .join('\n');
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderRenameTeamResult(result) {
  switch (result.outcome) {
    case 'RENAMED':
      return `✅ Renamed to **${result.team.label}** (\`${result.team.slug}\`).`;
    case 'TEAM_NOT_FOUND':
      return "There's no team with that slug.";
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderAddMemberResult(result) {
  switch (result.outcome) {
    case 'ADDED':
      return `✅ Added **${result.person.display_name}** to **${result.team.label}**.`;
    case 'USER_NOT_LINKED':
      return USER_NOT_LINKED_MSG;
    case 'TEAM_NOT_FOUND':
      return "There's no team with that slug.";
    case 'ALREADY_ON_TEAM':
      return `**${result.person.display_name}** is already on **${result.team.label}**.`;
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderRemoveMemberResult(result) {
  switch (result.outcome) {
    case 'REMOVED':
      return `✅ Removed **${result.person.display_name}** from **${result.team.label}**.`;
    case 'USER_NOT_LINKED':
      return USER_NOT_LINKED_MSG;
    case 'TEAM_NOT_FOUND':
      return "There's no team with that slug.";
    case 'NOT_ON_TEAM':
      return `**${result.person.display_name}** is not on **${result.team.label}**.`;
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderRosterResult(result) {
  switch (result.outcome) {
    case 'ROSTER': {
      const header = `**${result.team.label}** (\`${result.team.slug}\`)`;
      if (result.members.length === 0) return `${header}\n_No members yet._`;
      const lines = result.members.map((m) => {
        const adminTag = m.is_team_admin ? ' — team admin' : '';
        return `• **${m.person.display_name}** — ${m.role_kind_id}${adminTag}`;
      });
      return [header, ...lines].join('\n');
    }
    case 'TEAM_NOT_FOUND':
      return "There's no team with that slug.";
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}

export function renderMyTeamsResult(result) {
  switch (result.outcome) {
    case 'MY_TEAMS':
      if (result.memberships.length === 0) return "You're not on any team yet.";
      return result.memberships
        .map((m) => {
          const adminTag = m.is_team_admin ? ' — team admin' : '';
          return `• **${m.team.label}** (\`${m.team.slug}\`) — ${m.role_kind_id}${adminTag}`;
        })
        .join('\n');
    case 'DIRECTORY_DOWN':
      return DIRECTORY_DOWN_MSG;
    default:
      return FALLBACK;
  }
}
