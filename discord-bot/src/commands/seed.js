import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { renderSeedResult } from '../messages.js';

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
  const result = await ctx.seedService.seedPerson(
    { email, displayName: name, level },
    { caller: ctx.principal.person },
  );
  await interaction.reply({ content: renderSeedResult(result), flags: MessageFlags.Ephemeral });
}
