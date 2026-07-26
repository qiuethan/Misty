import { randomUUID } from 'node:crypto';

// Per-guild live-meeting lifecycle. Pure orchestration: all collaborators
// (transport client, recorder factory, poster) are injected. No discord.js
// import here — voiceChannel/textChannel are passed through opaquely.
export function createMeetingSurface({
  meetingClient,
  makeRecorder,
  poster,
  now = Date.now,
  genId = randomUUID,
}) {
  const sessions = new Map();

  function start({ guildId, voiceChannel, textChannel }) {
    if (sessions.has(guildId)) {
      return { status: 'already-recording' };
    }

    const sessionId = genId();

    // Idempotent teardown: if the guild's session has already been removed
    // (e.g. a normal stop() raced us, or this fires twice), this is a no-op.
    const teardown = () => {
      if (sessions.get(guildId)?.sessionId !== sessionId) return;
      sessions.delete(guildId);
      Promise.resolve(stream.close()).catch((err) => {
        console.error(`meetingSurface: error closing stream during teardown for guild ${guildId}:`, err);
      });
    };

    const stream = meetingClient.openStream(sessionId, {
      guildId,
      onError: () => teardown(),
    });
    const recorder = makeRecorder({ sink: stream, now });

    Promise.resolve(recorder.start(voiceChannel)).catch((err) => {
      console.error(`meetingSurface: recorder failed to start for guild ${guildId}:`, err);
      teardown();
    });

    sessions.set(guildId, {
      sessionId,
      stream,
      recorder,
      textChannel,
      voiceChannel,
      startedAt: now(),
    });

    return { status: 'recording', sessionId };
  }

  function status(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };
    return { status: 'recording', elapsedMs: now() - session.startedAt };
  }

  // The (opaque) voice channel currently being recorded for a guild, or null.
  // The Discord adapter uses this to auto-stop when the channel empties -- kept
  // here (the single session source of truth) so it can't drift from the live
  // session, but treated opaquely so this module stays free of any discord.js
  // dependency.
  function activeVoiceChannel(guildId) {
    return sessions.get(guildId)?.voiceChannel ?? null;
  }

  async function stop(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };

    // Remove the session BEFORE any awaits so a concurrent stop() call for
    // the same guild can't double-run the teardown below.
    sessions.delete(guildId);

    const { sessionId, stream, recorder, textChannel } = session;
    try {
      // Order matters: finalize server-side (POST /stop) BEFORE closing the
      // WS. The service treats a WS disconnect with no prior /stop as an
      // abrupt-disconnect discard() (deregister + temp-file cleanup, no
      // finalize) -- closing the WS first would race the session into being
      // discarded, so the subsequent /stop 404s and we lose the minutes.
      await recorder.stop();
      const report = await meetingClient.stop(sessionId);
      await poster({ channel: textChannel, report });
      return { status: 'stopped' };
    } catch (err) {
      console.error(`meetingSurface: error stopping meeting for guild ${guildId}:`, err);
      return { status: 'error' };
    } finally {
      // Close regardless of outcome so a failed recorder.stop()/finalize
      // never leaves the WS connected to the meeting service.
      await Promise.resolve(stream.close()).catch((closeErr) => {
        console.error(`meetingSurface: error closing stream during stop for guild ${guildId}:`, closeErr);
      });
    }
  }

  return { start, status, stop, activeVoiceChannel };
}
