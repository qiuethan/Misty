import { MessageFlags } from 'discord.js';
import { resolvePrincipal } from './auth/principal.js';
import { authorize } from './auth/policy.js';
import { DirectoryUnavailable } from './directoryClient.js';
import { authMessages } from './messages.js';

// --- Temporary shim (Task 2) ---
// The router still receives a discord.js `interaction` and still replies via
// `interaction.reply`/`followUp`. What changed: commands are now the neutral
// `defineCommand` shape (handler takes a plain intent, returns a
// `ReplyPayload`), so this shim translates between the two worlds. Task 3
// replaces this with a clean intent-based router and removes the shim.

async function safeReply(interaction, payload) {
  const dpayload = payloadToDiscord(payload);
  if (interaction.replied || interaction.deferred) {
    await interaction.followUp(dpayload).catch((e) => console.error('reply failed:', e.message));
  } else {
    await interaction.reply(dpayload).catch((e) => console.error('reply failed:', e.message));
  }
}

function payloadToDiscord(p) {
  const out = {};
  if (p.content) out.content = p.content;
  if (p.embeds) out.embeds = p.embeds; // discord.js accepts plain embed objects
  if (p.ephemeral) out.flags = MessageFlags.Ephemeral;
  return out;
}

function extractOptions(interaction, def) {
  const opts = {};
  const subcommand = def.subcommands.length
    ? interaction.options.getSubcommand(false)
    : null;
  const activeOptions = subcommand
    ? def.subcommands.find((s) => s.name === subcommand)?.options ?? []
    : def.options;
  for (const o of activeOptions) {
    if (o.type === 'string') opts[o.name] = interaction.options.getString(o.name);
    else if (o.type === 'boolean') opts[o.name] = interaction.options.getBoolean(o.name);
    else if (o.type === 'user') opts[o.name] = interaction.options.getUser(o.name);
  }
  return { options: opts, subcommand };
}

// The single Policy Enforcement Point: authenticate -> authorize -> dispatch.
// Command handlers never re-implement any of this.
export async function dispatchInteraction(interaction, { commands, appContext }) {
  const command = commands.get(interaction.commandName);
  if (!command) return;

  const { options, subcommand } = extractOptions(interaction, command);
  const activeAuth = subcommand
    ? command.subcommands.find((s) => s.name === subcommand)?.auth ?? command.auth
    : command.auth;
  const rawAuth = activeAuth;
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
    const payload = await command.handler({
      options,
      subcommand,
      principal,
      ctx: appContext,
      discordUserId: interaction.user.id,
      discordHandle: interaction.user.username,
    });
    await safeReply(interaction, payload);
  } catch (err) {
    console.error(`Command ${interaction.commandName} failed:`, err);
    await safeReply(interaction, authMessages.internalError());
  }
}
