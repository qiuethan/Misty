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
    case 'DIRECTORY_DOWN':
      return 'The directory is temporarily unavailable. Please try again shortly.';
    default:
      return 'Something went wrong. Please try again.';
  }
}
