import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { renderLinkResult } from '../messages.js';

export const data = new SlashCommandBuilder()
  .setName('link')
  .setDescription('Link your Discord account to your UTMIST directory record')
  .addStringOption((opt) =>
    opt.setName('email').setDescription('Your registered UTMIST email').setRequired(true),
  );

export const auth = 'public'; // you are not linked yet when you run /link
export const beta = false; // stable → registered globally (all prod servers)

export async function execute(interaction, ctx) {
  const email = interaction.options.getString('email');
  const result = await ctx.linkService.linkByEmail({
    email,
    discordUserId: interaction.user.id,
    discordHandle: interaction.user.username,
  });
  await interaction.reply({ content: renderLinkResult(result), flags: MessageFlags.Ephemeral });
}
