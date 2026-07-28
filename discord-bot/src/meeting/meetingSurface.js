import { randomUUID } from 'node:crypto';

// Per-guild live-meeting lifecycle. Pure orchestration: all collaborators
// (transport client, recorder factory, poster) are injected. No discord.js
// import here — voiceChannel/textChannel are passed through opaquely.
export function createMeetingSurface({
  meetingClient,
  makeRecorder,
  poster,
  // Tells the meeting's text channel that a recording died on its own. Without
  // it a dropped connection is invisible: the session is gone, /record status
  // says nothing is recording, and nobody knows the meeting was lost.
  notify = async () => {},
  now = Date.now,
  genId = randomUUID,
}) {
  const sessions = new Map();

  // `requesterId` is the Discord user id of whoever started the recording. It's
  // stored on the session (not read off the stopping interaction) so the
  // minutes always @-mention the person who asked for them -- including when
  // the recording ends via auto-stop, where there's no interaction at all.
  async function start({ guildId, voiceChannel, textChannel, requesterId }) {
    if (sessions.has(guildId)) {
      return { status: 'already-recording' };
    }

    const sessionId = genId();
    let recorder = null;

    // Idempotent teardown: if the guild's session has already been removed
    // (e.g. a normal stop() raced us, or this fires twice), this is a no-op.
    //
    // It MUST stop the recorder, not just close the stream. Leaving the voice
    // connection up means the bot sits in the channel holding open one receive
    // stream per speaker, while `sessions.delete` makes /record status report
    // nothing is recording and /record stop answer "no recording in progress"
    // -- so nothing short of a restart can remove it.
    const teardown = async (reason) => {
      if (sessions.get(guildId)?.sessionId !== sessionId) return;
      sessions.delete(guildId);
      try {
        if (recorder) await recorder.stop();
      } catch (err) {
        console.error(`meetingSurface: error stopping recorder during teardown for guild ${guildId}:`, err);
      }
      try {
        await stream.close();
      } catch (err) {
        console.error(`meetingSurface: error closing stream during teardown for guild ${guildId}:`, err);
      }
      await notify({
        channel: textChannel,
        content: `⚠️ The recording stopped unexpectedly (${reason}) and no minutes will be posted.`,
      }).catch((err) => console.error(`meetingSurface: teardown notify failed:`, err));
    };

    const stream = meetingClient.openStream(sessionId, {
      guildId,
      onError: () => teardown('connection error'),
      // A clean close counts too: an auth rejection, a duplicate session, or a
      // service redeploy all close the socket without an error, and every frame
      // after that is silently discarded by the client.
      onClose: () => teardown('connection closed'),
    });
    recorder = makeRecorder({ sink: stream, now });

    // Register BEFORE awaiting the join, so a teardown firing mid-join can
    // actually find the session and tear it down (it keys off sessionId).
    sessions.set(guildId, {
      sessionId,
      stream,
      recorder,
      textChannel,
      voiceChannel,
      requesterId,
      startedAt: now(),
    });

    // AWAIT the join. Returning "recording" before the voice connection is up
    // means a missing Connect permission, a full channel, or a 20s timeout is
    // reported to the user as success, and they only find out at /record stop.
    try {
      await recorder.start(voiceChannel);
    } catch (err) {
      console.error(`meetingSurface: recorder failed to start for guild ${guildId}:`, err);
      if (sessions.get(guildId)?.sessionId === sessionId) sessions.delete(guildId);
      await Promise.resolve(stream.close()).catch(() => {});
      return { status: 'error' };
    }

    // A teardown may have removed us while we were joining.
    if (sessions.get(guildId)?.sessionId !== sessionId) return { status: 'error' };

    return { status: 'recording', sessionId };
  }

  function status(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };
    return { status: 'recording', elapsedMs: now() - session.startedAt };
  }

  // A snapshot of the guild's active recording, or null: its `sessionId` and
  // the (opaque) `voiceChannel` being recorded. The Discord adapter uses this to
  // auto-stop when the channel empties. Both fields come from the single session
  // source of truth so they can't drift; the channel is treated opaquely so this
  // module stays free of any discord.js dependency. The `sessionId` lets the
  // adapter bind a scheduled auto-stop to a SPECIFIC recording, so a timer from
  // an already-ended session can never terminate a later one in the same guild.
  function activeSession(guildId) {
    const session = sessions.get(guildId);
    if (!session) return null;
    return { sessionId: session.sessionId, voiceChannel: session.voiceChannel };
  }

  async function stop(guildId) {
    const session = sessions.get(guildId);
    if (!session) return { status: 'not-recording' };

    // Remove the session BEFORE any awaits so a concurrent stop() call for
    // the same guild can't double-run the teardown below.
    sessions.delete(guildId);

    const { sessionId, stream, recorder, textChannel, requesterId } = session;
    try {
      // Order matters: finalize server-side (POST /stop) BEFORE closing the
      // WS. The service treats a WS disconnect with no prior /stop as an
      // abrupt-disconnect discard() (deregister + drop buffers, no
      // finalize) -- closing the WS first would race the session into being
      // discarded, so the subsequent /stop 404s and we lose the minutes.
      await recorder.stop();
      // Then tell the service that was the last of the audio. This rides the
      // WS behind every frame already sent, so the service can wait for it
      // before finalizing instead of racing the tail. Without it, POST /stop
      // can finalize while the last frames are still in flight and the
      // transcript ends early. Best-effort: a failure here must not cost us
      // the minutes -- the service falls back to a timeout.
      try {
        stream.endAudio();
      } catch (err) {
        console.error(`meetingSurface: end-of-audio signal failed for guild ${guildId}:`, err);
      }
      const report = await meetingClient.stop(sessionId);
      await poster({ channel: textChannel, report, requesterId });
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

  return { start, status, stop, activeSession };
}
