import {
  joinVoiceChannel, EndBehaviorType, entersState, VoiceConnectionStatus,
} from '@discordjs/voice';

export function createRecorder({ sink, now = Date.now }) {
  let connection = null;
  let startedAt = null;
  const knownSpeakers = new Set();

  function subscribe(userId, member) {
    if (!knownSpeakers.has(userId)) {
      knownSpeakers.add(userId);
      const displayName = member?.displayName ?? member?.user?.username ?? userId;
      sink.sendControl({ speakerId: userId, displayName });
    }
    const opus = connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: 1000 },
    });
    opus.on('data', (packet) => {
      sink.sendFrame(userId, now() - startedAt, packet);
    });
    opus.on('error', (e) => console.error(`recorder: opus stream error for ${userId}:`, e.message));
  }

  return {
    async start(voiceChannel) {
      connection = joinVoiceChannel({
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        adapterCreator: voiceChannel.guild.voiceAdapterCreator,
        selfDeaf: false,
        selfMute: true,
      });
      await entersState(connection, VoiceConnectionStatus.Ready, 20_000);
      startedAt = now();
      connection.receiver.speaking.on('start', (userId) => {
        const member = voiceChannel.guild.members.cache.get(userId);
        if (member?.user?.bot) return;
        subscribe(userId, member);
      });
    },
    async stop() {
      if (connection) {
        connection.receiver.speaking.removeAllListeners('start');
        connection.destroy();
        connection = null;
      }
    },
  };
}
