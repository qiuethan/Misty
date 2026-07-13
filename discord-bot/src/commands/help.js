import { defineCommand } from '../defineCommand.js';
import { authorize } from '../auth/policy.js';
import { buildCommandDetailEmbed, buildHelpEmbed, helpMessages } from '../messages.js';

function visiblePolicy(command) {
  // Dynamic policies depend on request options. Treat them as linked for menu
  // visibility, matching the command registry's fail-secure convention.
  return typeof command.auth === 'function' ? 'linked' : command.auth;
}

export default defineCommand({
  name: 'help',
  description: 'List commands you can use or show details for one command',
  auth: 'public',
  identifyCaller: true,
  beta: false,
  options: [
    {
      name: 'command',
      type: 'string',
      required: false,
      description: 'Command name to show details for',
    },
  ],
  async handler({ options, principal, ctx }) {
    const visible = [...ctx.commands.values()]
      .filter((command) => command.name !== 'help')
      .filter((command) => authorize(visiblePolicy(command), principal).ok);

    if (!options.command) return buildHelpEmbed(visible);

    const requested = options.command.trim().replace(/^\//, '').toLowerCase();
    const command = visible.find((candidate) => candidate.name === requested);
    return command ? buildCommandDetailEmbed(command) : helpMessages.unknownCommand(requested);
  },
});
