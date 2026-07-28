import {
  joinVoiceChannel, EndBehaviorType, entersState, VoiceConnectionStatus,
} from '@discordjs/voice';

// After /record stop we keep forwarding until the receive streams have been
// quiet this long, so packets Discord had already buffered still make it out.
const DRAIN_QUIET_MS = 250;
// ...but never longer than this: someone may simply still be talking, and
// /record stop must not wait on them indefinitely.
const DRAIN_MAX_MS = 2000;
const DRAIN_POLL_MS = 50;

export function createRecorder({
  sink,
  now = Date.now,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  join = joinVoiceChannel,
  ready = (connection) => entersState(connection, VoiceConnectionStatus.Ready, 20_000),
}) {
  let connection = null;
  let startedAt = null;
  const knownSpeakers = new Set();
  // userId -> the speaker's live receive stream, held open for the whole
  // meeting and torn down in stop().
  const subscriptions = new Map();
  let stopped = false;
  let lastPacketAt = 0;

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
    if (subscriptions.has(userId)) return;

    // Manual, NOT AfterSilence. AfterSilence ends the stream a second after
    // someone stops talking, and the receiver silently DISCARDS packets for a
    // user with no subscription (Receiver.onUdpMessage: `if (!stream) return`).
    // Re-subscribing depends on SpeakingMap emitting 'start' again, and its
    // ~100ms speaking timeout is nothing like the 1s stream timeout -- so a
    // speaker who paused could lose everything they said afterwards. Holding
    // one stream open per speaker removes the race entirely: there is always a
    // subscription, so no packet is ever dropped.
    const opus = connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.Manual },
    });
    subscriptions.set(userId, opus);
    const clearActive = () => subscriptions.delete(userId);
    opus.on('data', (packet) => {
      if (stopped) return;
      lastPacketAt = now();
      sink.sendFrame(userId, now() - startedAt, packet);
    });
    opus.on('error', (e) => console.error(`recorder: opus stream error for ${userId}:`, e.message));
    // A Manual stream should never end on its own; these only fire if the
    // connection goes away underneath us, and keep the map honest if it does.
    opus.once('error', clearActive);
    opus.once('close', clearActive);
  }

  return {
    async start(voiceChannel) {
      connection = join({
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        adapterCreator: voiceChannel.guild.voiceAdapterCreator,
        selfDeaf: false,
        selfMute: true,
      });
      try {
        await ready(connection);
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
      if (!connection) return; // already stopped
      const conn = connection;
      connection = null; // claim it first, so a concurrent stop() is a no-op

      // Stop taking on NEW speakers, but keep forwarding what is already in
      // flight. destroy() discards whatever Discord has buffered in the receive
      // streams, and setting `stopped` first drops packets that arrive in the
      // meantime -- between them that clipped the last words of the meeting.
      conn.receiver.speaking.removeAllListeners('start');

      const deadline = now() + DRAIN_MAX_MS;
      while (now() < deadline && now() - lastPacketAt < DRAIN_QUIET_MS) {
        await wait(DRAIN_POLL_MS);
      }

      stopped = true;
      // Manual streams never end themselves, so close them explicitly rather
      // than leaving them attached to a destroyed connection.
      for (const opus of subscriptions.values()) {
        try {
          opus.destroy();
        } catch (err) {
          console.error('recorder: failed to close a receive stream:', err.message);
        }
      }
      subscriptions.clear();
      conn.destroy();
    },
  };
}
