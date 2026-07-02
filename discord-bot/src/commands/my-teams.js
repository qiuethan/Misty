import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import { renderMyTeamsResult } from '../messages.js';

export const data = new SlashCommandBuilder()
  .setName('my-teams')
  .setDescription('List the teams you are on');

export const auth = 'linked';
export const beta = true;

export async function execute(interaction, ctx) {
  const caller = ctx.principal.person;
  const result = await ctx.teamService.getMyTeams({ personId: caller.id }, { caller });
  await interaction.reply({
    content: renderMyTeamsResult(result),
    flags: MessageFlags.Ephemeral,
  });
}
