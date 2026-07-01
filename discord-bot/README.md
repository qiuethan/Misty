# UTMIST Discord Bot

A thin Node.js application layer over the [team-tracking](../team-tracking) directory
API. v1 does one thing: link a Discord account to a pre-seeded directory `Person`,
behind a proper **auth layer** so future commands and role-based permissions slot
in cleanly.

It holds **no database and no business logic** — every action is an HTTP call to
the directory (the API-only source of truth).

## Commands

- `/link email:<your UTMIST email>` (public) — links your Discord account to your
  directory record. Your email must already be in the directory (execs seed
  members). No email verification yet — see the `// TODO: verification` in
  `src/linkService.js`.
- `/whoami` (linked) — shows which directory record you're linked to. Requires you
  to be linked; the auth layer handles the "not linked" case.

## Auth layer

The bot's gate is its authentication/authorization layer — the Discord-side
parallel to team-tracking's scoped-key auth.

- **Principal** (`src/auth/principal.js`) — the authenticated subject, `{ person }`
  in v1. Extension point for roles/memberships later.
- **Policy** (`src/auth/policy.js`) — each command declares `auth: 'public' | 'linked'`
  (default `'linked'`, fail-secure). Extends to role/team-admin policies without
  touching handlers.
- **Router** (`src/router.js`) — the single Policy Enforcement Point:
  authenticate → authorize → dispatch. Fails **closed** if the directory is
  unreachable.

## Setup

1. **Node 20+** required.
2. `cp .env.example .env` and fill in:
   - Discord app credentials (`DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_GUILD_ID`).
   - `DIRECTORY_BASE_URL` (e.g. `http://localhost:8000`).
   - `DIRECTORY_API_KEY` — issue one from team-tracking:
     ```bash
     cd ../team-tracking
     uv run team-tracking-keys issue --name discord-bot \
       --scopes people:read identifiers:read identifiers:write
     ```
3. `npm install`
4. `npm run register` — registers the slash commands to your guild (run once, or
   whenever command definitions change).
5. `npm start`

## Architecture

| File | Responsibility |
|---|---|
| `src/config.js` | Load + validate env. |
| `src/context.js` | Wire application services once. |
| `src/directoryClient.js` | The only module that knows the team-tracking HTTP shape. |
| `src/linkService.js` | Orchestrates the `/link` action. Holds the verification TODO. |
| `src/auth/principal.js` | Authentication: Discord id → Principal. |
| `src/auth/policy.js` | Authorization: policy + principal → allow/deny. |
| `src/router.js` | Policy Enforcement Point: authN → authZ → dispatch. |
| `src/messages.js` | Pure reply-string rendering. |
| `src/commands/*.js` | Thin discord.js interaction handlers + registry. |
| `src/index.js` | Client setup + interaction routing. |
| `src/registerCommands.js` | One-shot guild slash-command registration. |

## Testing

```bash
npm test    # node --test — unit tests for config, client, service, auth, router, render
```

The auth layer (principal, policy, router) and the service layer are fully unit
tested against a mocked directory client. discord.js handlers are kept thin.

## Deferred (v1 non-goals)

Email verification code, role-based authorization, Discord role sync, roster/read
commands, admin writes, `/unlink`, and any bot-side persistence.
