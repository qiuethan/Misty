import { SlashCommandBuilder, MessageFlags, EmbedBuilder } from 'discord.js';
import { buildWhoamiEmbed } from '../messages.js';
import { DirectoryUnavailable } from '../directoryClient.js';

export const data = new SlashCommandBuilder()
  .setName('whoami')
  .setDescription('Show your directory record and linked accounts');

export const auth = 'linked'; // the router guarantees ctx.principal is present
export const beta = false; // stable → registered globally (all prod servers)

export async function execute(interaction, ctx) {
  const person = ctx.principal.person;

  // Partial-view degrade: the caller is already authenticated, so a failed
  // identifiers fetch shouldn't hide the info the router just resolved.
  let identifiers;
  try {
    identifiers = await ctx.directory.listIdentifiers(person.id);
  } catch (e) {
    if (e instanceof DirectoryUnavailable) {
      identifiers = null;
    } else {
      throw e;
    }
  }

  const spec = buildWhoamiEmbed(person, identifiers);
  const embed = new EmbedBuilder().setTitle(spec.title).addFields(spec.fields);
  await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
}
