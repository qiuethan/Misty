# Deployment

Production deployment guide for the team-tracking service.

This guide covers **Levels 1 + 2** of the security posture:

- **Level 1** (infrastructure): TLS termination, per-IP rate limiting, HSTS/CSP headers, constant-time key comparison, secret handling outside `.env`.
- **Level 2** (auth model): per-consumer API keys stored hashed with argon2, per-endpoint scope enforcement, revocation without a flag day, structured JSON audit log for every request.

## Threat model

What this posture protects against:

- **Casual scanning / opportunistic bots.** TLS + rate limit + strict headers means drive-by scanners find nothing exploitable.
- **Timing attacks on any API key.** All key comparisons are constant-time (`secrets.compare_digest` for the env bootstrap key, argon2 for DB-issued keys).
- **Traffic interception.** HTTPS with modern TLS (1.2/1.3) via Let's Encrypt.
- **A leaked API key.** DB-issued keys are per-consumer, scoped, and revocable in seconds — no flag day, no other consumers affected.
- **A compromised consumer.** Scopes limit blast radius. A leaked `discord-bot` key with only `people:read` can't create memberships or leak person emails via a mutation.
- **Key theft from disk.** Only argon2 hashes are stored in the DB — plaintext is shown once at issuance and never persisted.
- **Silent abuse.** Every request lands in the structured audit log with `key_name` attributed cryptographically (not self-declared).

What this posture does **not** protect against:

- **Insider-level abuse.** If someone with prod DB access exfiltrates the whole table, no in-band protection stops it. This is a hosting/access-control concern.
- **A compromised admin key.** The `admin` scope is a wildcard. Only grant it to keys you trust, and rotate them promptly if suspicious.
- **DDoS beyond the rate-limiter's throughput.** Caddy's per-IP limit trips casual abusers; a real DDoS needs upstream mitigation (Cloudflare, etc.).

## Prerequisites

- A Linux host with a public IP (a small VPS is fine — Hetzner, DigitalOcean, Fly, Oracle Free Tier)
- DNS pointed at that host (e.g. `team-tracking.utmist.ca` A record → server IP)
- Ports 80 and 443 open (Caddy needs 80 for Let's Encrypt's HTTP-01 challenge)
- Docker + Docker Compose for the Postgres container (or a managed Postgres)
- A place to run the FastAPI app: systemd unit, docker-compose service, or a process manager

## Architecture

```
Internet
   │  HTTPS (443)
   ▼
┌──────────────────────────┐
│ Caddy or nginx           │  ← TLS termination, rate limit, headers
└─────────────┬────────────┘
              │  HTTP (localhost:8000)
              ▼
┌──────────────────────────┐
│ uvicorn / gunicorn       │  ← FastAPI app
└─────────────┬────────────┘
              │  postgresql+psycopg (localhost:5433 or managed)
              ▼
┌──────────────────────────┐
│ Postgres 16              │
└──────────────────────────┘
```

The API and Postgres never talk to the internet directly. Only Caddy is exposed.

## Step 1: Provision Postgres

Two options.

### Option A: Docker Compose (matches dev)

Same as local dev, but on the production host:

```bash
docker compose up -d postgres
```

Change `POSTGRES_PASSWORD` in `docker-compose.yml` first — the default is `dev_password` which is fine for dev, not for anywhere else. Generate a strong one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Option B: Managed Postgres (Neon, Supabase, RDS, Fly Postgres)

Point `DATABASE_URL` at the managed instance. Nothing else changes — SQLAlchemy Core is portable across every Postgres-family provider.

For any managed option, restrict IP access to the API server if the provider supports it.

## Step 2: Deploy the API

Run migrations first, then start the server. Any process manager works:

### systemd unit (recommended for a VPS)

Create `/etc/systemd/system/team-tracking.service`:

```ini
[Unit]
Description=UTMIST team-tracking API
After=network.target
Wants=postgres.service

[Service]
Type=simple
User=team-tracking
WorkingDirectory=/opt/team-tracking
EnvironmentFile=/etc/team-tracking/secrets.env
ExecStartPre=/opt/team-tracking/.venv/bin/alembic upgrade head
ExecStart=/opt/team-tracking/.venv/bin/uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5

# Sandboxing
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/log/team-tracking
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

`/etc/team-tracking/secrets.env` (mode 0600, owned by `team-tracking:team-tracking`):

```
DATABASE_URL=postgresql+psycopg://team_tracking:PASSWORD@localhost:5433/team_tracking
API_KEY=GENERATED-STRONG-KEY-HERE
TT_ENV=production
```

**`TT_ENV`** declares which environment tier this instance represents. Values
are `local` | `staging` | `production` (typed `Literal` in `src/config.py`, so
a typo like `Production` or trailing whitespace crashes at startup instead of
silently disabling safety gates). In production it MUST be `production` — this
enables two defense-in-depth gates around the `dev:spoof` scope: the
`team-tracking-keys issue` CLI refuses to issue keys with that scope, and the
request-time middleware 403s any request bearing such a key. Both fire only
when `TT_ENV=production`. Local dev omits `TT_ENV` and gets the default
(`local`), which permits `dev:spoof`.

Generate the env bootstrap `API_KEY` (a plain random string — **do not** give it a `tt_` prefix):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> Why no `tt_` prefix: the auth layer routes any key shaped like `tt_<prefix>_<secret>` to the DB-issued-key path and verifies it against the `api_keys` table. A `tt_`-prefixed env key would take that path, find no matching row, and be rejected — it would never be compared against `API_KEY`. Keep the env bootstrap key in a plain format so it falls through to the env check.

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now team-tracking
sudo systemctl status team-tracking
```

## Step 3: Front with Caddy (or nginx)

### Caddy (simpler; auto TLS)

```bash
# Install Caddy (Ubuntu/Debian)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

**For rate limiting**, Caddy needs a plugin — build a custom binary with `xcaddy`:

```bash
# Install xcaddy
sudo apt install -y golang-go
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest

# Build Caddy with the rate-limit module
~/go/bin/xcaddy build --with github.com/mholt/caddy-ratelimit

# Replace the default caddy binary
sudo mv caddy /usr/bin/caddy
```

Then copy `deploy/Caddyfile` from this repo to `/etc/caddy/Caddyfile`, edit the domain, and reload:

```bash
sudo cp /opt/team-tracking/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy auto-obtains a Let's Encrypt cert on first request. Verify:

```bash
curl -v https://team-tracking.utmist.ca/openapi.json
```

### nginx (if you'd rather not build Caddy)

`deploy/nginx.conf.example` is a starting point. You'll also need certbot for TLS:

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d team-tracking.utmist.ca
sudo cp /opt/team-tracking/deploy/nginx.conf.example /etc/nginx/sites-available/team-tracking
sudo ln -s /etc/nginx/sites-available/team-tracking /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Step 4: Secret handling — do not use `.env` in production

`.env` is fine for local dev — it holds the dummy `dev-api-key-change-me` value that any deploy environment should overwrite. In production, load secrets from one of these:

### Simplest: systemd `EnvironmentFile` (what the systemd unit above uses)

- File at `/etc/team-tracking/secrets.env`
- Mode `0600`, owned by the service user
- Never in git, never in the app's working directory
- Rotated by editing the file and running `sudo systemctl restart team-tracking`

### Better: a secret manager

- **1Password Connect** — good for small teams already on 1Password
- **HashiCorp Vault** — heavier but auditable
- **Cloud provider secret managers** (AWS SecretsManager, GCP Secret Manager, Azure Key Vault) — pair with an init script that fetches at startup

Whatever you pick, the flow is always: secret manager → environment variables at startup → `pydantic-settings` reads env → app never sees a file.

### Rotating the env `API_KEY` (Level 1 bootstrap key)

The env `API_KEY` is now a **grace-period bootstrap key** — it exists so brand-new deployments can hit the API before any DB-issued keys exist. It has admin scope. Rotate it the same way you rotate any env secret:

1. Generate a new value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Update `API_KEY` in the secret store
3. `sudo systemctl restart team-tracking`
4. Update any consumer still using the env key

Ideally, only your bootstrap tooling ever uses the env key. Every real consumer should have its own DB-issued key (see next section) so it can be revoked without disturbing others.

### Issuing DB-issued keys (Level 2 — recommended for every real consumer)

Each consumer (Discord bot, docs catalog, sync job, etc.) should have its own scoped key.

**Issue a key** via the CLI, which talks directly to Postgres:

```bash
uv run team-tracking-keys issue --name discord-bot --scopes people:read memberships:read
```

The plaintext key is printed **once** to stdout. Capture it and hand it to the consumer:

```bash
uv run team-tracking-keys issue --name discord-bot --scopes people:read memberships:read > /tmp/key.txt
# The file now contains: tt_<prefix>_<secret>
# Hand this to the consumer, then delete the file.
```

**Available scopes:**

| Scope | Grants |
|---|---|
| `people:read` | GET /people, GET /people/{id} |
| `people:write` | POST /people, PATCH /people/{id} |
| `teams:read` | GET /teams, GET /teams/{id}, GET /teams/by-slug/{slug} |
| `teams:write` | POST /teams, PATCH /teams/{id} |
| `role_kinds:read` | GET /role_kinds, GET /role_kinds/{id} |
| `memberships:read` | GET /memberships, GET /memberships/{id} |
| `memberships:write` | POST /memberships, PATCH /memberships/{id}, POST /memberships/{id}/end |
| `providers:read` | GET /providers, GET /providers/{id} |
| `identifiers:read` | GET /people/by-identifier/{provider}/{external_id}, GET /people/{id}/identifiers |
| `identifiers:write` | POST / PATCH / DELETE /people/{id}/identifiers[/{provider}] |
| `admin` | Wildcard — grants every scope. Use only for trusted operators / migrations. |

Example: a Discord bot that resolves users and reads rosters needs `people:read memberships:read identifiers:read`.

**List issued keys:**

```bash
uv run team-tracking-keys list                # all keys, including revoked
uv run team-tracking-keys list --active-only  # only active + non-revoked
```

The CLI never prints plaintext or hashes on list — only metadata (name, prefix, active flag, scopes).

**Revoke a key** (soft-delete — history is preserved for audit):

```bash
uv run team-tracking-keys revoke <api_key_id>
```

Revocation is instant — the next request with the revoked key returns 401.

### Rotating a DB-issued key (no flag day)

Because each consumer has its own key, rotation is safe and staged:

1. Issue a NEW key for the same consumer: `... issue --name discord-bot-v2 --scopes ...`
2. Update the consumer to use the new key (deploy, restart, whatever)
3. Verify the consumer is working via the audit log (grep for `"key_name":"discord-bot-v2"`)
4. Revoke the OLD key: `... revoke <old-key-id>`

Zero downtime, no coordination window with other consumers.

### Reading the audit log

Every request emits one JSON line to stdout. Ship stdout to your log aggregator (journald + `journalctl -u team-tracking`, Loki, CloudWatch, Datadog — anything works). Each line looks like:

```json
{"ts":"2026-07-01T05:41:20.606Z","request_id":"682e63ff-...","method":"POST","path":"/people","status":201,"duration_ms":52,"key_name":"discord-bot","is_bootstrap":false,"remote":"203.0.113.7"}
```

**Useful greps:**

```bash
# Everything discord-bot did in the last hour
journalctl -u team-tracking --since '1 hour ago' | grep '"key_name":"discord-bot"'

# All failed auth attempts (401s)
journalctl -u team-tracking --since today | grep '"status":401'

# All scope denials (403s) — spot a consumer trying to over-reach
journalctl -u team-tracking --since today | grep '"status":403'

# Requests using the deprecated env bootstrap key
journalctl -u team-tracking --since today | grep '"is_bootstrap":true'
```

That last one is your migration progress bar — as consumers move to DB-issued keys, `is_bootstrap:true` lines should drop to zero.

## Step 5: Backups

Postgres data is the SoT. Minimum viable backup:

```bash
# Daily backup via cron, encrypted, off-host
0 3 * * * pg_dump -Fc team_tracking | gpg --encrypt --recipient backups@utmist.ca > /var/backups/tt-$(date +\%F).dump.gpg
```

Ship the encrypted dumps somewhere off the host (S3, Backblaze, another VPS). Test the restore path at least once — an untested backup is a hopeful backup.

## Verification checklist

After deploying, run through this list from an external machine:

- [ ] `curl -v http://team-tracking.utmist.ca/openapi.json` — returns 301 to HTTPS
- [ ] `curl https://team-tracking.utmist.ca/openapi.json` — returns the OpenAPI JSON
- [ ] Request without `X-API-Key` returns 401 (with an audit line for it)
- [ ] Request with wrong key returns 401
- [ ] Request with a scope-limited DB key to an out-of-scope endpoint returns 403
- [ ] Request with correct scoped key returns 200/201
- [ ] `curl -sSI https://team-tracking.utmist.ca/openapi.json` shows `strict-transport-security`, `x-frame-options: DENY`, etc.
- [ ] TLS grade check: `https://www.ssllabs.com/ssltest/analyze.html?d=team-tracking.utmist.ca` should be A or A+
- [ ] Rate limit: hammer 200 requests fast; the tail should get 429s
- [ ] Audit log lines are landing in your aggregator (grep for a recent `request_id`)
- [ ] `sudo systemctl status team-tracking` shows active + recent restart absent
- [ ] Revoke a test key and verify 401 on the next request

## When it's time to level up further

- **Level 3 (context-dependent):**
  - OAuth2/OIDC for human users of a web UI backed by this API
  - HMAC request signing or mTLS for the highest-trust callers
  - IP allowlisting per key
  - `api_request_log` DB-backed audit table (in addition to stdout log) for queryable investigations
  - Compliance-driven controls (SOC2 audit trail retention, key rotation SLA, etc.)

Most of these are only worth the work if a compliance requirement forces them.
