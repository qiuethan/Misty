const HELPER_MAX_TOKENS = 1024;

// Best-effort: resolve the asker's active team labels for the system prompt.
// A directory hiccup must not fail the answer — fall back to name-only.
async function resolveTeamLabels(directory, personId) {
  try {
    const memberships = await directory.listMemberships({ personId, activeOnly: true });
    // One listTeams round-trip instead of one getTeam per membership (N+1).
    // Fetch ALL teams (activeOnly: false) to match getTeam's active-agnostic
    // behavior: an active membership on an inactive team still resolved to a
    // label under the old code. Preserve membership order and the getTeam-404
    // fallback — a team_id that genuinely doesn't exist is absent from the map,
    // resolves to undefined, and is dropped, exactly as getTeam returned null.
    const teams = await directory.listTeams({ activeOnly: false });
    const byId = new Map(teams.map((t) => [t.id, t]));
    return memberships
      .map((m) => byId.get(m.team_id))
      .filter(Boolean)
      .map((t) => t.label)
      .filter(Boolean);
  } catch {
    return [];
  }
}

function buildSystemPrompt(displayName, teamLabels) {
  let s = `You are UTMIST's internal helper bot. Answer concisely and helpfully. You are helping ${displayName}`;
  if (teamLabels.length) s += `, who is on ${teamLabels.join(', ')}`;
  s += '.';
  return s;
}

// Surface-agnostic: takes an already-assembled neutral messages array and the
// authenticated principal, injects identity/team context, and returns the
// completion text. No discord.js.
export function createHelperService({ llmClient, directory }) {
  return {
    async answer({ messages, principal }) {
      const person = principal.person;
      const teamLabels = await resolveTeamLabels(directory, person.id);
      const system = buildSystemPrompt(person.display_name, teamLabels);
      const { content } = await llmClient.chat({ messages, system, maxTokens: HELPER_MAX_TOKENS });
      return { content };
    },
  };
}
