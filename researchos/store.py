"""Reliable SQLite persistence for Research OS.

The UI is intentionally not coupled to a particular database framework.  This
module provides the small, boring, explicit persistence API used by the
application: typed entities, directed relations, full-text search, revisions,
timeline events, daily logs, integrity checks, and recoverable backups.

All timestamps are UTC ISO-8601 strings.  Entity-specific fields live in the
``data`` JSON object so the schema can evolve without losing old work.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import ENTITY_TYPES, Entity, Relation, SearchHit
from .schema import LATEST_SCHEMA_VERSION, iter_migrations


class StoreError(RuntimeError):
    """Base error raised by the Research OS store."""


class NotFoundError(StoreError):
    """Raised when a requested entity or relation does not exist."""


class IntegrityError(StoreError):
    """Raised when an integrity assertion fails."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)


def _parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _normalise_relation_type(value: str) -> str:
    text = "_".join(str(value or "").strip().upper().replace("-", "_").split())
    if not text:
        raise ValueError("relation_type cannot be empty")
    return text


class ResearchStore:
    """SQLite-backed repository for all structured research records.

    Parameters
    ----------
    path:
        SQLite filename.  ``":memory:"`` is supported for tests and previews.
    backup_dir:
        Optional directory receiving periodic and explicit backups.
    autosave:
        When true, every mutation is committed immediately.  If ``backup_dir``
        is supplied, a checkpoint backup is created at most every
        ``autosave_interval`` seconds (default five minutes).
    """

    def __init__(
        self,
        path: str | os.PathLike[str] = "research_os.sqlite3",
        *,
        backup_dir: str | os.PathLike[str] | None = None,
        autosave: bool = True,
        autosave_interval: float = 300.0,
        timeout: float = 30.0,
    ) -> None:
        self.path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir = Path(backup_dir) if backup_dir else None
        if self.backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.autosave = autosave
        self.autosave_interval = max(0.0, float(autosave_interval))
        self._last_backup_monotonic = 0.0
        self._lock = threading.RLock()
        db_target = ":memory:" if str(path) == ":memory:" else str(self.path)
        self.conn = sqlite3.connect(db_target, timeout=timeout, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # WAL is ideal for a desktop app, but is not available for :memory:.
        if db_target != ":memory:":
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:
                pass
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()
        self._fts_available = self._ensure_fts()

    # ------------------------------------------------------------------
    # Lifecycle and schema
    # ------------------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock, self.conn:
            current = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
            if current > LATEST_SCHEMA_VERSION:
                raise StoreError(
                    f"database schema version {current} is newer than this Research OS build "
                    f"({LATEST_SCHEMA_VERSION}); upgrade the application before opening it"
                )
            for version, statements in iter_migrations(current):
                for statement in statements:
                    self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {int(version)}")
            self.conn.execute(
                "INSERT OR IGNORE INTO metadata(key, value, updated_at) VALUES (?, ?, ?)",
                ("app", "Research OS", utc_now()),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", str(LATEST_SCHEMA_VERSION), utc_now()),
            )

    def _ensure_fts(self) -> bool:
        """Create the FTS5 index if this SQLite build supports it.

        FTS is maintained explicitly on writes rather than with triggers.  This
        keeps migrations portable across the SQLite versions shipped with
        supported Windows Python distributions.
        """
        try:
            with self._lock, self.conn:
                self.conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5(
                        entity_id UNINDEXED,
                        entity_type,
                        title,
                        content,
                        data
                    )
                    """
                )
                self.conn.execute("DELETE FROM entity_fts")
                rows = self.conn.execute(
                    "SELECT id, entity_type, title, content, data_json FROM entities WHERE deleted = 0"
                ).fetchall()
                self.conn.executemany(
                    "INSERT INTO entity_fts(entity_id, entity_type, title, content, data) VALUES (?, ?, ?, ?, ?)",
                    [(r[0], r[1], r[2], r[3], r[4]) for r in rows],
                )
            return True
        except sqlite3.DatabaseError:
            return False

    def close(self) -> None:
        with self._lock:
            if self.conn:
                # ``close`` is intentionally idempotent: GUI shutdown hooks,
                # context managers and test tear-downs can all legitimately
                # call it more than once.
                try:
                    self.conn.commit()
                    self.conn.close()
                except sqlite3.ProgrammingError:
                    # sqlite raises this when commit/close is repeated on an
                    # already-closed connection; there is nothing left to do.
                    pass

    def __enter__(self) -> "ResearchStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def save(self) -> None:
        """Commit pending work and optionally make a checkpoint backup."""
        with self._lock:
            self.conn.commit()
            self._maybe_autosave(force=True)

    def _maybe_autosave(self, *, force: bool = False) -> None:
        if not self.autosave or not self.backup_dir:
            return
        import time

        now = time.monotonic()
        if force or now - self._last_backup_monotonic >= self.autosave_interval:
            self.backup()
            self._last_backup_monotonic = now

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_entity(value: Entity | Mapping[str, Any]) -> Entity:
        if isinstance(value, Entity):
            return value
        return Entity.from_dict(value)

    def create_entity(
        self,
        entity: Entity | Mapping[str, Any] | None = None,
        *,
        entity_type: str | None = None,
        title: str = "",
        content: str = "",
        data: Mapping[str, Any] | None = None,
        entity_id: str | None = None,
    ) -> Entity:
        """Insert and return an entity, recording its initial revision."""
        if entity is not None:
            item = self._coerce_entity(entity)
            if any(v is not None for v in (entity_type, data, entity_id)) or title or content:
                # Explicit keyword values are useful when callers start from a
                # partially populated Entity; they override only supplied data.
                if entity_type is not None:
                    item.entity_type = entity_type
                if data is not None:
                    item.data = dict(data)
                if entity_id is not None:
                    item.id = entity_id
                if title:
                    item.title = title
                if content:
                    item.content = content
        else:
            item = Entity(entity_type=entity_type or "Concept", title=title, content=content, data=dict(data or {}), id=entity_id)
        item.entity_type = str(item.entity_type or "Concept").strip()
        item.title = str(item.title or "")
        item.content = str(item.content or "")
        if not item.entity_type:
            raise ValueError("entity_type cannot be empty")
        item.id = item.id or _new_id("ent")
        now = utc_now()
        item.created_at = item.created_at or now
        item.updated_at = now
        item.version = max(1, int(item.version or 1))
        with self._lock, self.conn:
            try:
                self.conn.execute(
                    """
                    INSERT INTO entities(id, entity_type, title, content, data_json, created_at, updated_at, version, deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (item.id, item.entity_type, item.title, item.content, _json(item.data), item.created_at, item.updated_at, item.version),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"entity id already exists: {item.id}") from exc
            self._record_revision(item, "CREATE")
            self._record_event("ENTITY_CREATED", item.title, entity_id=item.id, occurred_at=now)
            self._fts_upsert(item)
        self._maybe_autosave()
        return item

    def get_entity(self, entity_id: str, *, include_deleted: bool = False) -> Entity | None:
        sql = "SELECT * FROM entities WHERE id = ?"
        params: list[Any] = [entity_id]
        if not include_deleted:
            sql += " AND deleted = 0"
        with self._lock:
            row = self.conn.execute(sql, params).fetchone()
        return self._row_to_entity(row) if row else None

    def require_entity(self, entity_id: str, *, include_deleted: bool = False) -> Entity:
        result = self.get_entity(entity_id, include_deleted=include_deleted)
        if result is None:
            raise NotFoundError(f"entity not found: {entity_id}")
        return result

    @staticmethod
    def _row_to_entity(row: sqlite3.Row | Mapping[str, Any]) -> Entity:
        return Entity(
            id=row["id"],
            entity_type=row["entity_type"],
            title=row["title"],
            content=row["content"],
            data=_parse_json(row["data_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=int(row["version"] or 1),
        )

    def list_entities(
        self,
        entity_type: str | Sequence[str] | None = None,
        *,
        include_deleted: bool = False,
        limit: int | None = None,
        offset: int = 0,
        order_by: str = "updated_at",
        descending: bool = True,
    ) -> list[Entity]:
        allowed_order = {"updated_at", "created_at", "title", "entity_type", "version"}
        if order_by not in allowed_order:
            raise ValueError(f"unsupported order_by: {order_by}")
        sql = "SELECT * FROM entities WHERE 1=1"
        params: list[Any] = []
        if not include_deleted:
            sql += " AND deleted = 0"
        if entity_type:
            values = [entity_type] if isinstance(entity_type, str) else list(entity_type)
            sql += " AND entity_type IN (" + ",".join("?" for _ in values) + ")"
            params.extend(values)
        sql += f" ORDER BY {order_by} {'DESC' if descending else 'ASC'}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([max(0, int(limit)), max(0, int(offset))])
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def update_entity(
        self,
        entity_id: str | Entity | Mapping[str, Any],
        entity: Entity | Mapping[str, Any] | None = None,
        **changes: Any,
    ) -> Entity:
        """Update selected fields and append a revision snapshot.

        ``data`` is merged by default, making it safe for individual notebook
        panels to update one field without clobbering another panel's fields.
        Pass ``replace_data=True`` in ``changes`` to replace the JSON object.
        """
        # Accept the concise ``update_entity(Entity(...))`` form used by the
        # original UI prototype in addition to the explicit ID form.
        if not isinstance(entity_id, str):
            if entity is not None:
                raise TypeError("entity cannot be supplied twice")
            entity = self._coerce_entity(entity_id)
            if not entity.id:
                raise ValueError("entity.id is required for update")
            entity_id = entity.id
        current = self.require_entity(entity_id, include_deleted=True)
        replace_data = bool(changes.pop("replace_data", False))
        if entity is not None:
            incoming = self._coerce_entity(entity)
            changes.setdefault("entity_type", incoming.entity_type)
            changes.setdefault("title", incoming.title)
            changes.setdefault("content", incoming.content)
            changes.setdefault("data", incoming.data)
        if "entity_type" in changes:
            current.entity_type = str(changes["entity_type"] or current.entity_type).strip()
        if "title" in changes:
            current.title = str(changes["title"] or "")
        if "content" in changes:
            current.content = str(changes["content"] or "")
        if "data" in changes:
            incoming_data = dict(changes["data"] or {})
            current.data = incoming_data if replace_data else {**current.data, **incoming_data}
        if not current.entity_type:
            raise ValueError("entity_type cannot be empty")
        current.version = int(current.version or 1) + 1
        current.updated_at = utc_now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE entities SET entity_type = ?, title = ?, content = ?, data_json = ?, updated_at = ?, version = ?
                WHERE id = ?
                """,
                (current.entity_type, current.title, current.content, _json(current.data), current.updated_at, current.version, entity_id),
            )
            self._record_revision(current, "UPDATE")
            self._record_event("ENTITY_UPDATED", current.title, entity_id=entity_id, occurred_at=current.updated_at)
            self._fts_upsert(current)
        self._maybe_autosave()
        return current

    def upsert_entity(self, entity: Entity | Mapping[str, Any]) -> Entity:
        item = self._coerce_entity(entity)
        if item.id and self.get_entity(item.id, include_deleted=True):
            return self.update_entity(item.id, item, replace_data=True)
        return self.create_entity(item)

    def seed(
        self,
        entities: Iterable[Entity | Mapping[str, Any]] = (),
        relations: Iterable[Relation | Mapping[str, Any]] = (),
    ) -> dict[str, int]:
        """Insert a portable fixture and return insertion counts.

        This intentionally accepts ordinary dictionaries so demo workspaces
        can be authored as JSON without importing Python dataclasses.
        Existing IDs are updated, making repeated seed calls idempotent.
        """
        entity_count = 0
        relation_count = 0
        for entity in entities:
            self.upsert_entity(entity)
            entity_count += 1
        for relation in relations:
            self.create_relation(relation)
            relation_count += 1
        return {"entities": entity_count, "relations": relation_count}

    def delete_entity(self, entity_id: str, *, hard: bool = False) -> bool:
        current = self.require_entity(entity_id, include_deleted=True)
        with self._lock, self.conn:
            if hard:
                self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
                self._fts_delete(entity_id)
            else:
                now = utc_now()
                self.conn.execute("UPDATE entities SET deleted = 1, updated_at = ?, version = version + 1 WHERE id = ?", (now, entity_id))
                current.updated_at = now
                current.version += 1
                self._record_revision(current, "DELETE")
                self._record_event("ENTITY_DELETED", current.title, entity_id=entity_id, occurred_at=now)
                self._fts_delete(entity_id)
        self._maybe_autosave()
        return True

    def restore_entity(self, entity_id: str) -> Entity:
        current = self.require_entity(entity_id, include_deleted=True)
        with self._lock, self.conn:
            now = utc_now()
            current.updated_at = now
            current.version += 1
            self.conn.execute("UPDATE entities SET deleted = 0, updated_at = ?, version = ? WHERE id = ?", (now, current.version, entity_id))
            self._record_revision(current, "RESTORE")
            self._record_event("ENTITY_RESTORED", current.title, entity_id=entity_id, occurred_at=now)
            self._fts_upsert(current)
        self._maybe_autosave()
        return current

    def _record_revision(self, entity: Entity, operation: str) -> None:
        self.conn.execute(
            "INSERT INTO entity_revisions(entity_id, version, operation, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity.id, entity.version, operation, _json(entity.to_dict()), utc_now()),
        )

    # ------------------------------------------------------------------
    # Relations and graph operations
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_relation(value: Relation | Mapping[str, Any]) -> Relation:
        if isinstance(value, Relation):
            return value
        return Relation.from_dict(value)

    def create_relation(
        self,
        relation: Relation | Mapping[str, Any] | None = None,
        *,
        source_id: str | None = None,
        relation_type: str | None = None,
        target_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Relation:
        if relation is not None:
            item = self._coerce_relation(relation)
            if source_id is not None:
                item.source_id = source_id
            if relation_type is not None:
                item.relation_type = relation_type
            if target_id is not None:
                item.target_id = target_id
            if metadata is not None:
                item.metadata = dict(metadata)
        else:
            item = Relation(source_id=source_id or "", relation_type=relation_type or "", target_id=target_id or "", metadata=dict(metadata or {}))
        item.source_id = str(item.source_id or "")
        item.target_id = str(item.target_id or "")
        item.relation_type = _normalise_relation_type(item.relation_type)
        if not item.source_id or not item.target_id:
            raise ValueError("source_id and target_id are required")
        # Require active or soft-deleted entities: linking unknown IDs is almost
        # always a data-entry bug, while deleted entities remain recoverable.
        if self.get_entity(item.source_id, include_deleted=True) is None:
            raise NotFoundError(f"source entity not found: {item.source_id}")
        if self.get_entity(item.target_id, include_deleted=True) is None:
            raise NotFoundError(f"target entity not found: {item.target_id}")
        item.id = item.id or _new_id("rel")
        item.created_at = item.created_at or utc_now()
        with self._lock, self.conn:
            existing = self.conn.execute(
                "SELECT * FROM relations WHERE source_id = ? AND relation_type = ? AND target_id = ?",
                (item.source_id, item.relation_type, item.target_id),
            ).fetchone()
            if existing:
                item.id = existing["id"]
                item.created_at = existing["created_at"]
                if item.metadata:
                    self.conn.execute("UPDATE relations SET metadata_json = ? WHERE id = ?", (_json(item.metadata), item.id))
                    item.metadata = dict(_parse_json(_json(item.metadata), {}))
                else:
                    item.metadata = dict(_parse_json(existing["metadata_json"], {}))
            else:
                try:
                    self.conn.execute(
                        "INSERT INTO relations(id, source_id, relation_type, target_id, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (item.id, item.source_id, item.relation_type, item.target_id, _json(item.metadata), item.created_at),
                    )
                except sqlite3.IntegrityError as exc:
                    raise StoreError("could not create relation") from exc
            self._record_event("RELATION_CREATED", item.relation_type, entity_id=item.source_id)
        self._maybe_autosave()
        return item

    @staticmethod
    def _row_to_relation(row: sqlite3.Row | Mapping[str, Any]) -> Relation:
        return Relation(
            id=row["id"],
            source_id=row["source_id"],
            relation_type=row["relation_type"],
            target_id=row["target_id"],
            metadata=_parse_json(row["metadata_json"], {}),
            created_at=row["created_at"],
        )

    def get_relation(self, relation_id: str) -> Relation | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM relations WHERE id = ?", (relation_id,)).fetchone()
        return self._row_to_relation(row) if row else None

    def list_relations(
        self,
        entity_id: str | None = None,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        relation_type: str | None = None,
        include_deleted_entities: bool = False,
    ) -> list[Relation]:
        sql = "SELECT r.* FROM relations r JOIN entities s ON s.id = r.source_id JOIN entities t ON t.id = r.target_id WHERE 1=1"
        params: list[Any] = []
        if not include_deleted_entities:
            sql += " AND s.deleted = 0 AND t.deleted = 0"
        if entity_id and not source_id and not target_id:
            sql += " AND (r.source_id = ? OR r.target_id = ?)"
            params.extend([entity_id, entity_id])
        if source_id:
            sql += " AND r.source_id = ?"
            params.append(source_id)
        if target_id:
            sql += " AND r.target_id = ?"
            params.append(target_id)
        if relation_type:
            sql += " AND r.relation_type = ?"
            params.append(_normalise_relation_type(relation_type))
        sql += " ORDER BY r.created_at ASC, r.id ASC"
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_relation(row) for row in rows]

    def delete_relation(self, relation_id: str) -> bool:
        with self._lock, self.conn:
            row = self.conn.execute("SELECT * FROM relations WHERE id = ?", (relation_id,)).fetchone()
            if not row:
                return False
            self.conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
            self._record_event("RELATION_DELETED", row["relation_type"], entity_id=row["source_id"])
        self._maybe_autosave()
        return True

    def neighbors(
        self,
        entity_id: str,
        *,
        direction: str = "both",
        relation_type: str | None = None,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Return graph neighbors in a stable, UI-friendly shape."""
        self.require_entity(entity_id)
        direction = direction.lower()
        if direction not in {"both", "out", "in"}:
            raise ValueError("direction must be one of both, out, in")
        # A zero-depth expansion is useful to callers that share a depth
        # control with ``graph``: it should return no neighbors, not silently
        # widen to one hop.  Negative values are treated the same way.
        max_depth = max(0, int(depth))
        seen = {entity_id}
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        found: list[dict[str, Any]] = []
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= max_depth:
                continue
            clauses: list[str] = []
            params: list[Any] = []
            if direction in {"both", "out"}:
                clauses.append("r.source_id = ?")
                params.append(current)
            if direction in {"both", "in"}:
                clauses.append("r.target_id = ?")
                params.append(current)
            sql = "SELECT r.* FROM relations r JOIN entities s ON s.id=r.source_id JOIN entities t ON t.id=r.target_id WHERE (" + " OR ".join(clauses) + ") AND s.deleted=0 AND t.deleted=0"
            if relation_type:
                sql += " AND r.relation_type = ?"
                params.append(_normalise_relation_type(relation_type))
            with self._lock:
                rows = self.conn.execute(sql, params).fetchall()
            for row in rows:
                relation = self._row_to_relation(row)
                neighbour_id = relation.target_id if relation.source_id == current else relation.source_id
                if neighbour_id in seen:
                    continue
                neighbour = self.get_entity(neighbour_id)
                if not neighbour:
                    continue
                seen.add(neighbour_id)
                queue.append((neighbour_id, current_depth + 1))
                # Keep the nested representation for rich clients, while also
                # exposing the entity fields at the top level for simple graph
                # widgets and older integrations that expect ``item['id']``.
                item = dict(neighbour.to_dict())
                item.update({"entity": neighbour.to_dict(), "relation": relation.to_dict(), "depth": current_depth + 1})
                found.append(item)
        return found

    def graph(
        self,
        entity_ids: Iterable[str] | str | None = None,
        *,
        entity_type: str | Sequence[str] | None = None,
        relation_type: str | None = None,
        depth: int | None = None,
    ) -> dict[str, Any]:
        """Return nodes and edges for the interactive graph view."""
        # Accept a single ID positionally for small scripts and older UI
        # adapters, while retaining the richer iterable form.
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        entities = self.list_entities(entity_type=entity_type)
        entity_map = {e.id: e for e in entities if e.id}
        relations = self.list_relations(relation_type=relation_type)
        if entity_ids is not None:
            seeds = {str(x) for x in entity_ids}
            if depth is None:
                allowed = seeds
                for relation in relations:
                    if relation.source_id in seeds:
                        allowed.add(relation.target_id)
                    if relation.target_id in seeds:
                        allowed.add(relation.source_id)
            else:
                allowed = {x for x in seeds if x in entity_map}
                for level in range(max(0, int(depth))):
                    edge_ids = {r.target_id for r in relations if r.source_id in allowed} | {r.source_id for r in relations if r.target_id in allowed}
                    allowed |= edge_ids
            entity_map = {key: val for key, val in entity_map.items() if key in allowed}
            relations = [r for r in relations if r.source_id in entity_map and r.target_id in entity_map]
        nodes = [e.to_dict() for e in entity_map.values()]
        edges = [r.to_dict() for r in relations if r.source_id in entity_map and r.target_id in entity_map]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges), "generated_at": utc_now()}

    def backlinks(self, entity_id: str, *, relation_type: str | None = None) -> list[dict[str, Any]]:
        """Entities and relation records that point at ``entity_id``."""
        self.require_entity(entity_id)
        result: list[dict[str, Any]] = []
        for relation in self.list_relations(target_id=entity_id, relation_type=relation_type):
            source = self.get_entity(relation.source_id)
            if source:
                item = dict(source.to_dict())
                item.update({"entity": source.to_dict(), "relation": relation.to_dict()})
                result.append(item)
        return result

    def outlinks(self, entity_id: str, *, relation_type: str | None = None) -> list[dict[str, Any]]:
        self.require_entity(entity_id)
        result: list[dict[str, Any]] = []
        for relation in self.list_relations(source_id=entity_id, relation_type=relation_type):
            target = self.get_entity(relation.target_id)
            if target:
                item = dict(target.to_dict())
                item.update({"entity": target.to_dict(), "relation": relation.to_dict()})
                result.append(item)
        return result

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------
    def _fts_upsert(self, entity: Entity) -> None:
        if not self._fts_available or not entity.id:
            return
        self.conn.execute("DELETE FROM entity_fts WHERE entity_id = ?", (entity.id,))
        self.conn.execute(
            "INSERT INTO entity_fts(entity_id, entity_type, title, content, data) VALUES (?, ?, ?, ?, ?)",
            (entity.id, entity.entity_type, entity.title, entity.content, _json(entity.data)),
        )

    def _fts_delete(self, entity_id: str) -> None:
        if self._fts_available:
            self.conn.execute("DELETE FROM entity_fts WHERE entity_id = ?", (entity_id,))

    def search(
        self,
        query: str,
        entity_type: str | None = None,
        *,
        entity_types: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        query = str(query or "").strip()
        if not query:
            return []
        if isinstance(entity_types, str):
            types = [entity_types]
        else:
            types = list(entity_types or ([] if not entity_type or entity_type == "All" else [entity_type]))
        if self._fts_available:
            # Quoting each token avoids accidental MATCH operators from user text.
            tokens = [part for part in query.replace("\n", " ").split() if part]
            match = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
            sql = """
                SELECT e.*, bm25(entity_fts) AS rank
                FROM entity_fts JOIN entities e ON e.id = entity_fts.entity_id
                WHERE e.deleted = 0 AND entity_fts MATCH ?
            """
            params: list[Any] = [match]
            if types:
                sql += " AND e.entity_type IN (" + ",".join("?" for _ in types) + ")"
                params.extend(types)
            sql += " ORDER BY rank LIMIT ?"
            params.append(max(0, int(limit)))
            try:
                with self._lock:
                    rows = self.conn.execute(sql, params).fetchall()
                return [SearchHit(self._row_to_entity(row), float(row["rank"] or 0.0), self._snippet(self._row_to_entity(row), query)) for row in rows]
            except sqlite3.DatabaseError:
                pass
        # Portable LIKE fallback (also catches malformed FTS punctuation).
        pattern = f"%{query}%"
        sql = "SELECT * FROM entities WHERE deleted = 0 AND (title LIKE ? COLLATE NOCASE OR content LIKE ? COLLATE NOCASE OR data_json LIKE ? COLLATE NOCASE OR entity_type LIKE ? COLLATE NOCASE)"
        params = [pattern, pattern, pattern, pattern]
        if types:
            sql += " AND entity_type IN (" + ",".join("?" for _ in types) + ")"
            params.extend(types)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(0, int(limit)))
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [SearchHit(self._row_to_entity(row), 0.0, self._snippet(self._row_to_entity(row), query)) for row in rows]

    @staticmethod
    def _snippet(entity: Entity, query: str, length: int = 180) -> str:
        text = " ".join(x for x in (entity.title, entity.content, _json(entity.data)) if x)
        if not text:
            return ""
        lower, needle = text.lower(), query.lower()
        index = lower.find(needle)
        if index < 0:
            return text[:length]
        start = max(0, index - length // 3)
        return ("…" if start else "") + text[start : start + length]

    # ------------------------------------------------------------------
    # Daily logs, explicit timeline, and history
    # ------------------------------------------------------------------
    def save_daily_log(
        self,
        log_date: str,
        fields: Mapping[str, Any] | None = None,
        *,
        read: str = "",
        built: str = "",
        tested: str = "",
        learned: str = "",
        questions: str = "",
        tomorrow: str = "",
        content: str = "",
        **extra: Any,
    ) -> Entity:
        # Keep the canonical date inside the structured payload on both the
        # insert and update paths.  The update path replaces the JSON object
        # deliberately, so omitting it there would make an idempotent save
        # lose the log's date even though the daily_logs index still points to
        # the entity.
        supplied = dict(fields or {})
        # A legacy caller may pass the six sections as a mapping.  Preserve
        # those values; keyword arguments fill only sections omitted there.
        defaults = {"read": read, "built": built, "tested": tested, "learned": learned, "questions": questions, "tomorrow": tomorrow}
        for key, value in defaults.items():
            supplied.setdefault(key, value)
        supplied.update(extra)
        fields = {"date": log_date, **supplied}
        with self._lock:
            row = self.conn.execute("SELECT entity_id FROM daily_logs WHERE log_date = ?", (log_date,)).fetchone()
        if row:
            return self.update_entity(row["entity_id"], content=content, data=fields, replace_data=True)
        entity = self.create_entity(Entity(entity_type="DailyLog", title=f"Research Log {log_date}", content=content, data={"date": log_date, **fields}))
        with self._lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO daily_logs(log_date, entity_id) VALUES (?, ?)", (log_date, entity.id))
        return entity

    def get_daily_log(self, log_date: str) -> Entity | None:
        with self._lock:
            row = self.conn.execute("SELECT entity_id FROM daily_logs WHERE log_date = ?", (log_date,)).fetchone()
        return self.get_entity(row["entity_id"]) if row else None

    def list_daily_logs(self, *, limit: int | None = None) -> list[Entity]:
        return self.list_entities(entity_type="DailyLog", limit=limit, order_by="title", descending=True)

    def add_timeline_event(
        self,
        event_type: str,
        title: str,
        *,
        occurred_at: str | None = None,
        entity_id: str | None = None,
        details: Mapping[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if entity_id:
            self.require_entity(entity_id, include_deleted=True)
        event = {
            "id": event_id or _new_id("evt"),
            "entity_id": entity_id,
            "event_type": str(event_type or "NOTE"),
            "occurred_at": occurred_at or utc_now(),
            "title": str(title or ""),
            "details": dict(details or {}),
            "created_at": utc_now(),
        }
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO timeline_events(id, entity_id, event_type, occurred_at, title, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event["id"], event["entity_id"], event["event_type"], event["occurred_at"], event["title"], _json(event["details"]), event["created_at"]),
            )
        self._maybe_autosave()
        return event

    def _record_event(self, event_type: str, title: str, *, entity_id: str | None = None, occurred_at: str | None = None) -> None:
        # Internal helper is called inside an existing transaction.
        self.conn.execute(
            "INSERT INTO timeline_events(id, entity_id, event_type, occurred_at, title, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_new_id("evt"), entity_id, event_type, occurred_at or utc_now(), title, "{}", utc_now()),
        )

    def list_timeline(
        self,
        *,
        entity_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM timeline_events WHERE 1=1"
        params: list[Any] = []
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if since:
            sql += " AND occurred_at >= ?"
            params.append(since)
        if until:
            sql += " AND occurred_at <= ?"
            params.append(until)
        sql += " ORDER BY occurred_at ASC, created_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(0, int(limit)))
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "id": row["id"],
                "entity_id": row["entity_id"],
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "title": row["title"],
                "details": _parse_json(row["details_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def entity_history(self, entity_id: str) -> list[dict[str, Any]]:
        self.require_entity(entity_id, include_deleted=True)
        with self._lock:
            rows = self.conn.execute("SELECT * FROM entity_revisions WHERE entity_id = ? ORDER BY version ASC, id ASC", (entity_id,)).fetchall()
        return [
            {
                "id": row["id"],
                "entity_id": row["entity_id"],
                "version": row["version"],
                "operation": row["operation"],
                "snapshot": _parse_json(row["snapshot_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Integrity, backup, restore
    # ------------------------------------------------------------------
    def integrity_check(self) -> dict[str, Any]:
        with self._lock:
            quick = str(self.conn.execute("PRAGMA quick_check").fetchone()[0])
            full = str(self.conn.execute("PRAGMA integrity_check").fetchone()[0])
            foreign = [dict(row) for row in self.conn.execute("PRAGMA foreign_key_check").fetchall()]
            counts = {
                "entities": int(self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]),
                "relations": int(self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]),
                "revisions": int(self.conn.execute("SELECT COUNT(*) FROM entity_revisions").fetchone()[0]),
            }
        ok = quick.lower() == "ok" and full.lower() == "ok" and not foreign
        return {"ok": ok, "quick_check": quick, "integrity_check": full, "foreign_key_errors": foreign, "schema_version": int(self.conn.execute("PRAGMA user_version").fetchone()[0]), "counts": counts}

    def assert_integrity(self) -> None:
        result = self.integrity_check()
        if not result["ok"]:
            raise IntegrityError(json.dumps(result, ensure_ascii=False))

    def backup(self, destination: str | os.PathLike[str] | None = None) -> Path:
        """Create a consistent SQLite backup using SQLite's online backup API."""
        if destination is None:
            if not self.backup_dir:
                raise StoreError("backup destination is required when backup_dir is not configured")
            destination = self.backup_dir / f"research_os_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Avoid copying a database onto itself.
        if str(target.resolve()) == str(self.path.resolve()) and str(self.path) != ":memory:":
            raise StoreError("backup destination must differ from the active database")
        if target.exists():
            target.unlink()
        if str(self.path) == ":memory:":
            dest_conn = sqlite3.connect(str(target))
            try:
                with dest_conn:
                    self.conn.backup(dest_conn)
            finally:
                dest_conn.close()
        else:
            dest_conn = sqlite3.connect(str(target))
            try:
                with self._lock:
                    self.conn.commit()
                    self.conn.backup(dest_conn)
            finally:
                dest_conn.close()
        return target

    def restore(
        self,
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str] | None = None,
        *,
        replace: bool = True,
    ) -> "ResearchStore | None":
        """Restore a validated backup.

        With only ``source`` the active workspace is replaced and re-opened,
        which is the safe operation needed by the desktop UI.  Supplying a
        different ``destination`` writes a restored copy and returns a new
        :class:`ResearchStore` for that copy.  ``restore_to`` below preserves
        an explicit class-level style for scripts that want a new workspace.
        """
        # When accessed through the class, a regular method is unbound:
        # ``ResearchStore.restore(backup, destination)`` therefore arrives with
        # ``self`` equal to the backup path and ``source`` equal to destination.
        # Preserve that early public spelling as well as ``restore_to``.
        if not isinstance(self, ResearchStore):
            return ResearchStore.restore_to(self, source, replace=replace)
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(src)
        dst = Path(destination) if destination is not None else self.path
        same_active = str(dst.resolve()) == str(self.path.resolve()) and str(self.path) != ":memory:"
        if dst.exists() and not same_active and not replace:
            raise FileExistsError(f"destination exists (pass replace=True): {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Validate before copying so a corrupt backup never becomes active.
        check = sqlite3.connect(str(src))
        try:
            status = str(check.execute("PRAGMA integrity_check").fetchone()[0])
            if status.lower() != "ok":
                raise IntegrityError(f"backup integrity check failed: {status}")
        finally:
            check.close()
        # Restoring a workspace from itself is a harmless no-op.  Avoid
        # closing the live connection and then asking shutil to copy a file
        # onto itself (which raises ``SameFileError`` on Windows).
        if same_active and src.resolve() == dst.resolve():
            return None
        if str(self.path) == ":memory:" and destination is None:
            # An in-memory workspace has no file to replace.  Reopen a fresh
            # connection and stream the validated backup into it instead.
            source_conn = sqlite3.connect(str(src))
            try:
                self.conn.close()
                self.conn = sqlite3.connect(":memory:", timeout=30.0, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA foreign_keys = ON")
                source_conn.backup(self.conn)
                self.conn.commit()
                self._migrate()
                self._fts_available = self._ensure_fts()
            finally:
                source_conn.close()
            return None
        if same_active:
            # Close WAL handles before replacing the file, then reopen the
            # connection and rebuild the optional FTS index.
            self.close()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(dst) + suffix)
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError:
                        pass
            shutil.copy2(src, dst)
            db_target = str(dst)
            self.conn = sqlite3.connect(db_target, timeout=30.0, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:
                pass
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self._migrate()
            self._fts_available = self._ensure_fts()
            return None
        shutil.copy2(src, dst)
        return ResearchStore(dst, backup_dir=self.backup_dir, autosave=self.autosave, autosave_interval=self.autosave_interval)

    @classmethod
    def restore_to(
        cls,
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
        *,
        replace: bool = False,
    ) -> "ResearchStore":
        """Explicit class-level convenience for restoring a new workspace."""
        # A temporary in-memory owner lets the instance implementation perform
        # the same validation and copy logic without duplicating it.
        owner = cls(":memory:")
        try:
            result = owner.restore(source, destination, replace=replace)
        finally:
            owner.close()
        if isinstance(result, ResearchStore):
            return result
        return cls(destination)

    def recover_latest_backup(self, *, destination: str | os.PathLike[str] | None = None) -> "ResearchStore":
        if not self.backup_dir:
            raise StoreError("backup_dir is not configured")
        candidates = sorted(self.backup_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise FileNotFoundError(f"no backups in {self.backup_dir}")
        dst = Path(destination) if destination else self.path.with_name(self.path.stem + ".recovered.sqlite3")
        result = self.restore(candidates[0], dst, replace=True)
        return result if isinstance(result, ResearchStore) else ResearchStore(dst)

    # ------------------------------------------------------------------
    # Export convenience methods (implemented lazily to avoid import cycles)
    # ------------------------------------------------------------------
    def export_markdown(self, destination: str | os.PathLike[str]) -> Path:
        from .exporter import ResearchExporter

        return ResearchExporter(self).markdown(destination)

    def export_html(self, destination: str | os.PathLike[str]) -> Path:
        from .exporter import ResearchExporter

        return ResearchExporter(self).html(destination)

    def export_graph_json(self, destination: str | os.PathLike[str]) -> Path:
        from .exporter import ResearchExporter

        return ResearchExporter(self).graph_json(destination)

    def export_csv(self, destination: str | os.PathLike[str]) -> Path:
        from .exporter import ResearchExporter

        return ResearchExporter(self).csv(destination)


def create_workspace(path: str | os.PathLike[str], *, backup_dir: str | os.PathLike[str] | None = None) -> ResearchStore:
    """Compatibility helper used by scripts and tests."""
    return ResearchStore(path, backup_dir=backup_dir)


def open_workspace(path: str | os.PathLike[str], *, backup_dir: str | os.PathLike[str] | None = None) -> ResearchStore:
    """Alias used by the desktop shell and external scripts."""
    return create_workspace(path, backup_dir=backup_dir)
