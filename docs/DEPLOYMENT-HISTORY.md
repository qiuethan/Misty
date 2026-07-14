# Deployment Design & Lessons

Why the UTMIST ops platform is deployed the way it is, and the non-obvious lessons we learned standing it up. For the operational **runbook** (how to redeploy, provision keys, verify, roll back), see [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md). This document explains the *choices*.

---

## The shape

```
                                Railway staging environment           Railway production environment
GitHub                          ├── team-tracking service              ├── team-tracking service
├── staging branch  ──deploys──▶├── documentation-system service       ├── documentation-system service
└── main branch     ──deploys──▶└── discord-bot service                └── discord-bot service
                                        │                                      │
                                        ▼                                      ▼
                                  Neon: team-tracking + docs-system      Neon: team-tracking + docs-system
                                  projects, `staging` branch of each     projects, `main` branch of each
```

Two environments (staging, production). Three shared services (each is one Railway entity; variable *values* differ per environment). Two Neon projects (one per API), each with two branches (one per environment). One repo, two long-lived branches, feature → staging → main.

---

## The choices, and why we made them

### Railway over a self-hosted VPS

UTMIST has volunteer turnover: the person who set up a box will graduate, and the next cohort inherits a mystery server they didn't provision. Railway removes the "who owns the box" question — deploys are `git push`, there's no OS to patch, and the next volunteer inherits a dashboard, not a Linux system. Cost is ~$5–20/mo; the turnover-proofing is worth more than that.

### Neon over self-hosted Postgres

Same reasoning, plus Neon's **branching** feature. `staging` is a copy-on-write branch of prod — realistic data, isolated writes, and reset-able in seconds. A separately-seeded staging DB would drift from prod forever and require ongoing sync work.

### One Neon project per service

Each service owns its DB. team-tracking's DB never contains a doc catalog entry; docs-system's DB never contains a person record. Services talk over HTTP, not shared tables. Matches the "each service is a source of truth for one domain" principle — and Neon's free-tier limits mean each service gets its own storage + compute budget.

### Shared services with per-environment variables

Three services, each existing once at the Railway project level and exposed in *both* environments with different variable values. This is Railway's idiomatic pattern: adding a variable later is one dashboard change, not two. Cross-service references (`${{team-tracking.RAILWAY_PRIVATE_DOMAIN}}`) resolve to the right environment automatically.

### Branching model: feature → staging → main

- **`staging` is the default branch.** Feature PRs auto-target it. Merges auto-deploy to the Railway staging environment.
- **`main` is the release branch.** Only PRs from `staging` can merge — enforced by the `main-source-guard` workflow. Merges auto-deploy to production.
- Both branches require the 4 CI checks; main additionally requires the source-guard.

This gives you the loop of `push to feature → PR → staging → real staging deploy → validate → promote to main → production deploy`, with no branch or environment able to skip validation.

### Per-consumer scoped API keys

The bot and docs-system authenticate to team-tracking with their **own** scoped `tt_…` keys — not a shared admin bootstrap. A leaked bot key can't be used by docs-system, each is revocable independently, and the audit log records who did what by name.

Keys are minted by `scripts/provision-directory-key.sh <env>`, which runs `team-tracking-keys issue` against that environment's Neon branch and writes each key onto its Railway consumer with `railway variables --set`. One command per environment.

Scopes:
- **discord-bot:** `people:read people:write people:elevate identifiers:read identifiers:write teams:read teams:write memberships:read memberships:write role_kinds:read` (needs identity + membership management; `people:elevate` lets `/seed` promote people to `admin`/`superuser`)
- **documentation-system:** `people:read teams:read` (only needs to look up an owner's label)

### CI on every PR to `staging` or `main`

`.github/workflows/ci.yml` runs:
- **`python-test`** — Postgres 16 service container, applies migrations, runs the full pytest suite
- **`documentation-system-test`** — Postgres 16 service container, runs `alembic upgrade head`, then `pytest` with `RUN_PG_TESTS=1` (does not yet run ruff — deferred)
- **`python-lint`** — ruff check + format
- **`node-test`** — the bot's `node --test` suite
- **`docker-build`** — builds *and boot-smoke-tests* all three images (`python -c "import src.api.app"` for the APIs, `node --check src/index.js` for the bot)

Plus `main-source-guard` on PRs to `main`. All required — nothing red merges.

---

## Non-obvious things worth knowing (lessons)

Three sharp edges bit us during the first live deploy. Each is documented so nobody has to learn them from a failed deploy.

### Wrap shell-variable start commands in `sh -c`

Railway executes a string `startCommand` in `railway.json` directly — no shell interpretation. So `uvicorn ... --port ${PORT}` passes the literal string `${PORT}` to uvicorn, which rejects it with `Error: Invalid value for '--port': '${PORT}' is not a valid integer.`

Wrap it explicitly:
```json
"startCommand": "sh -c 'uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}'"
```
The `sh -c` runs a shell that expands `$PORT` (which Railway injects at container start) before uvicorn sees it.

### Bind APIs to `0.0.0.0`, not `::`

On the default `python:3.11-slim` kernel, binding to `::` binds **IPv6-only**. Railway's healthcheck reaches the container over IPv4 and finds no listener, so every deploy fails healthcheck even though uvicorn started fine and migrations succeeded.

Bind to `--host 0.0.0.0`. Railway's private network routes to the container's port regardless of bind family, so internal service-to-service calls still work.

### If you cross-reference a service's `PORT`, set it explicitly

Railway's cross-service template `${{team-tracking.PORT}}` resolves from the **variable store**. `PORT` as Railway injects it at container runtime is *not* in the variable store — so the template resolves to an empty string, and consumers try to hit `http://team-tracking.railway.internal:` with no port, which fails.

Set `PORT=8000` (or whatever you like) as an **explicit** Railway variable on any service being referenced. Railway respects your value at container start, *and* the template ref now resolves correctly on consumers.

### Both branches require an approving review

`staging` and `main` are both branch-protected with `required_approving_review_count: 1`. Auto-merging your own PR isn't possible; use the standard review flow or an admin merge for genuinely trivial changes (e.g. docs-only). Removing this requirement would speed things up but weaken the safety net — don't do it without a real reason.

---

## Release log

### 2026-07-14 — security-review remediation (staging)

The remediation from the 2026-07-13 security review merged to `staging`. In one release:

- **team-tracking:** an SSRF egress guard on outbound fetches; a `PATCH /people`
  privilege-escalation fix backed by a new **`people:elevate`** scope (required to
  set a non-`member` `access_level` on `POST`/`PATCH /people`; plain `people:write`
  can no longer escalate, `admin` still satisfies it); a membership temporal
  no-overlap constraint, `400`s on bad foreign-key references, and `active_only`
  filtering.
- **documentation-system:** URL dedup hardened via a partial unique index on
  `url_normalized WHERE active`.
- **verification:** `confirm-code` replay hardening — an idempotent replay on a
  consumed-but-unexpired code now re-checks the submitted code (no email leak on a
  wrong code) and enforces the same attempt limit (`429`).
- **llm:** `POST /chat` now requires the dedicated **`chat`** scope (was: any valid key).

**Migrations applied on staging** — team-tracking **007** (membership no-overlap via a
`btree_gist` exclusion constraint; the migration creates the `btree_gist` extension) and
documentation-system **004** (the partial unique index above). Both run automatically as
Railway's `preDeployCommand` (`alembic upgrade head`).

**CI:** added the **`documentation-system-test`** job (Postgres 16 service +
`alembic upgrade head` + `pytest` with `RUN_PG_TESTS=1`; ruff deferred).

**Keys:** the discord-bot directory key was rotated to add `people:elevate`
(`scripts/provision-directory-key.sh` updated) so its `/seed` can promote people to
`admin`/`superuser`.

**Discord:** `/doc` was promoted from beta to stable and now registers globally.

## Current state

- Both environments fully deployed and healthy.
- APIs are **private-only** on Railway (no public domains). Only in-project services (the bot, docs-system) reach them, over Railway's internal network. Add a public domain later if an external caller ever needs one — both APIs already have API-key auth.
- **Discord commands.** Stable commands (`/link`, `/whoami`, `/seed`) are registered globally on the production bot. Beta commands (`/team`, `/my-teams`) are still guild-scoped to the test guild — flip `beta: false` in each module + re-run `registerCommands` to promote them to production when confident.
- **Migrations run automatically** as Railway's `preDeployCommand` on the two API services — `alembic upgrade head` against the environment's Neon branch before every deploy. Idempotent.

---

## Redeploy and rollback

**Deploying is merging.** Merge to `staging` → Railway rebuilds and deploys staging. Merge `staging → main` → Railway does the same for production. No other trigger needed.

**Manual redeploy** (rare — after a Railway hiccup):
```bash
railway service redeploy --service <name> --environment <staging|production> --yes
```

**Rolling back:**
```bash
# Roll back staging:
git checkout staging && git revert <bad-commit> && git push
# Roll back production: revert on staging first, then promote via a staging → main PR.
```

If the bad change included a schema migration, downgrade it against the environment's Neon branch:
```bash
railway run --service team-tracking --environment <env> -- alembic downgrade -1
```
Every migration ships with a working `downgrade()` — that's a review requirement.

Neon also offers point-in-time recovery: reset a branch to an earlier snapshot from the Neon dashboard. A lifeline if a bad migration *and* data corruption happen together.

---

## Access

- **Railway project (`Bot-Deploy`)** — invited via the Railway workspace.
- **Neon projects** — invited via each project's settings.
- **GitHub repo** — standard PR flow; branch protection enforces review + CI.
- **Discord bots** — tokens live *only* in Railway (per-environment); the developer portal shows the app, but you need to be invited as a team member to see it there.

**Superuser seeding** is a controlled action — see the runbook's "seed the first admin" section. Only existing superusers/admins can promote more people from Discord (`/seed`).

---

## Explicitly out of scope (for now)

- A local `docker-compose.yml` for the whole platform. The existing native flows (`npm run dev:web` for the bot playground, per-service quick-starts for the APIs) cover local dev better than a compose file would.
- Any CD beyond Railway's built-in auto-deploy. Railway watches the branches; no extra pipeline needed.
- Custom domains for the APIs — they're private-only until an external caller appears.
- Observability beyond Railway's built-in logs and metrics — sufficient for current scale.

## Nice-to-haves if the itch strikes

- **SHA-pin CI actions** (currently on major tags) for supply-chain hardening.
- **Add `concurrency:` blocks to CI** so superseded PR pushes auto-cancel.
- **Custom domain** for team-tracking or docs-system if a dashboard ever wants to hit them from outside Railway.
