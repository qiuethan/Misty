# UTMIST Discord Bot

A thin Node.js application layer over the [team-tracking](../team-tracking) directory
API. v1 does one thing: link a Discord account to a pre-seeded directory `Person`,
behind a proper **auth layer** so future commands and role-based permissions slot
in cleanly.

It holds **no database and no business logic** — every action is an HTTP call to
the directory (the API-only source of truth).

## Multi-server model

The bot is meant to run across **many Discord servers** from a single deployment.
There is no per-server allowlist: anyone can add it to a server, and access is
gated purely by the auth layer — an unlinked user can't run gated commands, a
linked user can. Identity is a Discord user's **global** account (snowflake), so
a linked person is recognized in every server the bot shares with them.

### Release channels (beta vs stable)

Commands are split into two channels by an `export const beta` flag:

- **Stable** (`beta = false` or omitted) — registered **globally**, available in
  every server the bot is in (production).
- **Beta** (`beta = true`) — registered **only** to the dedicated testing guild
  (`DISCORD_GUILD_ID`), so a new command can be trialed in the test server without
  ever reaching production. Promote it by flipping `beta` to `false`.

`npm run register` sends stable commands globally and beta commands to the test
guild exclusively (re-running also clears stale/promoted beta commands from the
guild). If any command is beta and `DISCORD_GUILD_ID` is unset, registration warns
and skips them.

## Commands

- `/link email:<your UTMIST email>` (public) — links your Discord account to your
  directory record. Your email must already be in the directory (execs seed
  members). No email verification yet — see the `// TODO: verification` in
  `src/linkService.js`.
- `/whoami` (linked) — shows which directory record you're linked to. Requires you
  to be linked; the auth layer handles the "not linked" case.
- `/seed email:<> name:<> [level:member|admin|superuser]` (admin) — add a member to
  the directory. Gated to admins; you can only grant a level at or below your own
  (`superuser` > `admin` > `member`). The bot's directory key needs `people:write`.
- `/team create slug:<> label:<> [description:<>]` (admin) — create a team.
- `/team list [active_only:<bool>]` (linked) — list teams (default active only).
- `/team rename slug:<> new_label:<>` (admin) — rename a team.
- `/team add user:<@mention> team:<slug> [role:<...>] [team_admin:<bool>]` (admin) — add a member. The mentioned user must have already run `/link`.
- `/team remove user:<@mention> team:<slug>` (admin) — soft-end a membership as of today.
- `/team roster team:<slug> [as_of:<YYYY-MM-DD>]` (linked) — show a team's current roster.
- `/my-teams` (linked) — list your active memberships.

`/team` and `/my-teams` are currently on the **beta** channel (test guild only) — promote by setting `beta = false` in the command modules and re-running `npm run register`.

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
   - Discord app credentials (`DISCORD_TOKEN`, `DISCORD_CLIENT_ID`).
   - `DISCORD_GUILD_ID` — dedicated testing guild ID. **Beta** commands register
     exclusively here; stable commands are always global. Required only if you
     have beta commands (see "Release channels" above).
   - `DIRECTORY_BASE_URL` (e.g. `http://localhost:8000`).
   - `DIRECTORY_API_KEY` — issue one from team-tracking:
     ```bash
     cd ../team-tracking
     uv run team-tracking-keys issue --name discord-bot \
       --scopes people:read people:write identifiers:read identifiers:write \
                teams:read teams:write memberships:read memberships:write role_kinds:read
     ```
3. `npm install`
4. `npm run register` — registers the slash commands (run once, or whenever
   command definitions change). **Stable** commands go global (can take ~1h to
   propagate); **beta** commands go only to the testing guild. See "Release
   channels" above.
5. `npm start` — then invite the bot to any server via its OAuth2 URL.

## Web playground (local dev)

For iterating on commands without going through Discord, the bot exposes
the same command surface via HTTP. Run it with:

```bash
npm run dev:web
```

Then open `http://127.0.0.1:3001`. Every registered command renders as a
form; submit runs the same router pipeline the Discord surface uses.

The "Acting as" field at the top of the page lets you pretend to be any
Discord user — useful for testing permission gates like `/seed` (admins
only) without swapping accounts.

**Requires** a team-tracking API key with the `dev:spoof` scope. Issue one
against your local team-tracking:

```bash
cd ../team-tracking
uv run team-tracking-keys issue --name discord-bot-playground \
  --scopes people:read people:write identifiers:read identifiers:write dev:spoof
```

Put the returned key in `.env` as `DIRECTORY_API_KEY`. The bot's startup
guard refuses to run the web surface without this scope; team-tracking
refuses to issue it against `TT_ENV=production` — the safety property
holds on both sides.

This playground is deliberately plain (form-only, no chat transcript, no
mention rendering, no ephemeral DB isolation). Those land in Plan 2B.

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
| `src/registerCommands.js` | One-shot slash-command registration (stable → global; beta → testing guild only). |
| `src/defineCommand.js` | Neutral, surface-agnostic command factory. |
| `src/adapters/discord.js` | The ONLY module that imports from discord.js — turns interactions into intents. |
| `src/web/server.js` | Fastify web playground (see "Web playground" above). |
| `src/startupGuard.js` | Refuses web-mode boot if the directory key lacks `dev:spoof`. |

## Testing

```bash
npm test    # node --test — unit tests for config, client, service, auth, router, render
```

The auth layer (principal, policy, router) and the service layer are fully unit
tested against a mocked directory client. discord.js handlers are kept thin.

## Deferred (v1 non-goals)

Email verification code, role-based authorization, Discord role sync, `/unlink`,
and any bot-side persistence.

Team archive/unarchive, `/team info`, editing role/team-admin on existing memberships, team-admin delegation authority, dynamic role_kinds fetch for slash choices, LLM adapter.
