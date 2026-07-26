import WsWebSocket from 'ws';

export class MeetingUnavailable extends Error {
  constructor(message) {
    super(message);
    this.name = 'MeetingUnavailable';
  }
}

// Transport client for the internal meeting service: a WebSocket audio/control
// stream plus a small HTTP surface (transcript/stop). Pure transport — no
// discord.js here; the binary frame layout below MUST byte-match the
// service's parser (2-byte BE speaker_id length, speaker_id utf8, 8-byte BE
// ts_ms, remaining bytes = opus payload).
export function createMeetingClient({ baseUrl, wsUrl, apiKey, WebSocketImpl = WsWebSocket, fetchImpl = fetch }) {
  function encodeFrame(speakerId, tsMs, opusBuffer) {
    const id = Buffer.from(speakerId, 'utf8');
    const head = Buffer.allocUnsafe(2);
    head.writeUInt16BE(id.length, 0);
    const ts = Buffer.alloc(8);
    ts.writeBigUInt64BE(BigInt(tsMs), 0);
    return Buffer.concat([head, id, ts, opusBuffer]);
  }

  function openStream(sessionId, { guildId, onError }) {
    // The API key is intentionally NOT put in the URL (query strings leak into
    // access/proxy logs). Instead we rely on the service's first-text-frame
    // auth fallback: connect with no `key` query param, then send exactly one
    // text frame `{"key": "..."}` as the very first message once the socket
    // opens, before anything else (see services/meeting's
    // src/api/routers/meetings.py `_authenticate_ws`/`stream_meeting`).
    const url = `${wsUrl}/meetings/${sessionId}/stream?guild_id=${encodeURIComponent(guildId)}`;
    const ws = new WebSocketImpl(url);

    let open = false;
    let dead = false;
    const queue = [];

    const onOpen = () => {
      open = true;
      // Auth frame MUST be sent first, before any queued control/audio frames.
      ws.send(JSON.stringify({ key: apiKey }));
      for (const data of queue.splice(0)) ws.send(data);
    };
    const onErrorEvent = (e) => {
      dead = true;
      console.error('meeting stream error:', e?.message ?? e);
      try {
        onError?.(e);
      } catch (cbErr) {
        console.error('meeting stream onError callback failed:', cbErr);
      }
    };
    const onCloseEvent = () => {
      dead = true;
    };

    if (typeof ws.addEventListener === 'function') {
      ws.addEventListener('open', onOpen);
      ws.addEventListener('error', onErrorEvent);
      ws.addEventListener('close', onCloseEvent);
    } else if (typeof ws.on === 'function') {
      ws.on('open', onOpen);
      ws.on('error', onErrorEvent);
      ws.on('close', onCloseEvent);
    }

    const dispatch = (data) => {
      if (dead) return;
      if (open) ws.send(data);
      else queue.push(data);
    };

    return {
      sendControl({ speakerId, displayName }) {
        dispatch(JSON.stringify({ speaker_id: speakerId, display_name: displayName }));
      },
      sendFrame(speakerId, tsMs, opusBuffer) {
        dispatch(encodeFrame(speakerId, tsMs, opusBuffer));
      },
      close() {
        ws.close();
      },
    };
  }

  async function getTranscript(sessionId) {
    let resp;
    try {
      resp = await fetchImpl(`${baseUrl}/meetings/${sessionId}/transcript`, {
        headers: { 'X-API-Key': apiKey },
      });
    } catch {
      throw new MeetingUnavailable('network error reaching meeting service');
    }
    if (!resp.ok) throw new MeetingUnavailable(`meeting service returned ${resp.status}`);
    try {
      return await resp.json();
    } catch {
      throw new MeetingUnavailable('malformed meeting service response');
    }
  }

  async function stop(sessionId) {
    let resp;
    try {
      resp = await fetchImpl(`${baseUrl}/meetings/${sessionId}/stop`, {
        method: 'POST',
        headers: { 'X-API-Key': apiKey },
      });
    } catch {
      throw new MeetingUnavailable('network error reaching meeting service');
    }
    if (!resp.ok) throw new MeetingUnavailable(`meeting service returned ${resp.status}`);
    try {
      return await resp.json();
    } catch {
      throw new MeetingUnavailable('malformed meeting service response');
    }
  }

  return { encodeFrame, openStream, getTranscript, stop };
}
