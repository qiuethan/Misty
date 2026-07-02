import { MessageFlags } from 'discord.js';
import { resolvePrincipal } from './auth/principal.js';
import { authorize } from './auth/policy.js';
import { DirectoryUnavailable } from './directoryClient.js';
import { authMessages } from './messages.js';

async function safeReply(interaction, content) {
  const payload = { content, flags: MessageFlags.Ephemeral };
  if (interaction.replied || interaction.deferred) {
    await interaction.followUp(payload).catch((e) => console.error('reply failed:', e.message));
  } else {
    await interaction.reply(payload).catch((e) => console.error('reply failed:', e.message));
  }
}

// The single Policy Enforcement Point: authenticate -> authorize -> dispatch.
// Command handlers never re-implement any of this.
export async function dispatchInteraction(interaction, { commands, appContext }) {
  const command = commands.get(interaction.commandName);
  if (!command) return;

  const rawAuth = command.auth;
  const resolvedAuth = typeof rawAuth === 'function' ? rawAuth(interaction) : rawAuth;
  const policy = resolvedAuth ?? 'linked'; // fail-secure default

  // --- Authentication ---
  let principal = null;
  if (policy !== 'public') {
    try {
      principal = await resolvePrincipal(appContext.directory, interaction.user.id);
    } catch (e) {
      if (e instanceof DirectoryUnavailable) {
        await safeReply(interaction, authMessages.unavailable()); // fail closed
        return;
      }
      throw e;
    }
  }

  // --- Authorization ---
  const decision = authorize(policy, principal);
  if (!decision.ok) {
    await safeReply(interaction, authMessages.denied(decision.reason));
    return;
  }

  // --- Dispatch ---
  try {
    await command.execute(interaction, { ...appContext, principal });
  } catch (err) {
    console.error(`Command ${interaction.commandName} failed:`, err);
    await safeReply(interaction, authMessages.internalError());
  }
}
