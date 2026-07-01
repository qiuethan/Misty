export const authMessages = {
  unavailable: () =>
    "I can't verify you right now — the directory is unavailable. Please try again shortly.",
  denied: (reason) =>
    reason === 'not_linked'
      ? 'You need to link your account first. Run `/link` to identify yourself, then try again.'
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

export function renderWhoami(person) {
  return `You're identified as **${person.display_name}**.`;
}
