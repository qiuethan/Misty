# Security & Code-Quality Review — 2026-07-13

Full-codebase review of the Misty platform (services: `team-tracking`, `documentation-system`,
`llm`, `verification`; `discord-bot`; shared `packages/auth`).

**Method.** Two independent reviews were run and then cross-verified:
- A multi-agent workflow review (finder angles + per-finding adversarial verify).
- An independent `codex` full-repo review.

Every finding was then re-checked by the engine that did **not** originate it (Codex verified the
workflow's findings; adversarial subagents verified Codex's findings). Verdicts below reflect that
cross-verification.

**Headline:** 2 Critical, 5 High, 5 Medium, 7 Low. The dominant systemic cause is **storage-adapter
drift** — the Postgres and in-memory adapters have diverged and the test suite only exercises
in-memory, so multiple real Postgres/prod bugs pass CI green.

---

## Findings (cross-verified)

| # | Finding | Sev | Status | Location |
|---|---------|-----|--------|----------|
| 1 | SSRF: docs web-fetcher fetches arbitrary user URLs (follows redirects, no egress filter), persists body to `content_snapshot`, readable back via `GET /docs`. Second trigger via `/refetch`. | **Critical** | CONFIRMED | `documentation-system/src/fetch/web.py:33-36`, `ingest.py:73-75`, `api/routers/docs.py` |
| 2 | Privilege escalation: `PATCH /people/{id}` applies `access_level` from payload with only `people:write` and no rank guard → any writer self-promotes to `superuser`. | **Critical** | CONFIRMED | `team-tracking/src/api/routers/people.py:61`, `contracts/types.py:101`, adapters `update_person` |
| 3 | `create_membership` doesn't translate FK `IntegrityError`→`ValueError`; router's 400 path is dead → 500. | High | CONFIRMED (both) | `team-tracking/src/storage/postgres.py:298`, `routers/memberships.py:27` |
| 4 | `update_membership` skips role validation → FK violation escapes as 500. | High | CONFIRMED (both) | `team-tracking/src/storage/postgres.py:352` |
| 5 | Doc dedup returns oldest-regardless-of-`active`; soft-removed + re-ingested URLs proliferate duplicate active rows. | High | CONFIRMED | `documentation-system/src/storage/postgres.py:138`, `in_memory.py:67`, `ingest.py:45` |
| 6 | No uniqueness on active memberships; bot pre-check is a bypassable TOCTOU. Duplicates double the roster; `/team remove` ends only one row. | High | CONFIRMED | `team-tracking/src/storage/schema.py:86-89`, `postgres.py:286`, `discord-bot/src/teamService.js:56,100,120` |
| 7 | `active_only` = `ended_at IS NULL` drops **future-dated** memberships immediately (correct predicate exists 3 lines away in the `as_of` branch). Strips doc visibility + `/my-teams` early. | High | CONFIRMED | `team-tracking/src/storage/postgres.py:326`, `in_memory.py:217`, `documentation-system/.../http_client.py:48`, `discord-bot/src/teamService.js:136` |
| 9 | `parent_id` FK violation misreported as `409 slug already exists`; in-memory accepts nonexistent parent. | Medium | CONFIRMED | `team-tracking/src/storage/postgres.py:215,230`, `in_memory.py:112`, `routers/teams.py:20` |
| 10 | LLM `/chat` authorizes on any valid key, ignores scopes (`require_scope` exists but unwired). | Medium | CONFIRMED | `llm/src/api/routers/chat.py:23`, `auth.py:22`, `mint_key.py:19` |
| 11 | Doc dedup has no DB unique constraint (only a non-unique index) → concurrent `POST /docs` double-insert. | Medium | CONFIRMED | `documentation-system/src/ingest.py:45`, `storage/schema.py:45`, `postgres.py:114` |
| 12 | `confirm-code` replay: consumed-but-unexpired subject returns `verified:true` + email **without re-checking the code**. Scoped to `verification:write` holders. | Medium | CONFIRMED | `verification/src/api/routers/verification.py:82` |
| 13 | No connection pooling: fresh `HttpDirectoryClient` + `httpx.Client` per call. | Low | CONFIRMED (both) | `documentation-system/src/directory/http_client.py:21`, `api/deps.py:31` |
| 14 | N+1 tag hydration in `list_docs`. | Low | CONFIRMED (both) | `documentation-system/src/storage/postgres.py:176` |
| 15 | N+1 team fetches per helper answer (`getTeam` per membership instead of one `listTeams`). | Low | CONFIRMED | `discord-bot/src/helperService.js:5` |
| 16 | `remove_tag` fetches the doc 3× (`add_tag` only 2× — overstated originally). | Low | PARTIAL | `documentation-system/src/api/routers/docs.py:126-131` |
| 17 | API-key storage block duplicated ×4 across services + in-memory adapters. | Low | CONFIRMED (shared-base location is a design call — `ApiKeyStore` only covers 3 of 6 methods). | `documentation-system/.../postgres.py:272`, `team-tracking/.../postgres.py:527` |
| 18 | Bot HTTP client wrappers (`parseJson`/`send`) duplicated ×3. | Low | CONFIRMED | `discord-bot/src/{directoryClient,docClient,verificationClient}.js` |
| 19 | In-memory `increment_attempts` non-atomic vs Postgres atomic increment (test/prod divergence; largely theoretical). | Low | CONFIRMED | `verification/src/storage/in_memory.py:24` vs `postgres.py:66` |
| 8 | `get_person_by_email` doesn't strip whitespace on lookup. **Downgraded**: column is `CITEXT`, so case IS handled — only leading/trailing whitespace differs from in-memory. | Low (was Medium) | DOWNGRADED | `team-tracking/src/storage/postgres.py:181`, `schema.py:24` |

---

## Remediation — fix branches

All branches cut from `staging`, single-zone where possible (respects `pr-zone-check`), TDD, PR **not**
merge. CI runs per-service `pytest` (Postgres-backed for team-tracking/verification via `alembic upgrade
head`), Ruff lint+format, and `npm test` for the bot — every PR must pass these.

### Wave 1 — Security (ship first)
- **`fix/docs-ssrf-egress-guard`** (#1) — validate URL host/IP against private/loopback/link-local/metadata
  ranges + scheme allowlist, re-validate every redirect hop (or disable redirects); consider dropping
  `content_snapshot` from the default read model. Zone: documentation-system.
- **`fix/people-access-level-escalation`** (#2) — gate `access_level` changes behind a rank/escalation
  check (mirror `seedService.js`) enforced in the service/storage layer. Zone: team-tracking.
- **`fix/llm-chat-scope-enforcement`** (#10) — `require_scope("chat")` on `/chat`. Zone: llm.
- **`fix/verification-confirm-code-replay`** (#12) — compare submitted code on the consumed branch; don't
  echo email on mismatch. Zone: verification.

### Wave 2 — Data integrity & adapter parity
- **`fix/membership-integrity`** (#3, #4, #6, #7) — FK→ValueError mapping; partial-unique index on
  `(person_id, team_id) WHERE ended_at IS NULL` (new migration, mirror `person_identifiers`); roster dedup +
  end-all-active on remove; `active_only` = `ended_at IS NULL OR ended_at > CURRENT_DATE`. Zone: team-tracking.
- **`fix/docs-url-dedup`** (#5, #11) — prefer active row in `get_doc_by_normalized_url`; partial-unique
  index on `url_normalized WHERE active` (new migration); race-safe ingest (SAVEPOINT/on-conflict, mirror
  `add_grant`). Zone: documentation-system.
- **`fix/team-parent-id-validation`** (#9) — branch on `constraint_name` to split parent-FK (400) from slug
  conflict (409); validate `parent_id` in-memory. Zone: team-tracking.

### Wave 3 — Cleanup & performance
- **`perf/docs-pooling-and-queries`** (#13, #14, #16) — shared `httpx.Client`; batch tag hydration; drop
  `remove_tag`'s redundant fetch. Zone: documentation-system.
- **`perf/bot-helper-n-plus-one`** (#15) — `resolveTeamLabels` uses one `listTeams`. Zone: discord-bot.
- **`refactor/bot-http-clients`** (#18) — extract shared `parseJson`/`send` helper. Zone: discord-bot.

### Deferred (tracked, not in this batch)
- **#17** API-key store dedup — inherently cross-zone; shared-base location (`packages/auth`?) is a design
  decision. Revisit after Wave 2.
- **#8** email-lookup whitespace, **#19** attempts atomicity — trivial parity nits; fold in opportunistically.

### Cross-cutting recommendation
Add a **Postgres-backed run of the storage contract tests** so adapter drift (#3, #4, #7, #8, #9, #11)
surfaces in CI instead of hiding behind the in-memory suite.
