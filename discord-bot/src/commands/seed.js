import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { renderSeedResult } from '../messages.js';
import { rankOf } from '../auth/policy.js';
import { PersonExists, DirectoryUnavailable } from '../directoryClient.js';

export const data = new SlashCommandBuilder()
  .setName('seed')
  .setDescription('Add a member to the directory (admins only)')
  .addStringOption((o) => o.setName('email').setDescription('Member email').setRequired(true))
  .addStringOption((o) => o.setName('name').setDescription('Display name').setRequired(true))
  .addStringOption((o) =>
    o
      .setName('level')
      .setDescription('Access level (default member)')
      .setRequired(false)
      .addChoices(
        { name: 'member', value: 'member' },
        { name: 'admin', value: 'admin' },
        { name: 'superuser', value: 'superuser' },
      ),
  );

export const auth = 'admin';
export const beta = false;

export async function execute(interaction, ctx) {
  const email = interaction.options.getString('email');
  const name = interaction.options.getString('name');
  const level = interaction.options.getString('level') ?? 'member';

  // Escalation guard: never grant a level above your own.
  const callerLevel = ctx.principal.person.access_level;
  if (rankOf(level) > rankOf(callerLevel)) {
    await interaction.reply({
      content: `You can only grant levels at or below your own (${callerLevel}).`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  let result;
  try {
    const person = await ctx.directory.createPerson({
      displayName: name,
      primaryEmail: email,
      accessLevel: level,
    });
    result = { outcome: 'SEEDED', person };
  } catch (e) {
    if (e instanceof PersonExists) result = { outcome: 'EXISTS', detail: e.detail };
    else if (e instanceof DirectoryUnavailable) result = { outcome: 'DIRECTORY_DOWN' };
    else throw e;
  }
  await interaction.reply({ content: renderSeedResult(result), flags: MessageFlags.Ephemeral });
}
