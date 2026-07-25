import path from 'node:path';
import os from 'node:os';
import { rm } from 'node:fs/promises';
import { mkdtempSync } from 'node:fs';

function wordsToSegments(displayName, words, gapMs = 3000) {
  const segments = [];
  let cur = null;
  for (const w of words) {
    if (!cur || w.startMs - cur.lastMs > gapMs) {
      cur = { speaker: displayName, startMs: w.startMs, lastMs: w.startMs, parts: [w.text] };
      segments.push(cur);
    } else {
      cur.parts.push(w.text);
      cur.lastMs = w.startMs;
    }
  }
  return segments.map((s) => ({ speaker: s.speaker, startMs: s.startMs, text: s.parts.join(' ') }));
}

export function createSessionManager({
  reportService, transcribeClient, audio, makeRecorder, poster,
  now = Date.now, maxRecordingMs = 3_600_000, tmpRoot = os.tmpdir(),
}) {
  const sessions = new Map(); // guildId -> { recorder, textChannel, startedAt, tmpDir, timer }

  async function runPipeline(guildId) {
    const s = sessions.get(guildId);
    if (!s) return { status: 'not-recording' };
    sessions.delete(guildId);
    if (s.timer) clearTimeout(s.timer);
    const { tracks, startedAt, endedAt } = await s.recorder.stop();

    const segments = [];
    const participants = [];
    for (const t of tracks) {
      participants.push(t.displayName);
      const monoPcm = await audio.runFfmpeg(audio.pcmToMono16kArgs(t.pcmPath));
      async function* chunks() { yield monoPcm; }
      const { words } = await transcribeClient.transcribePcm({ pcmChunks: chunks() });
      segments.push(...wordsToSegments(t.displayName, words));
    }

    const durationMs = endedAt - startedAt;
    const meta = {
      title: `Meeting recording — ${new Date(startedAt).toISOString().slice(0, 16).replace('T', ' ')}`,
      startedAt: new Date(startedAt).toISOString().slice(0, 16).replace('T', ' '),
      durationLabel: `${Math.round(durationMs / 60000)}m`,
      participants,
    };
    const { pdfBuffer } = await reportService.buildReport({ segments, meta });

    const mp3Path = path.join(s.tmpDir, 'meeting.mp3');
    if (tracks.length) {
      await audio.runFfmpeg(audio.mixToMp3Args(tracks.map((t) => t.pcmPath), mp3Path));
    }
    await poster({ channel: s.textChannel, pdfBuffer, mp3Path: tracks.length ? mp3Path : null, meta });
    await rm(s.tmpDir, { recursive: true, force: true });
    return { status: 'stopped' };
  }

  return {
    start({ guildId, voiceChannel, textChannel }) {
      if (sessions.has(guildId)) return { status: 'already-recording' };
      const startedAt = now();
      const dir = mkdtempSync(path.join(tmpRoot, 'meeting-'));
      const session = { textChannel, startedAt, tmpDir: dir, recorder: null, timer: null };
      sessions.set(guildId, session);
      session.recorder = makeRecorder({ tmpDir: dir });
      session.recorder.start(voiceChannel).catch((e) => console.error('recorder start failed:', e?.message ?? e));
      session.timer = setTimeout(() => { runPipeline(guildId).catch(() => {}); }, maxRecordingMs);
      if (session.timer && typeof session.timer.unref === 'function') session.timer.unref();
      return { status: 'recording' };
    },
    status(guildId) {
      const s = sessions.get(guildId);
      if (!s) return { status: 'not-recording' };
      return { status: 'recording', elapsedMs: now() - s.startedAt };
    },
    stop(guildId) { return runPipeline(guildId); },
  };
}
