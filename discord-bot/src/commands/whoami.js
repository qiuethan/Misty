import { SlashCommandBuilder } from 'discord.js';
import { renderWhoami } from '../messages.js';

export const data = new SlashCommandBuilder()
  .setName('whoami')
  .setDescription('Show which directory record your Discord account is linked to');

export const auth = 'linked'; // the router guarantees ctx.principal is present

export async function execute(interaction, ctx) {
  await interaction.reply({ content: renderWhoami(ctx.principal.person), ephemeral: true });
}
