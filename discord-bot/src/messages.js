export const authMessages = {
  unavailable: () =>
    "I can't verify you right now — the directory is unavailable. Please try again shortly.",
  denied: (reason) =>
    reason === 'not_linked'
      ? 'You need to link your account first. Run `/link` to identify yourself, then try again.'
      : "You're not allowed to do that.",
  internalError: () => 'Something went wrong. Please try again.',
};
