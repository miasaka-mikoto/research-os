# Research OS architecture

## Layers

1. **Domain records** (`researchos.models`) — typed, serialisable entity and relation records.
2. **Persistence** (`researchos.storage`) — SQLite connection, migrations, CRUD, revisions, FTS, graph traversal, backup and recovery.
3. **Workspace services** (`researchos.services`) — higher-level operations used by demo seeding and the UI.
4. **Desktop UI** (`researchos.app`) — Tkinter views; no business rules are embedded in widgets.
5. **Verification** (`tests`, `scripts/verify_demo.py`) — deterministic checks over a temporary workspace.

## Durability decisions

- Foreign keys and `PRAGMA integrity_check` are enabled for every connection.
- Mutations use transactions and write an entity revision snapshot.
- FTS is an index over entity title, content and JSON data; the canonical data remains in normal tables.
- Backups are SQLite online backups, not ad-hoc text dumps, so they can be restored without losing constraints or indexes.
- Migrations are numbered and recorded with `PRAGMA user_version`.
- Export formats are projections; they never replace the canonical database.

## Graph semantics

Edges are directed and typed. Reciprocal semantics are represented explicitly when useful (`SUPPORTS` and `REFUTES` are different relations). A graph query returns nodes plus edge records, and can be filtered by entity type, relation type or depth.
