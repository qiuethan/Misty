# Deployment

Production deployment guide for the team-tracking service.

This guide covers the **Level 1 security posture** — enough to run the service on the public internet without embarrassing yourself. It does not cover per-consumer API keys or scoped permissions; those are Level 2 (see `docs/ARCHITECTURE.md` for the roadmap).

## Threat model

What Level 1 protects against:

- **Casual scanning / opportunistic bots.** TLS + rate limit + strict headers means drive-by scanners find nothing exploitable.
- **Timing attacks on the API key.** Constant-time comparison in `src/api/auth.py` means an attacker cannot narrow the key by measuring response latency.
- **Traffic interception on the network.** HTTPS with modern TLS (1.2/1.3) via Let's Encrypt.
- **Key leakage via git or config accidents.** `.env` is gitignored; production secrets never live in a file that could reach a repo.

What Level 1 does **not** protect against:

- **A leaked API key.** There's only one, and it grants full access. If it leaks, you rotate the env var and restart. Level 2 (per-consumer keys) fixes this.
- **A malicious consumer.** Any key holder can call any endpoint. Level 2 (scopes) fixes this.
- **Insider-level abuse.** If someone with prod access exfiltrates the DB, no in-band protection stops it. This is a hosting/access-control concern, not an API concern.

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
```

Generate the API key:

```bash
python -c "import secrets; print('tt_' + secrets.token_urlsafe(32))"
```

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

### Rotating the API key

1. Generate a new key: `python -c "import secrets; print('tt_' + secrets.token_urlsafe(32))"`
2. Update `API_KEY` in the secret store
3. `sudo systemctl restart team-tracking`
4. Update every consumer with the new key
5. Once every consumer is verified working, the old key is gone

Because there's only one key today, rotation is a **flag day** — every consumer must be updated in a narrow window. Level 2 (per-consumer keys) removes this pain by letting keys overlap during a rotation window.

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
- [ ] Request without `X-API-Key` returns 401
- [ ] Request with wrong key returns 401
- [ ] Request with correct key returns data
- [ ] `curl -sSI https://team-tracking.utmist.ca/openapi.json` shows `strict-transport-security`, `x-frame-options: DENY`, etc.
- [ ] TLS grade check: `https://www.ssllabs.com/ssltest/analyze.html?d=team-tracking.utmist.ca` should be A or A+
- [ ] Rate limit: hammer 200 requests fast; the tail should get 429s
- [ ] Log files exist and are being written to
- [ ] `sudo systemctl status team-tracking` shows active + recent restart absent

## When it's time to level up

Once you have more than one consumer (e.g. Discord bot + docs catalog + one human dashboard), move to Level 2:

- Per-consumer API keys table (`api_keys` — hashed at rest, revocable, named)
- Scopes per key (`people:read`, `memberships:write`, `admin`)
- Structured request audit log middleware
- Key rotation without flag days

See `docs/ARCHITECTURE.md` for the design sketch. Level 2 is a separable sub-project.
