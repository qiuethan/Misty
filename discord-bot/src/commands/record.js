import { defineCommand } from '../defineCommand.js';

export default defineCommand({
  name: 'record',
  description: 'Record the current voice meeting and get a transcript + minutes PDF',
  auth: 'linked',
  beta: true,
  ephemeral: true,
  subcommands: [
    {
      name: 'start',
      description: 'Join your voice channel and start recording',
      async handler({ ctx }) {
        if (!ctx.voiceChannel) {
          return { content: 'Join a voice channel first, then run `/record start`.', ephemeral: true };
        }
        const { status } = ctx.sessionManager.start({
          guildId: ctx.guildId, voiceChannel: ctx.voiceChannel, textChannel: ctx.textChannel,
        });
        if (status === 'already-recording') {
          return { content: "I'm already recording in this server. Use `/record stop` to finish.", ephemeral: true };
        }
        return { content: '🔴 Recording. Use `/record stop` when you\'re done.', ephemeral: true };
      },
    },
    {
      name: 'status',
      description: 'Check whether a recording is in progress',
      async handler({ ctx }) {
        const s = ctx.sessionManager.status(ctx.guildId);
        if (s.status !== 'recording') return { content: 'Not currently recording.', ephemeral: true };
        return { content: `🔴 Recording — ${Math.round((s.elapsedMs ?? 0) / 60000)}m elapsed.`, ephemeral: true };
      },
    },
    {
      name: 'stop',
      description: 'Stop recording and post the transcript + minutes PDF',
      async handler({ ctx }) {
        const { status } = await ctx.sessionManager.stop(ctx.guildId);
        if (status === 'not-recording') return { content: 'No recording is in progress.', ephemeral: true };
        return { content: '⏳ Processing the recording — the transcript, minutes PDF, and audio will post here shortly.', ephemeral: true };
      },
    },
  ],
  async handler(intent) {
    const sub = this.subcommands.find((s) => s.name === intent.subcommand);
    if (!sub) return { content: 'Something went wrong. Please try again.', ephemeral: true };
    return sub.handler(intent);
  },
});
