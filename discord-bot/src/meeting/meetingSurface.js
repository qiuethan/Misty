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
    const stream = meetingClient.openStream(sessionId, { guildId });
    const recorder = makeRecorder({ sink: stream, now });

    Promise.resolve(recorder.start(voiceChannel)).catch((err) => {
      console.error(`meetingSurface: recorder failed to start for guild ${guildId}:`, err);
    });

    sessions.set(guildId, {
      sessionId,
      stream,
      recorder,
      textChannel,
      startedAt: now(),
    });

    return { status: 'recording', sessionId };
  }

  function status(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };
    return { status: 'recording', elapsedMs: now() - session.startedAt };
  }

  async function stop(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };

    // Remove the session BEFORE any awaits so a concurrent stop() call for
    // the same guild can't double-run the teardown below.
    sessions.delete(guildId);

    try {
      const { sessionId, stream, recorder, textChannel } = session;
      await recorder.stop();
      await stream.close();
      const report = await meetingClient.stop(sessionId);
      await poster({ channel: textChannel, report });
      return { status: 'stopped' };
    } catch (err) {
      console.error(`meetingSurface: error stopping meeting for guild ${guildId}:`, err);
      return { status: 'error' };
    }
  }

  return { start, status, stop };
}
