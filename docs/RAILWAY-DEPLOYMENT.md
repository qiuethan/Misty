# Railway Deployment (staging + production)

Deploys team-tracking, documentation-system, and discord-bot to Railway, backed
by Neon Postgres (a branch per environment). Repo-side config lives in each
service's `Dockerfile` + `railway.json`; the steps below are the account-side
setup you run in the Railway + Neon dashboards / CLIs.

## Prerequisites
- A Railway account + the `railway` CLI (`railway login`).
- A Neon account.
- `uv` locally (for the key-provisioning script).

## Branching + auto-deploy model
Each Railway environment is wired to a git branch. Merging a PR flips a deploy.

```
feature branch  ──PR──▶  staging  ──PR──▶  main
                          │                  │
                          ▼                  ▼
                    Railway staging   Railway production
                    (auto-deploy)     (auto-deploy)
```

- **`staging`** is the integration branch. Feature PRs target it (it's the repo
  default). Every merge auto-deploys to the `staging` Railway environment
  (staging Neon branch + staging Discord app).
- **`main`** is the release branch. **PRs to `main` may only come from
  `staging`** — enforced by the `main-source-guard` workflow
  ([`.github/workflows/main-source-guard.yml`](../.github/workflows/main-source-guard.yml)),
  which fails any PR to `main` whose head is not `staging`. Every merge to
  `main` auto-deploys to the `production` Railway environment.
- Both branches are protected; all four CI checks are required.

## 1. Neon: databases + branches
Create **two Neon projects** — `team-tracking` and `documentation-system` (each
service owns its DB). In each project you get a `main` branch (= production);
create a second branch named `staging` (copy-on-write from main). Copy the four
connection strings (2 projects × 2 branches). Use the `postgresql+psycopg://…`
form (append `?sslmode=require` if not present).

## 2. Railway: project, environments, services
1. Create a Railway project; it starts with a `production` environment — add a
   `staging` environment too.
2. Add three services from this repo, each with its **root directory** set:
   - `services/team-tracking`
   - `services/documentation-system`
   - `discord-bot`
   Railway picks up each service's `railway.json` (Dockerfile build, start
   command, health check, and — for the APIs — the `alembic upgrade head`
   pre-deploy step).
3. Keep the two APIs **private** (no public domain). The bot needs no domain.

## 3. Environment variables
Set these per environment (staging vs production) per service:

| Var | team-tracking | documentation-system | discord-bot |
|---|---|---|---|
| `DATABASE_URL` | tt Neon branch | docs Neon branch | — |
| `API_KEY` | a strong random secret | a strong random secret | — |
| `TT_ENV` | `staging` / `production` | — | — |
| `DIRECTORY_BASE_URL` | — | `http://${{team-tracking.RAILWAY_PRIVATE_DOMAIN}}:${{team-tracking.PORT}}` | same |
| `DIRECTORY_API_KEY` | — | *(set by the provisioning script — step 4)* | *(set by the script)* |
| `DISCORD_TOKEN` | — | — | staging app / prod app token |
| `DISCORD_CLIENT_ID` | — | — | per app |
| `DISCORD_GUILD_ID` | — | — | test guild (staging) / blank (prod) |
| `ENABLE_DISCORD` | — | — | `true` |
| `ENABLE_WEB` | — | — | `false` |

Deploy team-tracking first (its pre-deploy runs migrations on the Neon branch).

## 4. Provision the directory keys
Once team-tracking is up + migrated in an environment, mint + wire the scoped
consumer keys:

```bash
railway login          # once
TT_DATABASE_URL="<team-tracking Neon branch DATABASE_URL for this env>" \
  ./scripts/provision-directory-key.sh staging      # then: production
```

This issues scoped `team-tracking-keys` for discord-bot + documentation-system
and sets each service's `DIRECTORY_API_KEY`. Re-running issues a fresh key and
repoints the consumer; the previous key stays active until you revoke it
manually (`team-tracking-keys revoke <id>`).

## 5. Verify
- APIs: `railway run --service team-tracking bash -c 'curl -s localhost:$PORT/health'` → `{"status":"ok"}`; pre-deploy logs show `alembic upgrade head` ran.
- Bot: Railway logs show `Bot ready as …` — staging bot appears in the test guild; prod bot registers globally.
- End-to-end: run a bot command in the staging guild → reaches staging team-tracking → staging Neon branch.

## Notes
- APIs bind **`--host 0.0.0.0`**. Railway's IPv6 private network routes to the
  container's port regardless of the bind family, and `0.0.0.0` is what
  Railway's healthcheck reaches (an IPv6-only bind like `::` fails healthcheck
  on Debian's default kernel config). If service-to-service calls
  (bot → team-tracking) fail, check the `DIRECTORY_BASE_URL` reference next.
- Staging uses the **separate staging Discord application** + private test guild,
  so staging commands never touch the real UTMIST server.
