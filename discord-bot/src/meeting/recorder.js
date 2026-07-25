import { createWriteStream } from 'node:fs';
import path from 'node:path';
import prism from 'prism-media';
import {
  joinVoiceChannel, EndBehaviorType, getVoiceConnection, entersState, VoiceConnectionStatus,
} from '@discordjs/voice';

// 48kHz * 2ch * 2bytes = 192000 bytes/sec of silence padding.
const BYTES_PER_MS = 192000 / 1000;

export function createRecorder({ tmpDir }) {
  let connection = null;
  const tracks = new Map(); // userId -> { displayName, stream, path, lastWriteMs, bytesWritten }
  let startedAt = null;

  function ensureTrack(userId, displayName) {
    if (tracks.has(userId)) return tracks.get(userId);
    const filePath = path.join(tmpDir, `${userId}.pcm`);
    const stream = createWriteStream(filePath);
    const track = { displayName, stream, path: filePath, lastWriteMs: Date.now(), bytesWritten: 0 };
    tracks.set(userId, track);
    return track;
  }

  function subscribe(userId, member) {
    const displayName = member?.displayName ?? member?.user?.username ?? userId;
    const track = ensureTrack(userId, displayName);
    const opus = connection.receiver.subscribe(userId, {
      end: { behavior: EndBehaviorType.AfterSilence, duration: 1000 },
    });
    const decoder = new prism.opus.Decoder({ rate: 48000, channels: 2, frameSize: 960 });
    // Pad leading silence so this burst lands at the right point on the timeline.
    const now = Date.now();
    const gapMs = now - track.lastWriteMs;
    if (track.bytesWritten > 0 && gapMs > 0) {
      track.stream.write(Buffer.alloc(Math.floor(gapMs * BYTES_PER_MS)));
      track.bytesWritten += Math.floor(gapMs * BYTES_PER_MS);
    }
    opus.pipe(decoder).on('data', (pcm) => {
      track.stream.write(pcm);
      track.bytesWritten += pcm.length;
      track.lastWriteMs = Date.now();
    });
    decoder.on('end', () => { track.lastWriteMs = Date.now(); });
  }

  return {
    async start(voiceChannel) {
      startedAt = Date.now();
      connection = joinVoiceChannel({
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        adapterCreator: voiceChannel.guild.voiceAdapterCreator,
        selfDeaf: false,
        selfMute: true,
      });
      await entersState(connection, VoiceConnectionStatus.Ready, 20_000);
      connection.receiver.speaking.on('start', (userId) => {
        const member = voiceChannel.guild.members.cache.get(userId);
        if (member?.user?.bot) return;
        subscribe(userId, member);
      });
    },
    async stop() {
      const endedAt = Date.now();
      const out = [];
      for (const [userId, t] of tracks) {
        await new Promise((res) => t.stream.end(res));
        out.push({ userId, displayName: t.displayName, pcmPath: t.path });
      }
      const existing = getVoiceConnection(connection?.joinConfig?.guildId);
      if (existing) existing.destroy();
      return { tracks: out, startedAt, endedAt };
    },
  };
}
