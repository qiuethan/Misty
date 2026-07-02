import { resolvePrincipal } from './auth/principal.js';
import { authorize } from './auth/policy.js';
import { DirectoryUnavailable } from './directoryClient.js';
import { authMessages } from './messages.js';

// The single Policy Enforcement Point: authenticate -> authorize -> dispatch.
// Command handlers never re-implement any of this.
//
// Surface-agnostic: takes a plain `intent` object (not a discord.js
// interaction) and returns a `ReplyPayload | null`. The caller (a Discord
// adapter, a web adapter, etc.) is responsible for turning the payload into
// whatever the surface needs, and for handling `null` (unknown command).
export async function dispatch(intent, { commands, appContext }) {
  const command = commands.get(intent.commandName);
  if (!command) return null;

  const activeSubcommand = intent.subcommand
    ? command.subcommands.find((s) => s.name === intent.subcommand)
    : null;
  const rawAuth = activeSubcommand?.auth ?? command.auth;
  const resolvedAuth = typeof rawAuth === 'function' ? rawAuth(intent) : rawAuth;
  const policy = resolvedAuth ?? 'linked'; // fail-secure default

  // --- Authentication ---
  let principal = null;
  if (policy !== 'public') {
    try {
      principal = await resolvePrincipal(appContext.directory, intent.discordUserId);
    } catch (e) {
      if (e instanceof DirectoryUnavailable) return authMessages.unavailable(); // fail closed
      throw e;
    }
  }

  // --- Authorization ---
  const decision = authorize(policy, principal);
  if (!decision.ok) return authMessages.denied(decision.reason);

  // --- Dispatch ---
  try {
    return await command.handler({
      options: intent.options ?? {},
      subcommand: intent.subcommand ?? null,
      principal,
      ctx: appContext,
      discordUserId: intent.discordUserId,
      discordHandle: intent.discordHandle,
    });
  } catch (err) {
    console.error(`Command ${intent.commandName} failed:`, err);
    return authMessages.internalError();
  }
}
