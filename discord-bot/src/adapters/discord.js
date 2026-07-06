import { MessageFlags } from 'discord.js';
import { dispatch, dispatchAutocomplete } from '../router.js';
import { authMessages } from '../messages.js';
import { resolvePrincipal } from '../auth/principal.js';
import { authorize } from '../auth/policy.js';
import { DirectoryUnavailable } from '../directoryClient.js';

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

export function interactionToAutocompleteIntent(interaction) {
  const focused = interaction.options.getFocused(true); // { name, value, ... }
  return {
    commandName: interaction.commandName,
    subcommand: interaction.options.getSubcommand(false),
    focusedOption: focused.name,
    typed: focused.value ?? '',
    discordUserId: interaction.user.id,
  };
}

export function payloadToDiscordReply(payload) {
  if (!payload) return null;
  const out = {};
  if (payload.content !== undefined) out.content = payload.content;
  if (payload.embeds) out.embeds = payload.embeds;
  if (payload.ephemeral) out.flags = MessageFlags.Ephemeral;
  return out;
}

// Resolve the visibility hint for an interaction BEFORE the handler runs, so we
// can defer with the right ephemerality. Mirrors the router's auth resolution:
// an active subcommand's hint wins, otherwise the command-level hint, otherwise
// fail-safe to ephemeral (private).
export function resolveEphemeral(command, subcommandName) {
  const sub = subcommandName
    ? command.subcommands.find((s) => s.name === subcommandName)
    : null;
  return sub?.ephemeral ?? command.ephemeral ?? true;
}

async function safeReply(interaction, payload) {
  const dpayload = payloadToDiscordReply(payload);
  if (!dpayload) {
    // Nothing to say. If we deferred, clear the "thinking…" state so the user
    // isn't left staring at a spinner.
    if (interaction.deferred && !interaction.replied) {
      await interaction
        .deleteReply()
        .catch((e) => console.error('deleteReply failed:', e.message));
    }
    return;
  }

  // After deferReply(), the first response must edit the deferred message.
  // Ephemerality was already locked in at defer time, so editReply ignores the
  // ephemeral flag — strip it to avoid passing an unsupported option.
  if (interaction.deferred && !interaction.replied) {
    const { flags, ...editable } = dpayload;
    await interaction
      .editReply(editable)
      .catch((e) => console.error('reply failed:', e.message));
    return;
  }

  const method = interaction.replied ? 'followUp' : 'reply';
  await interaction[method](dpayload).catch((e) =>
    console.error('reply failed:', e.message),
  );
}

const DISCORD_MAX_MESSAGE = 2000;

export function startsWithBotMention(content, botId) {
  const trimmed = (content ?? '').trimStart();
  return trimmed.startsWith(`<@${botId}>`) || trimmed.startsWith(`<@!${botId}>`);
}

export function stripLeadingMention(content, botId) {
  const trimmed = (content ?? '').trimStart();
  for (const tag of [`<@${botId}>`, `<@!${botId}>`]) {
    if (trimmed.startsWith(tag)) return trimmed.slice(tag.length).trimStart();
  }
  return trimmed;
}

// Chronological array of fetched messages -> neutral /chat messages array.
// bot -> assistant, everyone else -> user; strip a leading mention from user
// turns; drop empties; collapse consecutive same-role turns (join with \n);
// drop leading assistant turns. Bedrock Converse needs strict user/assistant
// alternation starting with a user turn.
export function threadHistoryToMessages(fetched, botId) {
  const mapped = fetched
    .map((m) => {
      const role = m.author?.id === botId ? 'assistant' : 'user';
      const raw = m.content ?? '';
      const content = role === 'user' ? stripLeadingMention(raw, botId) : raw;
      return { role, content: content.trim() };
    })
    .filter((m) => m.content.length > 0);

  const collapsed = [];
  for (const m of mapped) {
    const last = collapsed[collapsed.length - 1];
    if (last && last.role === m.role) last.content += `\n${m.content}`;
    else collapsed.push({ ...m });
  }
  while (collapsed.length && collapsed[0].role === 'assistant') collapsed.shift();
  return collapsed;
}

export function chunkForDiscord(text) {
  const chunks = [];
  let remaining = text ?? '';
  while (remaining.length > DISCORD_MAX_MESSAGE) {
    let cut = remaining.lastIndexOf('\n', DISCORD_MAX_MESSAGE);
    if (cut <= 0) cut = DISCORD_MAX_MESSAGE; // no newline → hard split
    chunks.push(remaining.slice(0, cut));
    remaining = remaining.slice(cut).replace(/^\n/, '');
  }
  if (remaining.length > 0) chunks.push(remaining);
  return chunks;
}

const HISTORY_LIMIT = 20;
const LINK_PROMPT = 'You need to link your account first. Run `/link` to identify yourself, then try again.';
const VERIFY_UNAVAILABLE = "I can't verify you right now — the directory is unavailable. Please try again shortly.";
const LLM_UNAVAILABLE = "I'm having trouble reaching the assistant right now — please try again shortly.";

// Handle a message that starts with the bot's mention. Linked-only. In a
// channel it opens a thread; in a thread it replays the thread's history as
// memory. Never throws to discord.js.
export async function handleMention(message, { appContext, botId }) {
  const question = stripLeadingMention(message.content, botId);
  if (!question) return; // bare ping, nothing to answer

  let principal;
  try {
    principal = await resolvePrincipal(appContext.directory, message.author.id);
  } catch (e) {
    if (e instanceof DirectoryUnavailable) {
      await message.reply(VERIFY_UNAVAILABLE).catch(() => {});
      return;
    }
    throw e;
  }
  if (!authorize('linked', principal).ok) {
    await message.reply(LINK_PROMPT).catch(() => {});
    return;
  }

  let target;
  let messages;
  if (message.channel.isThread()) {
    target = message.channel;
    const fetched = await target.messages.fetch({ limit: HISTORY_LIMIT });
    const ordered = [...fetched.values()].sort(
      (a, b) => (a.createdTimestamp ?? 0) - (b.createdTimestamp ?? 0),
    );
    messages = threadHistoryToMessages(ordered, botId);
  } else {
    target = await message.startThread({ name: question.slice(0, 100) });
    messages = [{ role: 'user', content: question }];
  }
  if (!messages.length) return;

  await target.sendTyping().catch(() => {});
  let content;
  try {
    ({ content } = await appContext.helperService.answer({ messages, principal }));
  } catch (err) {
    console.error('helper answer failed:', err.message);
    await target.send(LLM_UNAVAILABLE).catch(() => {});
    return;
  }
  for (const chunk of chunkForDiscord(content)) {
    await target.send(chunk).catch((e) => console.error('helper reply failed:', e.message));
  }
}

export function wireDiscordClient(client, { commands, appContext }) {
  client.on('interactionCreate', async (interaction) => {
    // Autocomplete interactions are a separate path: they CANNOT be deferred and
    // must respond within 3s. Best-effort — dispatchAutocomplete never throws.
    if (interaction.isAutocomplete()) {
      const command = commands.get(interaction.commandName);
      if (!command) return;
      try {
        const intent = interactionToAutocompleteIntent(interaction);
        const suggestions = await dispatchAutocomplete(intent, { commands, appContext });
        await interaction.respond(suggestions.slice(0, 25)).catch(() => {});
      } catch (err) {
        console.error('Autocomplete error:', err);
        await interaction.respond([]).catch(() => {});
      }
      return;
    }

    if (!interaction.isChatInputCommand()) return;
    const command = commands.get(interaction.commandName);
    if (!command) return;
    try {
      const intent = interactionToIntent(interaction, command);
      // Acknowledge within Discord's 3s deadline BEFORE running the handler.
      // The handler may hit a cold-starting (asleep) Neon database that takes
      // several seconds to boot; without an early defer the interaction token
      // expires and the reply fails ("Unknown interaction") even though the DB
      // work succeeds. Deferring extends the response window to 15 minutes.
      const ephemeral = resolveEphemeral(command, intent.subcommand);
      await interaction.deferReply(ephemeral ? { flags: MessageFlags.Ephemeral } : {});
      const payload = await dispatch(intent, { commands, appContext });
      await safeReply(interaction, payload);
    } catch (err) {
      console.error('Unhandled interaction error:', err);
      // We already deferred, so the user is staring at "thinking…". Resolve the
      // interaction with a generic error instead of leaving it hanging until the
      // token expires. safeReply routes this via editReply on the deferred
      // message; its own catch swallows any follow-on failure.
      await safeReply(interaction, authMessages.internalError());
    }
  });

  client.on('messageCreate', async (message) => {
    try {
      if (message.author?.bot) return;
      const botId = client.user?.id;
      if (!botId || !startsWithBotMention(message.content, botId)) return;
      await handleMention(message, { appContext, botId });
    } catch (err) {
      console.error('Unhandled mention error:', err);
    }
  });
}
