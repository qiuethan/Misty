# meeting

Stateful HTTP + WebSocket service that ingests live per-speaker Discord voice audio, transcribes it via Amazon Transcribe streaming, and produces a rolling transcript plus end-of-meeting minutes and a PDF for UTMIST's internal consumers (the Discord bot).

## What this service does

A Discord bot opens one WebSocket per meeting and streams each speaker's raw Opus audio frame-by-frame as it arrives from voice channels. `meeting` decodes each frame to PCM (via ffmpeg), buffers it per speaker, and periodically re-runs Amazon Transcribe streaming over the buffered audio to keep a rolling transcript available. When the meeting ends (`POST /stop` or a client disconnect), it assembles the final transcript, calls the `llm` service to summarize decisions/action items into structured minutes, renders a PDF, and mixes all speaker tracks into one MP3 — returning transcript, minutes, PDF, and audio as one response.

Two design choices shape everything:

- **Stateful, but ephemeral.** Unlike `llm`, this service *does* hold state — one `MeetingSession` per active meeting, alive only in process memory for the meeting's duration (see the STATEFULNESS note below). There is no database and nothing survives a restart.
- **`llm` as the summarization choke point.** `meeting` never calls Bedrock directly. It POSTs the assembled transcript to the `llm` service's `/chat` endpoint (via `LLM_BASE_URL`/`LLM_API_KEY`) and parses the completion into `Minutes`. Swapping models, providers, or prompts happens in `llm`, not here.

## Quick start

Prerequisites: Python 3.11+, [uv](https://github.com/astral-sh/uv), and **ffmpeg** on `PATH` (used to decode/mix audio — see below). No Docker or database needed for local dev.

```bash
# 0. From the repo root, enter the service directory (all commands below run here)
cd services/meeting

# 1. Copy environment config
cp .env.example .env

# 2. Install dependencies (including dev tools)
uv sync --extra dev

# 3. Start the API server
uv run uvicorn src.api.app:app --reload --port 8003
```

> The repo is a single [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) (root `pyproject.toml` with `[tool.uv.workspace] members = ["services/*", "packages/*"]`, one root `uv.lock`). meeting depends on the shared `platform-auth` package (`[tool.uv.sources] platform-auth = { workspace = true }`) but the commands above are unchanged — `uv sync` and `uv run pytest` work exactly as shown when run from this directory.

The API is now at `http://localhost:8003`. Interactive Swagger UI is at `http://localhost:8003/docs`; the machine-readable schema is at `http://localhost:8003/openapi.json` (HTTP routes only — the WebSocket route isn't represented in OpenAPI).

The default dev bootstrap key is `dev-api-key-change-me` (set in `.env`, carries the `admin` wildcard scope). Pass it as `X-API-Key` on the HTTP endpoints, or `?key=` on the WebSocket.

**Ports:** this service runs on **8003** (team-tracking uses 8000, documentation-system 8001, llm 8002) — chosen to avoid colliding when running the services locally.

### Environment tiers (`MEETING_ENV`)

`MEETING_ENV` declares which environment this instance represents: `local` (default), `staging`, or `production`. Outside `local`, `create_app()` calls `verify_production_secrets()` and **refuses to start** unless `API_KEY` is overridden from the dev default, `AWS_REGION` is set, and `LLM_BASE_URL` is set — a misconfigured deploy dies at boot, not on first request.

### Configuration

All settings load from the environment (`src/config.py`, `.env` in dev):

| Var | Default | Purpose |
|-----|---------|---------|
| `MEETING_ENV` | `local` | Environment tier (`local` / `staging` / `production`). |
| `API_KEY` | `dev-api-key-change-me` | Env-bootstrap key; carries `admin` scope. Must be overridden outside `local`. |
| `CONSUMER_KEYS` | `""` | JSON array of per-consumer keys (see auth model). |
| `AWS_REGION` | `""` | Region for Amazon Transcribe streaming. Standard AWS credential chain also reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Required outside `local`. |
| `LLM_BASE_URL` | `""` | Base URL of the `llm` service (e.g. `http://llm.railway.internal:8002` in prod, `http://localhost:8002` in dev). Required outside `local`. |
| `LLM_API_KEY` | `""` | Consumer key this service presents to `llm`'s `X-API-Key`. |
| `REQUEST_TIMEOUT_S` | `60` | Per-request timeout when calling `llm` (seconds). |

## Auth model

Auth is scoped API keys via the shared `platform_auth` package, matching `llm` — **DB-free**, keys seeded from config, no `api_keys` table.

- Every HTTP request needs `X-API-Key`; the WebSocket takes the same key as a `?key=` query param (see below). A key is either the shared bootstrap env key (`API_KEY`, scope: `admin`) or a per-consumer key seeded from `CONSUMER_KEYS`.
- **`CONSUMER_KEYS` is a JSON array**, each entry `{"name", "prefix", "key_hash", "scopes"}`. At boot, the key store (`src/key_store.py`) parses it into an in-memory store satisfying `platform_auth`'s `ApiKeyStore` protocol — a malformed `CONSUMER_KEYS` fails fast at startup.
- Keys use the **`meeting_` envelope** (`meeting_<prefix>_<secret>`). There is a single scope, `meetings`, covering every endpoint (HTTP and WS) — this service has one internal consumer class (the Discord bot), so separate read/write/stream scopes were a deliberate simplification.

### Minting consumer keys

Use the `meeting-keys` CLI. It prints the plaintext key **once** to stdout and the `CONSUMER_KEYS` JSON entry to stderr — it does not (and cannot) write to any store:

```bash
uv run meeting-keys --name discord-bot --scopes meetings
# stdout: meeting_<prefix>_<secret>   (the key — give it to the consumer, shown ONCE)
# stderr: {"name": "discord-bot", "prefix": "...", "key_hash": "$argon2id$...", "scopes": ["meetings"]}
```

Append the printed JSON object to the service's `CONSUMER_KEYS` array and redeploy. To **revoke** a key, drop its entry from `CONSUMER_KEYS` and redeploy — there is no revoke command because there is no database.

## API at a glance

Every endpoint (HTTP and WS) requires the `meetings` scope; the `admin` wildcard also satisfies it.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe → `{"status": "ok"}`. No auth. |
| GET | `/meetings/{id}/transcript` | Poll the rolling transcript for an active session → `TranscriptView`. |
| POST | `/meetings/{id}/stop` | End the session: finalize transcript, generate minutes + PDF, mix audio, tear the session down → `StopResponse`. |
| WS | `/meetings/{id}/stream` | Live audio ingest + control channel (see below). |

`{id}` (`session_id`) must match `^[A-Za-z0-9_-]{1,64}$` — it's used to build a filesystem path for temp audio. A `session_id` unknown to the in-memory registry (never started, already stopped, or the process restarted) returns **404** on `/transcript` and `/stop`.

**`GET /meetings/{id}/transcript` → `TranscriptView`:** `{"segments": [{"speaker", "start_ms", "text"}, ...]}`. Re-runs transcription over each speaker's buffered-so-far audio, so successive polls can refine earlier text — this is a "periodic" view, not a diff/append stream.

**`POST /meetings/{id}/stop` → `StopResponse`:** `{"transcript", "minutes": {"summary", "decisions": [...], "action_items": [...]}, "pdf_b64", "audio_b64"}`. `pdf_b64`/`audio_b64` are base64-encoded bytes (PDF and mixed MP3 respectively); `audio_b64` is `null` if no speaker produced any audio.

### WebSocket: `WS /meetings/{id}/stream`

The wire contract the Discord-bot side mirrors.

**Connect:** `ws://.../meetings/{session_id}/stream?key=<consumer-key>&guild_id=<guild-id>`

- `key` (query param, preferred): validated against the key store before the socket is accepted; on failure the connection is rejected during the handshake. If `key` is omitted from the query string, the server instead accepts the socket and requires the *first* message to be a text frame `{"key": "..."}` — if that's missing, malformed, or invalid, the socket is closed with WS code **1008** (policy violation) before any audio is processed.
- `guild_id` (optional): passed to session creation; if omitted, `session_id` is used as the guild_id.
- An invalid `session_id` (fails the regex above) closes with code 1008 before a session is created.

**Once authenticated, two message types are accepted:**

1. **Control** (WebSocket text frame, UTF-8 JSON): `{"speaker_id": "<id>", "display_name": "<name>"}` — registers/updates the display name shown for a speaker_id. Send this whenever a speaker's identity becomes known (e.g. a Discord user joins voice). Unknown/malformed text frames are ignored, not fatal.
2. **Audio** (WebSocket binary frame), one raw Opus packet per frame, framed as:

   ```
   [2 bytes  big-endian uint16]  speaker_id_len
   [speaker_id_len bytes, UTF-8] speaker_id
   [8 bytes  big-endian uint64]  ts_ms
   [remaining bytes]             raw Opus packet payload
   ```

   i.e. a length-prefixed speaker id, then an 8-byte millisecond timestamp, then the raw Opus payload with no further framing. Truncated/undersized frames are dropped, not fatal.

**Disconnect:** if the client disconnects (or errors) without a preceding `POST /stop`, the server tears the session down itself (`session.discard()`) — a lightweight cleanup (delete the temp dir, deregister) that deliberately skips the finalize pipeline (transcription flush, minutes, PDF, audio mix), since that involves a blocking `llm` HTTP call not worth paying for on an abrupt drop.

## Private deploy (Railway)

This service is not exposed publicly. It sits on Railway's private network, addressed by internal consumers (the Discord bot) as `meeting.railway.internal:<PORT>` — mirroring how `llm` is reached internally. `railway.json` builds from `Dockerfile` (Dockerfile builder, build context = repo root), health-checks `/health`, and starts uvicorn bound to Railway's injected `${PORT}`.

## STATEFULNESS (read before deploying more than one instance)

Unlike `llm`, **this service holds state in process memory**: `SessionRegistry` (`src/sessions.py`) keeps one `MeetingSession` per active meeting — buffered per-speaker PCM, a live/rolling transcript, and a temp directory on local disk — for the lifetime of that meeting. This means:

- **Not horizontally scalable as-is.** A given `session_id`'s WebSocket, `/transcript` polls, and `/stop` call must all land on the *same* process/instance. Running multiple replicas behind a load balancer without sticky routing on `session_id` will misroute `/transcript` and `/stop` calls to a process that never saw that session.
- **Ephemeral by design — nothing is persisted.** A process restart or crash mid-meeting loses all in-flight state: buffered audio, the rolling transcript, everything. There is no database and no durable queue backing the session; `stop()`/`discard()` always deletes the session's temp dir. If a meeting's minutes/PDF/audio matter, the consumer (the bot) must call `POST /stop` and persist the response itself — this service will not retain it after replying.

## Live-verify caveats (flagged for sub-plan 3 integration, not this task)

A few integration assumptions are baked in and documented in-code, but need confirming against the real Discord bot / AWS account rather than unit tests:

- **Opus demuxer assumption** (`src/audio/decoder.py`): ffmpeg is invoked with `-f data -c:a libopus` (raw elementary-stream Opus, no container), on the assumption the bot's voice-receive stream yields bare Opus frames with no Ogg framing. If the bot instead Ogg-wraps packets before sending, this needs to change to `-f ogg -i pipe:0`.
- **Per-frame decode is not batched** (`src/api/wiring.py`'s `AudioAdapter`): each ~20ms Opus frame spawns its own ffmpeg subprocess. Correct, but not performant at scale — batching (buffer raw Opus per speaker, decode once per flush) is a follow-up.
- **Amazon Transcribe streaming** needs real AWS credentials (`AWS_REGION` + the standard credential chain) and realistic audio pacing to validate end-to-end; the test suite exercises `src/stt/transcribe.py` against a fake client only, never a live Transcribe session.

## Testing

```bash
uv run pytest
```

53 tests, no Docker, no network, no AWS credentials — ffmpeg calls and the Transcribe/LLM clients are faked via `app.dependency_overrides` and injected `deps`.

```bash
uv run ruff check .
uv run ruff format .
```

## Status

v0.1: stateful per-meeting session registry, live per-speaker audio ingest over WebSocket with binary frame parsing, periodic rolling-transcript polling, `llm`-backed minutes generation, PDF rendering, and final audio mixdown — all in-memory/ephemeral, with ffmpeg baked into the production image.

**Not implemented (by design):**

- **Persistence** — no database, no durable session store. A process restart loses all in-flight meetings.
- **Horizontal scaling** — one process must own a given session end-to-end; no shared session state across replicas.
- **True incremental streaming transcription** — `feed()` buffers and periodically re-transcribes rather than keeping one persistent Transcribe stream per speaker open; see `src/sessions.py`'s module docstring for the reasoning.
