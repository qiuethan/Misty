# UTMIST Directory — Design Spec

**Date:** 2026-06-30
**Status:** Design approved; implementation plan pending

## Context

UTMIST (University of Toronto Machine Intelligence Student Team) is building an internal ops platform. This spec covers the **directory** — the foundational data layer that models people, teams, roles, and memberships. Downstream systems (documentation catalog, Discord bot sync, sponsor CRM, event tools) reference this directory as the single source of truth for org identity.

The directory is deliberately built *first* because designing anything downstream (e.g., "who owns this doc") requires an org model. Building the org model inside another system would either mis-shape it for that system's needs or force a rebuild later.

## Goals

The directory is the source of truth for:

1. **Who's on what team, as what kind of role, right now** — queryable roster.
2. **Historical membership** — turnover continuity across rotating leadership.
3. **A stable schema other systems reference** — canonical IDs for people and teams that downstream systems (docs catalog, bots, sync jobs) can rely on.
4. **Sync-ready identifiers** — external IDs (Discord, GitHub, UofT email) are modeled as a future extension so sync jobs can be built without redesigning the base.
5. **Auto-perms derivation** — downstream systems derive access from role/team membership and the team-admin flag, so there is no separate ACL to maintain.

## Non-goals (v1)

- **No Discord / Google / GitHub / Notion sync jobs.** Sync is deferred to the connectors layer; base schema is designed to be sync-ready but no sync runs in v1.
- **No permission-enforcement engine.** The base provides queryable primitives (memberships, admin flag) from which downstream systems *derive* perms. No policy layer is built here.
- **No auth / login for the directory itself.** Officer access is via whatever admin surface is chosen later (NocoDB, Directus, direct SQL). Consumer access is via API keys.
- **No org-wide admin concept.** Deferred to the perms/connectors layer.
- **No content storage.** The directory holds identity and structure only. Documents, events, sponsor materials, etc. live in downstream systems that reference this one.

## Architecture — layered design

```
┌──────────────────────────────────────────────────────────┐
│ Base tables    people, teams, role_kinds,                │
│                team_memberships                          │
├──────────────────────────────────────────────────────────┤
│ Extensions     Reserved. Per-entity sidecar tables or    │
│                JSON fields for anything the base doesn't │
│                capture. Added as concrete needs land.    │
│                Examples: person_identifiers (Discord ID, │
│                UofT email, GitHub handle), team_metadata │
│                (charter URL, founded date).              │
├──────────────────────────────────────────────────────────┤
│ Connectors     Reserved. Integration surface for Discord │
│                bot, Google Workspace, GitHub org,        │
│                Notion. Designed later; hangs off the     │
│                Directory API, not the base tables.       │
└──────────────────────────────────────────────────────────┘
```

Three-layer split at the system level:

```
┌────────────────────────────┐   ┌────────────────────────────┐
│   Officer edit surface     │   │   Consumer clients         │
│   (NocoDB / Directus /     │   │   (Docs catalog, Discord   │
│   custom UI / raw SQL)     │   │   bot, future sync jobs)   │
└──────────────┬─────────────┘   └──────────────┬─────────────┘
               │                                 │
               ▼                                 ▼
      ┌───────────────────────────────────────────────┐
      │  Directory API (stable contract)               │
      │  - People CRUD                                 │
      │  - Team registry (with hierarchy)              │
      │  - Role-kind registry                          │
      │  - Membership assignments (with admin flag)    │
      │  - Queries: current members, as-of-date, ...   │
      └────────────────────┬──────────────────────────┘
                           │
                           ▼
      ┌───────────────────────────────────────────────┐
      │  Storage adapter (swappable) — Postgres v1    │
      └───────────────────────────────────────────────┘
```

- Schema is defined at the API layer, portable SQL DDL.
- Consumers only speak the Directory API — they don't know or care about the backend.
- Storage backend and officer admin UI are decided in the implementation plan; nothing here locks them in.

## Base schema

Four tables. Every table shares audit conventions:

- `created_at`, `updated_at` — timestamps, auto-populated
- `created_by`, `updated_by` — string identifiers of the actor (officer email, API key name, or system process). Free-form for v1; can be tightened into an `actors` table later.
- `active` — boolean, default `true`; soft-retirement without deleting history. Manual flip only.

### `people`

The human record. Long-lived across turnover.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | Canonical, never changes |
| `display_name` | text | NOT NULL | What the person wants to be called (one free-form field; handles all name conventions) |
| `primary_email` | citext | NOT NULL, UNIQUE | Case-insensitive identity key. Normalize to lowercase on write. |
| `active` | boolean | NOT NULL, default true | Manual soft-retirement |
| `created_at` | timestamptz | NOT NULL, auto | |
| `updated_at` | timestamptz | NOT NULL, auto | |
| `created_by` | text | NOT NULL | |
| `updated_by` | text | NOT NULL | |

**Minimum manual intake:** `display_name` + `primary_email`.

**Explicitly not here** (with reasoning):

- No role/team/title fields — those live in `team_memberships` and change over time.
- No Discord / UofT email / GitHub handle / any external IDs — deferred to extension layer (future `person_identifiers` table).
- No `pronouns`, `notes`, `avatar_url`, academic fields — barebones principle; richer profile lives above the base.

### `teams`

The operating org. Hierarchical via self-reference.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | Canonical, never changes |
| `slug` | text | NOT NULL, UNIQUE | Human-readable, mutable. Format `[a-z0-9_.]+` (e.g. `partnerships`, `events.agi_workshop_2025`). Enforced at app layer. |
| `label` | text | NOT NULL | Human-readable name |
| `description` | text | nullable | One-line "what does this team do." Useful during turnover. |
| `parent_id` | UUID | FK → teams.id, nullable | `null` = top-level department. |
| `active` | boolean | NOT NULL, default true | |
| `created_at`, `updated_at`, `created_by`, `updated_by` | (audit) | | |

**Minimum manual intake:** `slug` + `label`.

**Explicitly not here:**

- No `lead_id` / `owner_person_id` — derived from `team_memberships`.
- No connector fields (`discord_role_id`, `google_group_email`) — connectors layer.
- No `founded_at`, `retired_at` — `active` is enough for v1.

### `role_kinds`

Controlled vocabulary for the seniority axis of team roles. Small registry — treated as a table (not an enum) for extensibility.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | text | PK (slug) | Downstream code reads `role_kind_id = 'lead'` directly. Renaming is rare and handled via data migration. |
| `label` | text | NOT NULL | Human-readable |
| `description` | text | nullable | |
| `active` | boolean | NOT NULL, default true | |
| `created_at`, `updated_at`, `created_by`, `updated_by` | (audit) | | |

**Seed rows (initial data):**

| id | label |
|---|---|
| `executive` | Executive |
| `director` | Director |
| `lead` | Lead |
| `member` | Member |

**Implicit hierarchy** (documented, not enforced): `executive > director > lead > member`. Downstream perm rules encode this explicitly (e.g. `role_kind_id IN ('executive', 'director')` for "director-or-above").

**No `rank` column** — perm rules use explicit slug checks. Ordering for display is a UI concern.

**Note:** `admin` is intentionally NOT a `role_kind`. Admin authority is orthogonal to seniority — see `team_memberships.is_team_admin` below.

### `team_memberships`

The intersection table — encodes "person X holds role_kind Y on team Z from date A to date B." Also carries the team-admin flag.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `person_id` | UUID | FK → people.id, NOT NULL | |
| `team_id` | UUID | FK → teams.id, NOT NULL | |
| `role_kind_id` | text | FK → role_kinds.id, NOT NULL, default `'member'` | |
| `is_team_admin` | boolean | NOT NULL, default false | Orthogonal to `role_kind_id`. See below. |
| `started_at` | date | NOT NULL, default today | Calendar-scoped, not instant-scoped |
| `ended_at` | date | nullable | `null` = currently active |
| `created_at`, `updated_at`, `created_by`, `updated_by` | (audit) | | |

**No unique constraint on `(person_id, team_id)`** for active rows. Overlapping rows are allowed — useful during role transitions ("Alex was a `member` until Dec 1, then `lead` from Dec 1 onward" is naturally two rows).

**Minimum manual intake:** `person_id` + `team_id`. Two dropdown picks.

**Recommended indexes:**

- `(team_id, ended_at)` — for current-roster queries
- `(person_id, ended_at)` — for "Alex's active memberships"
- `(started_at, ended_at)` — for as-of-date reporting

**`is_team_admin = true` semantics:**

- Can edit the team row (slug, label, description, parent).
- Can add, remove, and edit `team_memberships` scoped to that team.
- Downstream systems (docs catalog, etc.) may derive further team-scoped authority from this flag.
- No cascade: ending a membership doesn't auto-revoke admin elsewhere; nothing propagates outside the row.

## Convention: named exec seats (President, VP X, Treasurer)

Named org-chart seats are modeled through the base tables, not a separate `positions` concept. Two patterns:

1. **Team-scoped exec seats** (e.g., "VP Partnerships") → a `team_memberships` row on the `partnerships` team with `role_kind_id = 'executive'`. Whether that person also has `is_team_admin = true` is a separate call.
2. **Org-wide exec seats** (e.g., "President", "Treasurer") → create a top-level team (convention: `leadership` or similar) and put those people there with an appropriate role_kind. The team is data, not schema.

Titles like "VP Partnerships" are the composite `(executive on partnerships)` — the schema doesn't store the string "VP Partnerships." If a display label is needed, it's rendered from the composite.

## Common queries this schema supports

- **Current roster of a team:**
  ```sql
  SELECT p.* FROM people p
  JOIN team_memberships tm ON tm.person_id = p.id
  WHERE tm.team_id = :team_id AND tm.ended_at IS NULL;
  ```
- **Everyone Alex is on right now:**
  ```sql
  SELECT t.* FROM teams t
  JOIN team_memberships tm ON tm.team_id = t.id
  WHERE tm.person_id = :alex_id AND tm.ended_at IS NULL;
  ```
- **Roster as of a past date** (turnover / handoff):
  ```sql
  SELECT p.* FROM people p
  JOIN team_memberships tm ON tm.person_id = p.id
  WHERE tm.team_id = :team_id
    AND tm.started_at <= :as_of_date
    AND (tm.ended_at IS NULL OR tm.ended_at > :as_of_date);
  ```
- **Current team admins of a team:**
  ```sql
  SELECT p.* FROM people p
  JOIN team_memberships tm ON tm.person_id = p.id
  WHERE tm.team_id = :team_id
    AND tm.is_team_admin = true
    AND tm.ended_at IS NULL;
  ```
- **Derived perm check** ("can Alex admin `partnerships`?"):
  ```sql
  SELECT EXISTS (
    SELECT 1 FROM team_memberships
    WHERE person_id = :alex_id
      AND team_id = :partnerships_id
      AND is_team_admin = true
      AND ended_at IS NULL
  );
  ```

## Extension layer (reserved, not built)

The base is intentionally minimal. Richer per-entity data is added later as separate tables (or JSON fields) that reference the base. Expected first extensions:

- **`person_identifiers`** — `(person_id, kind, value)` rows for `discord_id`, `uoft_email`, `github_handle`, and any other external identifiers. Added when sync work begins. Rationale for a separate table over columns: adding a new identifier type becomes a data change, not a schema change.
- **`team_metadata`** — optional per-team fields (charter URL, founded date, budget bucket, description overrides) that don't earn a base column.
- **Per-membership overrides** — custom title, notes, or scope on a specific membership.

Extensions are designed so that base tables remain untouched. Adding an extension never requires modifying `people`, `teams`, `role_kinds`, or `team_memberships`.

## Connectors layer (reserved, not built)

Integration surface between the directory and external systems. Designed later; hangs off the Directory API, not the base tables. Expected connectors:

- **Discord** — role sync, channel access derived from team membership
- **Google Workspace** — group membership, email aliases
- **GitHub** — org membership, team access
- **Notion** — workspace access

Sync direction, reconciliation, and drift handling are all deferred to that layer's design.

## Deferred decisions

The following are intentionally not decided in this spec. Each is compatible with the schema as designed.

- **Storage backend.** Design assumes a Postgres-family database. Concrete choice (self-hosted vs managed, which provider) is deferred to the implementation plan. Schema is portable SQL DDL.
- **Officer admin surface.** Options include NocoDB, Directus, Supabase Studio, or a custom admin app. All are compatible with the schema. Chosen in the implementation plan.
- **API shape.** REST vs GraphQL vs auto-generated (PostgREST). Chosen in the implementation plan.
- **Auth model.** For officers editing and for API consumers (bot keys). Chosen in the implementation plan.
- **Team seed data.** Which departments UTMIST starts with is data, created by officers post-deploy, not fixed by this spec.
- **Full extension and connectors designs.** Separate specs when those layers are built.

## What comes next

- **Implementation plan** — turns this spec into concrete steps (storage backend selection, schema DDL, migrations, admin surface, API scaffolding, seed data).
- **Documentation catalog (next sub-project)** — references this directory for ownership and derived perms.
- **Connectors (later)** — starts with Discord sync as the highest-value integration.
