import {
  joinVoiceChannel, EndBehaviorType, entersState, VoiceConnectionStatus,
} from '@discordjs/voice';

export function createRecorder({ sink, now = Date.now }) {
  let connection = null;
  let startedAt = null;
  const knownSpeakers = new Set();
  const activeSubscriptions = new Set();
  let stopped = false;

  function subscribe(userId, member) {
    if (!knownSpeakers.has(userId)) {
      knownSpeakers.add(userId);
      const displayName = member?.displayName ?? member?.user?.username ?? userId;
      sink.sendControl({ speakerId: userId, displayName });
    }
    // `receiver.subscribe` returns the same open AudioReceiveStream if one is
    // already active for this userId. Skip re-subscribing so we don't attach
    // duplicate `data`/`error` listeners (which would forward each frame
    // multiple times into the transcription).
    if (activeSubscriptions.has(userId)) return;
    activeSubscriptions.add(userId);
    const opus = connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: 1000 },
    });
    const clearActive = () => activeSubscriptions.delete(userId);
    opus.on('data', (packet) => {
      if (stopped) return;
      sink.sendFrame(userId, now() - startedAt, packet);
    });
    opus.on('error', (e) => console.error(`recorder: opus stream error for ${userId}:`, e.message));
    opus.once('error', clearActive);
    opus.once('end', clearActive);
    opus.once('close', clearActive);
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
      try {
        await entersState(connection, VoiceConnectionStatus.Ready, 20_000);
      } catch (e) {
        connection.destroy();
        connection = null;
        throw e;
      }
      startedAt = now();
      connection.receiver.speaking.on('start', (userId) => {
        const member = voiceChannel.guild.members.cache.get(userId);
        if (member?.user?.bot) return;
        subscribe(userId, member);
      });
    },
    async stop() {
      stopped = true;
      if (connection) {
        connection.receiver.speaking.removeAllListeners('start');
        connection.destroy();
        connection = null;
      }
    },
  };
}
