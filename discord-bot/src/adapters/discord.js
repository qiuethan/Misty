import { MessageFlags } from 'discord.js';
import { dispatch } from '../router.js';

// The ONLY module (aside from src/index.js and src/registerCommands.js) that
// imports from discord.js. Everything else — router, commands, services —
// stays surface-agnostic.

function extractOptions(interaction, activeOptions) {
  const options = {};
  for (const o of activeOptions) {
    if (o.type === 'string') options[o.name] = interaction.options.getString(o.name);
    else if (o.type === 'boolean') options[o.name] = interaction.options.getBoolean(o.name);
    else if (o.type === 'user') options[o.name] = interaction.options.getUser(o.name);
    // extend for other types as they appear
  }
  return options;
}

export function interactionToIntent(interaction, command) {
  const subcommand = command.subcommands.length
    ? interaction.options.getSubcommand(false)
    : null;
  const activeOptions = subcommand
    ? command.subcommands.find((s) => s.name === subcommand)?.options ?? []
    : command.options;
  return {
    commandName: interaction.commandName,
    options: extractOptions(interaction, activeOptions),
    subcommand,
    discordUserId: interaction.user.id,
    discordHandle: interaction.user.username,
  };
}

export function payloadToDiscordReply(payload) {
  if (!payload) return null;
  const out = {};
  if (payload.content) out.content = payload.content;
  if (payload.embeds) out.embeds = payload.embeds;
  if (payload.ephemeral) out.flags = MessageFlags.Ephemeral;
  return out;
}

async function safeReply(interaction, payload) {
  const dpayload = payloadToDiscordReply(payload);
  if (!dpayload) return;
  const method = interaction.replied || interaction.deferred ? 'followUp' : 'reply';
  await interaction[method](dpayload).catch((e) =>
    console.error('reply failed:', e.message),
  );
}

export function wireDiscordClient(client, { commands, appContext }) {
  client.on('interactionCreate', async (interaction) => {
    if (!interaction.isChatInputCommand()) return;
    const command = commands.get(interaction.commandName);
    if (!command) return;
    try {
      const intent = interactionToIntent(interaction, command);
      const payload = await dispatch(intent, { commands, appContext });
      await safeReply(interaction, payload);
    } catch (err) {
      console.error('Unhandled interaction error:', err);
    }
  });
}
