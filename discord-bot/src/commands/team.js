import { SlashCommandBuilder, MessageFlags } from 'discord.js';
import {
  renderCreateTeamResult,
  renderListTeamsResult,
  renderRenameTeamResult,
  renderAddMemberResult,
  renderRemoveMemberResult,
  renderRosterResult,
} from '../messages.js';

const ROLE_CHOICES = [
  { name: 'executive', value: 'executive' },
  { name: 'director', value: 'director' },
  { name: 'lead', value: 'lead' },
  { name: 'member', value: 'member' },
];

export const data = new SlashCommandBuilder()
  .setName('team')
  .setDescription('Manage UTMIST teams and memberships')
  .addSubcommand((s) =>
    s
      .setName('create')
      .setDescription('Create a new team (admin)')
      .addStringOption((o) => o.setName('slug').setDescription('Short handle, e.g. "ml"').setRequired(true))
      .addStringOption((o) => o.setName('label').setDescription('Display name').setRequired(true))
      .addStringOption((o) => o.setName('description').setDescription('Optional description').setRequired(false)),
  )
  .addSubcommand((s) =>
    s
      .setName('list')
      .setDescription('List teams')
      .addBooleanOption((o) =>
        o.setName('active_only').setDescription('Only active teams (default true)').setRequired(false),
      ),
  )
  .addSubcommand((s) =>
    s
      .setName('rename')
      .setDescription('Rename a team (admin)')
      .addStringOption((o) => o.setName('slug').setDescription('Team slug').setRequired(true))
      .addStringOption((o) => o.setName('new_label').setDescription('New display name').setRequired(true)),
  )
  .addSubcommand((s) =>
    s
      .setName('add')
      .setDescription('Add a member to a team (admin)')
      .addUserOption((o) => o.setName('user').setDescription('Discord user').setRequired(true))
      .addStringOption((o) => o.setName('team').setDescription('Team slug').setRequired(true))
      .addStringOption((o) =>
        o.setName('role').setDescription('Role (default member)').setRequired(false).addChoices(...ROLE_CHOICES),
      )
      .addBooleanOption((o) => o.setName('team_admin').setDescription('Grant team-admin flag').setRequired(false)),
  )
  .addSubcommand((s) =>
    s
      .setName('remove')
      .setDescription('Remove a member from a team (admin)')
      .addUserOption((o) => o.setName('user').setDescription('Discord user').setRequired(true))
      .addStringOption((o) => o.setName('team').setDescription('Team slug').setRequired(true)),
  )
  .addSubcommand((s) =>
    s
      .setName('roster')
      .setDescription("Show a team's current roster")
      .addStringOption((o) => o.setName('team').setDescription('Team slug').setRequired(true))
      .addStringOption((o) => o.setName('as_of').setDescription('ISO date (default today)').setRequired(false)),
  );

const SUB_AUTH = {
  create: 'admin',
  list: 'linked',
  rename: 'admin',
  add: 'admin',
  remove: 'admin',
  roster: 'linked',
};

export const auth = (interaction) => SUB_AUTH[interaction.options.getSubcommand()] ?? 'linked';
export const beta = true;

export async function execute(interaction, ctx) {
  const sub = interaction.options.getSubcommand();
  const caller = ctx.principal?.person;
  const send = (content) => interaction.reply({ content, flags: MessageFlags.Ephemeral });

  if (sub === 'create') {
    const args = {
      slug: interaction.options.getString('slug'),
      label: interaction.options.getString('label'),
    };
    const description = interaction.options.getString('description');
    if (description !== null) args.description = description;
    const result = await ctx.teamService.createTeam(args, { caller });
    return send(renderCreateTeamResult(result));
  }

  if (sub === 'list') {
    const activeOnlyOpt = interaction.options.getBoolean('active_only');
    const activeOnly = activeOnlyOpt === null ? true : activeOnlyOpt;
    const result = await ctx.teamService.listTeams({ activeOnly }, { caller });
    return send(renderListTeamsResult(result));
  }

  if (sub === 'rename') {
    const result = await ctx.teamService.renameTeam(
      { slug: interaction.options.getString('slug'), newLabel: interaction.options.getString('new_label') },
      { caller },
    );
    return send(renderRenameTeamResult(result));
  }

  if (sub === 'add') {
    const user = interaction.options.getUser('user');
    const args = {
      discordSnowflake: user.id,
      teamSlug: interaction.options.getString('team'),
    };
    const role = interaction.options.getString('role');
    if (role !== null) args.roleKindId = role;
    const teamAdmin = interaction.options.getBoolean('team_admin');
    if (teamAdmin !== null) args.isTeamAdmin = teamAdmin;
    const result = await ctx.teamService.addMember(args, { caller });
    return send(renderAddMemberResult(result));
  }

  if (sub === 'remove') {
    const user = interaction.options.getUser('user');
    const result = await ctx.teamService.removeMember(
      { discordSnowflake: user.id, teamSlug: interaction.options.getString('team') },
      { caller },
    );
    return send(renderRemoveMemberResult(result));
  }

  if (sub === 'roster') {
    const args = { teamSlug: interaction.options.getString('team') };
    const asOf = interaction.options.getString('as_of');
    if (asOf !== null) args.asOf = asOf;
    const result = await ctx.teamService.getRoster(args, { caller });
    return send(renderRosterResult(result));
  }

  return send('Something went wrong. Please try again.');
}
