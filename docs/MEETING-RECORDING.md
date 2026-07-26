# Meeting Recording — Architecture

How the `/record` feature is split across a Discord **voice surface** (in the bot) and a stateful **`meeting` service**, and *why* the boundary sits where it does. Read this before changing either side — the two halves share a wire contract that must stay in lock-step.

Feature owner: Misty #92. Related: [platform ARCHITECTURE](ARCHITECTURE.md), [`services/meeting`](../services/meeting), [`discord-bot`](../discord-bot).

## What it does

A **linked** member (identity resolved via the directory — see "Authorization" below) runs `/record start` in a Discord voice channel. The bot joins, and as people talk it streams their audio to the `meeting` service, which transcribes each speaker live into a rolling transcript. Recording ends on `/record stop` **or automatically when everyone leaves the voice channel** (the bot ends the meeting once no non-bot member remains). On stop the service turns the transcript into minutes (via the `llm` service), renders a PDF, mixes the audio, and hands it back; the bot posts the **PDF + audio** to the text channel. Nothing is persisted — the transcript lives in memory for the meeting and is discarded after the report is returned.

## The boundary, and the one constraint that forces it

There is exactly one hard constraint, and it determines the whole design:

> **Voice capture is physically bound to the bot.** `@discordjs/voice` joins and receives voice through the bot's own Discord gateway connection (`guild.voiceAdapterCreator`). Nothing outside the bot process can receive that audio.

Everything *downstream* of capture — transcription, minutes, PDF, audio mixing — is ordinary stateful work with no Discord dependency. So the split is:

| | **`discord-bot`** — the *voice surface* | **`meeting` service** — stateful processing |
|---|---|---|
| **Owns** | Voice receive, the `/record` lifecycle, streaming audio up, posting results | Live transcription, the rolling transcript, minutes, PDF, audio mix |
| **Must not** | transcribe, summarize, render, or run ffmpeg | touch Discord |
| **Deps** | `@discordjs/voice`, `libsodium-wrappers` (RTP decrypt), `ws` | `amazon-transcribe` (streaming), ffmpeg, `fpdf2`, `httpx`, `platform_auth` |

The bot deliberately carries **no processing dependencies** (no `@aws-sdk`, no `pdfkit`, no ffmpeg) — it forwards Opus and posts what the service returns.

## Why the `meeting` service is *stateful*

Every other backend service (`team-tracking`, `documentation-system`, `llm`, `verification`) is a stateless source-of-truth: a request goes in, a response comes out, nothing is held between calls. `meeting` is the deliberate exception. **Live transcription requires *something* to hold the rolling transcript across the life of a meeting**, and the bot is the wrong place (we're keeping it lean and processing-free). So the service keeps an **in-memory registry of active meeting sessions**, each holding its per-speaker buffered audio and the growing rolling transcript, re-transcribed from the buffer as needed (see "Live" below). This is a considered trade, not an accident — it's the price of "ask Misty during the meeting" being possible at all. Persistent per-speaker Transcribe streams (incremental, not re-transcribed) are a deferred optimization — see "Known limitations" below.

State is still **ephemeral**: a session exists only while its meeting is live, and `POST /stop` (or an abrupt WebSocket disconnect) tears it down and deletes its temp files. Nothing reaches a database or object store.

## Data flow

```text
Discord voice  ──Opus──▶  bot recorder ──sendFrame──▶  meetingClient (WS) ══▶  meeting service
                                                                                  │
                                                     per-speaker AWS Transcribe (buffered re-transcription)
                                                                                  │
   /record stop ──POST /stop──────────────────────────────────────────────────▶  finalize:
                                                                    transcript → llm service → minutes
                                                                    → fpdf2 PDF → ffmpeg mix → MP3
   channel.send(PDF + MP3)  ◀────────────── {pdf_b64, audio_b64, transcript, minutes} ◀──
```

**Live:** the bot's recorder taps each speaker's raw Opus packets and forwards them (untouched, no decode) over one WebSocket. The service decodes/resamples each speaker's audio into a **per-speaker buffer** and transcribes those buffers via AWS Transcribe streaming to build the rolling transcript. (Current implementation: the whole buffer is re-transcribed on each poll/stop; **persistent incremental per-speaker streams** — transcribing continuously without re-sending finalized audio — are a deferred optimization, see "Known limitations".) `GET /meetings/{id}/transcript` exposes the transcript at any time — the hook that makes in-meeting "ask Misty" a fast-follow (the Q&A feature itself is not built yet).

**Stop:** `POST /meetings/{id}/stop` transcribes the final per-speaker buffers, assembles the transcript, calls the `llm` service for minutes, renders the PDF, mixes the per-speaker audio to MP3, returns them base64-encoded, and discards the session.

**Timeline correctness:** each forwarded frame carries `ts_ms` = milliseconds since the meeting started. AWS Transcribe reports word times relative to *each speaker's own* audio, so the service anchors every speaker's words by that speaker's first `ts_ms`. Without this, a person who joins the conversation late would sort to the *top* of the merged transcript. (This exact bug was caught in review — `ts_ms` must always be sent and honored.)

## The wire contract (keep both sides in lock-step)

The bot's `meetingClient.encodeFrame` and the service's `_parse_frame` are inverses. **If you change one, change the other.**

- **WebSocket:** `{wsUrl}/meetings/{sessionId}/stream?guild_id={guildId}` — the consumer key is sent as the **first WS text frame** `{"key": "…"}` (keeps it out of URLs/logs); the service also still accepts a `?key=` query param.
- **Binary audio frame:** `[2-byte big-endian speaker_id length][speaker_id UTF-8][8-byte big-endian ts_ms][raw Opus payload]`
- **Control frame (text/JSON):** `{"speaker_id": "...", "display_name": "..."}` — registers the display name shown for a speaker.
- **Auth:** the `platform_auth` consumer key — on the WS as the first text frame `{"key": "…"}` (or a `?key=` query param; both server-supported), and on `GET /transcript` / `POST /stop` as the `X-API-Key` header. The `meetings` scope is required.
- **`POST /stop` response:** `{ transcript, minutes, pdf_b64, audio_b64 }` (PDF + MP3 base64-encoded).

## The "separate surface" in the bot

Voice recording does **not** go through the bot's neutral slash-command path (`defineCommand` → `router.js` → a surface-agnostic handler returning a reply payload). That abstraction is for stateless request/response commands; a long-lived, stateful recording that posts file attachments does not fit it. Forcing it in (as an earlier iteration did) required smuggling live Discord objects through the router and bolting an attachment side-channel onto the reply contract.

Instead, `/record` is a **dedicated path in the Discord adapter**: `adapters/discord.js` intercepts `record` interactions *before* neutral dispatch and drives `meetingSurface` directly with the live interaction. `router.js` stays completely clean. The command is still declared (so it registers as a slash command) but its handler is never reached.

**Surface isolation** is preserved: only `index.js`, `registerCommands.js`, and `adapters/*` (plus the sanctioned voice modules `recorder.js`/`meetingSurface.js`) import `discord.js`/`@discordjs/voice`. `meetingClient.js` is transport-only (no Discord). The attachment poster is Discord-specific, so it is built in `index.js` (the composition root) and **injected** into `meetingSurface` — keeping `context.js` free of any Discord import.

**Authorization.** Because `/record` bypasses `router.js`, it also bypasses the router's single Policy Enforcement Point. So the dedicated handler re-runs the same `resolvePrincipal → authorize('linked', …)` check itself before doing anything — an unlinked caller is turned away with the standard "link your account" message, exactly as if the command had gone through neutral dispatch. If this check is ever removed, any guild member could drive live voice capture unauthenticated.

**Auto-stop.** `wireDiscordClient` listens for `voiceStateUpdate`; when a member leaves the channel currently being recorded and no non-bot member remains, it calls `meetingSurface.stop(guildId)` — the same path as `/record stop`. The recorded channel is read from the live session via `meetingSurface.activeVoiceChannel(guildId)` (stored opaquely, so `meetingSurface` keeps no `discord.js` dependency), which keeps the head-count check honest and makes the listener a no-op once a session has been torn down.

## Deployment

`meeting` is a private Railway service (`meeting.railway.internal:<PORT>`), like the other services: `platform_auth` consumer keys, `/health`, Dockerfile build (ffmpeg installed in the image), GitHub-connected auto-deploy on push to `staging`. It needs AWS credentials (Transcribe, via the standard chain), an `llm` consumer key (for minutes), and its own `CONSUMER_KEYS` set. The bot gets a `meeting` consumer key (`MEETING_API_KEY`) and `MEETING_BASE_URL=http://meeting.railway.internal:<PORT>`; the WebSocket rides Railway's private network. If `MEETING_BASE_URL` is unset the bot boots fine and `/record` reports "not configured" — the feature degrades gracefully.

## Known limitations & live-verify items

- **Transcription re-billing + unbounded memory:** the current session model re-transcribes the whole buffer on every `/transcript` poll and at stop, which re-bills AWS, and it holds every meeting's PCM in memory for the meeting's life. The intended fix is a persistent per-speaker Transcribe stream fed incrementally (finalized words never re-sent) — Misty #121. There is **no length cap by default** (`max_meeting_ms=None`): a meeting runs until `/record stop` or auto-stop-on-empty, so a genuinely marathon meeting with people continuously present can grow memory without bound and OOM the service. Auto-stop-on-empty covers the common case; set `MAX_MEETING_MS` to re-enable a hard bound until #121 lands.
- **Opus decode assumption:** the service decodes forwarded Discord Opus with a specific ffmpeg input (`-f data -c:a libopus`); this needs live confirmation against the real byte stream (fallback: Ogg-wrapped input).
- **Per-frame decode cost:** one ffmpeg invocation per ~20 ms Opus frame — fine for small meetings; batch before decode if it bites.
- **Concurrency:** one AWS Transcribe stream per active speaker; watch the account's concurrent-stream limit.
- **Not built yet:** the in-meeting `/ask` Q&A feature (only the `GET /transcript` hook it will use).
