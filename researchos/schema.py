"""SQLite schema and migration definitions for Research OS.

Migrations are deliberately small and numbered.  ``PRAGMA user_version`` is
used as the durable migration marker; applying migrations is idempotent and
safe on an existing database.
"""

from __future__ import annotations

from typing import Iterable


LATEST_SCHEMA_VERSION = 3


MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(source_id, relation_type, target_id),
                FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS entity_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                operation TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)",
            "CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type)",
            "CREATE INDEX IF NOT EXISTS idx_revisions_entity ON entity_revisions(entity_id, version)",
        ),
    ),
    (
        2,
        (
            """
            CREATE TABLE IF NOT EXISTS daily_logs (
                log_date TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_entities_type_title ON entities(entity_type, title)",
        ),
    ),
    (
        3,
        (
            """
            CREATE TABLE IF NOT EXISTS timeline_events (
                id TEXT PRIMARY KEY,
                entity_id TEXT,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_timeline_occurred ON timeline_events(occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_timeline_entity ON timeline_events(entity_id)",
        ),
    ),
)


def iter_migrations(current_version: int) -> Iterable[tuple[int, tuple[str, ...]]]:
    """Yield migrations newer than ``current_version`` in order."""

    for version, statements in MIGRATIONS:
        if version > current_version:
            yield version, statements
