# team-tracking

UTMIST's team-tracking system. The directory layer: people, teams, roles, memberships. Foundational — downstream systems (docs catalog, Discord bot, sponsor CRM, event tools) reference this as the source of truth for org identity.

See `DESIGN.md` for the schema and layered architecture.

## Design principle: interface-first

The database, admin UI, API framework, and hosting are all deferred decisions. This code is structured so those choices can change without rewriting consumers.

Every boundary that could change is expressed as an **interface** (contract) with concrete implementations behind it:

```
consumers
    │
    ▼
DirectoryAPI     ← stable contract; consumers only depend on this
    │
    ▼
StorageAdapter   ← stable contract; DirectoryAPI only depends on this
    │
    ▼
Postgres | SQLite | ... ← swappable concrete implementations
```

**Rules of thumb:**

- Consumers never import from `src/storage/*` directly. They only see the interfaces in `contracts/`.
- Swapping Postgres for another store means adding a new class in `src/storage/` that implements `StorageAdapter`. No other file should change.
- Same pattern for auth, event publishing, admin surface — any boundary that touches an external system.

## Folder layout

```
team-tracking/
├── README.md          — this file
├── DESIGN.md          — schema + architecture spec
├── contracts/         — stable interface definitions (the things nothing else can break)
├── src/               — concrete implementations (freely swappable)
│   └── storage/       — storage adapters (Postgres first; others later)
└── migrations/        — SQL DDL for the initial Postgres schema
```

## Status

Design phase complete. Implementation stack not yet chosen — the concrete language / framework for `contracts/` and `src/` is the next decision.
