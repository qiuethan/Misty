import { defineCommand } from '../defineCommand.js';

// Registration-only. This command exists so registerCommands.js registers the
// `/record` slash command (and its subcommands) with Discord. The
// interactionCreate handler in src/adapters/discord.js intercepts
// commandName === 'record' BEFORE the neutral dispatch path and routes
// straight to appContext.meetingSurface — the handlers below are never
// invoked in production. They exist only so defineCommand's validation
// (which requires a handler) is satisfied, and as a safety net if the
// interception is ever bypassed.
function unreachable() {
  return { content: 'Recording is handled by the voice surface.', ephemeral: true };
}

export default defineCommand({
  name: 'record',
  description: 'Record the current voice channel and post meeting minutes',
  auth: 'linked',
  beta: true, // testing-guild only while the voice surface is validated
  options: [],
  subcommands: [
    {
      name: 'start',
      description: 'Start recording the voice channel you are in',
      handler: unreachable,
    },
    {
      name: 'status',
      description: 'Check whether a recording is in progress',
      handler: unreachable,
    },
    {
      name: 'stop',
      description: 'Stop recording and post the meeting minutes',
      handler: unreachable,
    },
  ],
  async handler() {
    return unreachable();
  },
});
