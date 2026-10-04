"""Tkinter desktop interface for Research OS.

The UI is intentionally dependency free.  It talks to :class:`ResearchStore`
when the domain layer is available and contains a small SQLite fallback so a
fresh checkout is still usable before optional packaging steps have run.

The interface is a research graph workspace rather than a notes editor: all
records are typed entities, relations are first class, and every screen can
open the same entity editor and backlink panel.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sqlite3
import tempfile
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .models import ENTITY_TYPES, Entity, Relation

try:  # The core agent supplies the production store.
    from .store import ResearchStore  # type: ignore
except Exception:  # pragma: no cover - fallback is exercised on a fresh checkout
    ResearchStore = None  # type: ignore


RELATION_TYPES = (
    "SUPPORTS",
    "REFUTES",
    "INSPIRES",
    "TESTED_BY",
    "USES",
    "PRODUCES",
    "CONTRADICTS",
    "NEEDS_VERIFICATION",
    "CITES",
    "DERIVED_FROM",
    "RELATED_TO",
    "PART_OF",
    "NEXT_STEP",
    "MOTIVATES",
    "DOCUMENTS",
    "VISUALIZES",
    "INFORMS",
    "FOLLOWS",
    "EXTENDS",
    "SUBQUESTION_OF",
    "DECOMPOSES",
    "HAS_SUBQUESTION",
)

TYPE_COLORS = {
    "Paper": "#6da8ff",
    "Claim": "#ffb86b",
    "Evidence": "#77d7a2",
    "Concept": "#b79cff",
    "Question": "#ff8fa3",
    "Hypothesis": "#f5df68",
    "Experiment": "#63d9d4",
    "Dataset": "#c0a0ff",
    "Artifact": "#d6a67a",
    "Result": "#7dd3fc",
    "Decision": "#fca5a5",
    "Idea": "#f9a8d4",
    "Task": "#a7f3d0",
    "DailyLog": "#cbd5e1",
}

BG = "#111827"
PANEL = "#1b2433"
PANEL_2 = "#222e40"
TEXT = "#edf2f7"
MUTED = "#9aa9bd"
ACCENT = "#5eead4"
ENTRY_BG = "#0f172a"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _entity(value: Any) -> Entity:
    """Normalize store return values into the public dataclass."""
    if isinstance(value, Entity):
        return value
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return Entity.from_dict(value)
    return Entity(entity_type="Concept", title=str(value), id=str(value))


def _relation(value: Any) -> Relation:
    if isinstance(value, Relation):
        return value
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return Relation.from_dict(value)
    return Relation(source_id="", relation_type="RELATED_TO", target_id="")


class _FallbackStore:
    """Minimal SQLite implementation used only if the core store is absent.

    It mirrors the methods used by the UI and is deliberately conservative:
    no data is held solely in memory, and SQLite's backup API is used for
    snapshots.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities(
              id TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
              data_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
              deleted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS relations(
              id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
              relation_type TEXT NOT NULL, target_id TEXT NOT NULL,
              metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
              UNIQUE(source_id, relation_type, target_id),
              FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
              FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        if entity_type and entity_type != "All":
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE deleted=0 AND entity_type=? ORDER BY updated_at DESC",
                (entity_type,),
            )
        else:
            rows = self._conn.execute("SELECT * FROM entities WHERE deleted=0 ORDER BY updated_at DESC")
        return [self._row_entity(row) for row in rows]

    def _row_entity(self, row: sqlite3.Row) -> Entity:
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        return Entity(
            id=row["id"], entity_type=row["entity_type"], title=row["title"],
            content=row["content"], data=data, created_at=row["created_at"],
            updated_at=row["updated_at"], version=row["version"],
        )

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self._conn.execute("SELECT * FROM entities WHERE id=? AND deleted=0", (entity_id,)).fetchone()
        return self._row_entity(row) if row else None

    def create_entity(self, value: Entity | None = None, **kwargs: Any) -> Entity:
        value = value or Entity.from_dict(kwargs)
        value.id = value.id or str(uuid.uuid4())
        stamp = _now()
        value.created_at = value.created_at or stamp
        value.updated_at = stamp
        self._conn.execute(
            "INSERT INTO entities(id,entity_type,title,content,data_json,created_at,updated_at,version) VALUES(?,?,?,?,?,?,?,?)",
            (value.id, value.entity_type, value.title, value.content, json.dumps(value.data, ensure_ascii=False),
             value.created_at, value.updated_at, value.version),
        )
        self._conn.commit()
        return value

    def update_entity(self, value: Entity | None = None, **kwargs: Any) -> Entity:
        value = value or Entity.from_dict(kwargs)
        if not value.id:
            return self.create_entity(value)
        old = self.get_entity(value.id)
        if not old:
            return self.create_entity(value)
        value.created_at = old.created_at
        value.updated_at = _now()
        value.version = old.version + 1
        self._conn.execute(
            "UPDATE entities SET entity_type=?,title=?,content=?,data_json=?,updated_at=?,version=? WHERE id=?",
            (value.entity_type, value.title, value.content, json.dumps(value.data, ensure_ascii=False),
             value.updated_at, value.version, value.id),
        )
        self._conn.commit()
        return value

    def delete_entity(self, entity_id: str) -> None:
        self._conn.execute("UPDATE entities SET deleted=1,updated_at=? WHERE id=?", (_now(), entity_id))
        self._conn.commit()

    def search(self, query: str, entity_type: str | None = None) -> list[Any]:
        pattern = f"%{query}%"
        sql = "SELECT * FROM entities WHERE deleted=0 AND (title LIKE ? OR content LIKE ? OR data_json LIKE ?)"
        args: list[Any] = [pattern, pattern, pattern]
        if entity_type and entity_type != "All":
            sql += " AND entity_type=?"
            args.append(entity_type)
        sql += " ORDER BY updated_at DESC"
        return [self._row_entity(row) for row in self._conn.execute(sql, args)]

    def list_relations(self, entity_id: str | None = None) -> list[Relation]:
        if entity_id:
            rows = self._conn.execute("SELECT * FROM relations WHERE source_id=? OR target_id=?", (entity_id, entity_id))
        else:
            rows = self._conn.execute("SELECT * FROM relations ORDER BY created_at DESC")
        result = []
        for row in rows:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except Exception:
                meta = {}
            result.append(Relation(id=row["id"], source_id=row["source_id"], relation_type=row["relation_type"],
                                   target_id=row["target_id"], metadata=meta, created_at=row["created_at"]))
        return result

    def create_relation(self, value: Relation | None = None, **kwargs: Any) -> Relation:
        value = value or Relation.from_dict(kwargs)
        value.id = value.id or str(uuid.uuid4())
        value.created_at = value.created_at or _now()
        self._conn.execute(
            "INSERT OR IGNORE INTO relations(id,source_id,relation_type,target_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (value.id, value.source_id, value.relation_type, value.target_id, json.dumps(value.metadata), value.created_at),
        )
        self._conn.commit()
        return value

    def delete_relation(self, relation_id: str) -> None:
        self._conn.execute("DELETE FROM relations WHERE id=?", (relation_id,))
        self._conn.commit()

    def neighbors(self, entity_id: str) -> list[Entity]:
        ids = [r.source_id if r.target_id == entity_id else r.target_id for r in self.list_relations(entity_id)]
        return [e for i in ids if (e := self.get_entity(i))]

    def graph(self) -> tuple[list[Entity], list[Relation]]:
        return self.list_entities(), self.list_relations()

    def backlinks(self, entity_id: str) -> list[tuple[Entity, Relation]]:
        result = []
        for relation in self.list_relations(entity_id):
            if relation.target_id == entity_id:
                source = self.get_entity(relation.source_id)
                if source:
                    result.append((source, relation))
        return result

    def integrity_check(self) -> str:
        return str(self._conn.execute("PRAGMA integrity_check").fetchone()[0])

    def backup(self, destination: str | os.PathLike[str]) -> str:
        destination = str(destination)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        self._conn.backup(target)
        target.close()
        return destination

    def restore(self, source: str | os.PathLike[str]) -> None:
        source_conn = sqlite3.connect(str(source))
        source_conn.backup(self._conn)
        source_conn.close()
        self._conn.commit()


class StoreFacade:
    """Adapt small variations in ResearchStore APIs without coupling the UI."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backend: Any
        if ResearchStore is not None:
            try:
                # Keep rolling SQLite checkpoints beside the workspace.  The
                # core store only creates a checkpoint when a mutation occurs,
                # so a normal session never pays a backup cost on every timer
                # tick while still having a recoverable copy after edits.
                self.backend = ResearchStore(
                    str(self.db_path),
                    backup_dir=str(self.db_path.parent / "backups"),
                    autosave=True,
                    autosave_interval=300.0,
                )
            except TypeError:
                try:
                    self.backend = ResearchStore(path=str(self.db_path))
                except Exception:
                    self.backend = _FallbackStore(self.db_path)
            except Exception:
                self.backend = _FallbackStore(self.db_path)
        else:
            self.backend = _FallbackStore(self.db_path)

    @property
    def path(self) -> str:
        return str(self.db_path)

    def _method(self, *names: str):
        for name in names:
            method = getattr(self.backend, name, None)
            if callable(method):
                return method
        return None

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        method = self._method("list_entities", "entities", "all_entities")
        if method:
            # ``All`` is a UI sentinel, not a persisted entity type.  Pass
            # ``None`` to the core store so the complete graph is returned.
            requested = None if not entity_type or entity_type == "All" else entity_type
            for args, kwargs in [((requested,), {}), ((), {"entity_type": requested}), ((), {})]:
                try:
                    value = method(*args, **kwargs) if args or kwargs else method()
                    result = [_entity(v) for v in (value or [])]
                    if requested and not (args or kwargs):
                        result = [v for v in result if v.entity_type == entity_type]
                    return result
                except (TypeError, ValueError):
                    continue
        return []

    def get_entity(self, entity_id: str) -> Entity | None:
        method = self._method("get_entity", "read_entity", "find_entity")
        if method:
            try:
                value = method(entity_id)
                return _entity(value) if value else None
            except (TypeError, ValueError):
                pass
        return next((e for e in self.list_entities() if e.id == entity_id), None)

    def create_entity(self, value: Entity) -> Entity:
        method = self._method("create_entity", "add_entity", "insert_entity")
        if method:
            for args, kwargs in [((value,), {}), ((), value.to_dict()), ((), {"entity": value})]:
                try:
                    return _entity(method(*args, **kwargs))
                except (TypeError, ValueError):
                    continue
        # This path is mostly for an unusual custom backend.
        if isinstance(self.backend, _FallbackStore):
            return self.backend.create_entity(value)
        raise RuntimeError("ResearchStore does not expose create_entity")

    def update_entity(self, value: Entity) -> Entity:
        method = self._method("update_entity", "save_entity", "put_entity")
        if method:
            # ResearchStore's intentionally explicit API is
            # ``update_entity(entity_id, entity, **changes)`` while the
            # fallback and a few older adapters accept ``update_entity(entity)``.
            # Prefer the explicit form first so a typed Entity is never bound
            # accidentally as a SQLite parameter.
            if value.id:
                try:
                    return _entity(method(value.id, value, replace_data=True))
                except (TypeError, ValueError, KeyError, sqlite3.Error):
                    pass
            for args, kwargs in [((value,), {}), ((), value.to_dict()), ((), {"entity": value})]:
                try:
                    return _entity(method(*args, **kwargs))
                except (TypeError, ValueError, KeyError, sqlite3.Error):
                    continue
        if isinstance(self.backend, _FallbackStore):
            return self.backend.update_entity(value)
        raise RuntimeError("ResearchStore does not expose update_entity")

    def delete_entity(self, entity_id: str) -> None:
        method = self._method("delete_entity", "remove_entity")
        if method:
            method(entity_id)

    def search(self, query: str, entity_type: str | None = None) -> list[Entity]:
        method = self._method("search", "search_entities", "full_text_search")
        if method:
            attempts = []
            if entity_type and entity_type != "All":
                # Core ResearchStore uses the plural keyword ``entity_types``.
                attempts.append(((query,), {"entity_types": [entity_type]}))
                attempts.append(((query,), {"entity_type": entity_type}))
            attempts.extend([((query, entity_type), {}), ((query,), {})])
            for args, kwargs in attempts:
                try:
                    value = method(*args, **kwargs)
                    result = [_entity(v.entity if hasattr(v, "entity") else v) for v in (value or [])]
                    if entity_type and entity_type != "All" and not kwargs and len(args) <= 1:
                        result = [v for v in result if v.entity_type == entity_type]
                    return result
                except (TypeError, ValueError, KeyError, sqlite3.Error):
                    continue
        return [e for e in self.list_entities(entity_type) if query.lower() in (e.title + " " + e.content + " " + json.dumps(e.data)).lower()]

    def list_relations(self, entity_id: str | None = None) -> list[Relation]:
        method = self._method("list_relations", "relations", "all_relations")
        if method:
            for args, kwargs in [((entity_id,), {}), ((), {"entity_id": entity_id}), ((), {})]:
                try:
                    value = method(*args, **kwargs) if args or kwargs else method()
                    result = [_relation(v) for v in (value or [])]
                    if entity_id and not (args or kwargs):
                        result = [r for r in result if entity_id in (r.source_id, r.target_id)]
                    return result
                except (TypeError, ValueError):
                    continue
        return []

    def create_relation(self, value: Relation) -> Relation:
        method = self._method("create_relation", "add_relation", "insert_relation")
        if method:
            for args, kwargs in [((value,), {}), ((), value.to_dict()), ((), {"relation": value})]:
                try:
                    return _relation(method(*args, **kwargs))
                except (TypeError, ValueError):
                    continue
        if isinstance(self.backend, _FallbackStore):
            return self.backend.create_relation(value)
        raise RuntimeError("ResearchStore does not expose create_relation")

    def delete_relation(self, relation_id: str) -> None:
        method = self._method("delete_relation", "remove_relation")
        if method:
            method(relation_id)

    def neighbors(self, entity_id: str) -> list[Entity]:
        method = self._method("neighbors", "get_neighbors", "neighbor_entities")
        if method:
            try:
                result = []
                for item in method(entity_id) or []:
                    # ResearchStore returns {entity: ..., relation: ..., depth: ...}.
                    if isinstance(item, Mapping) and "entity" in item:
                        result.append(_entity(item["entity"]))
                    else:
                        result.append(_entity(item))
                return result
            except (TypeError, ValueError, KeyError, sqlite3.Error):
                pass
        ids = []
        for r in self.list_relations(entity_id):
            ids.append(r.target_id if r.source_id == entity_id else r.source_id)
        return [e for i in ids if (e := self.get_entity(i))]

    def graph(self) -> tuple[list[Entity], list[Relation]]:
        method = self._method("graph", "get_graph", "graph_data")
        if method:
            try:
                value = method()
                if isinstance(value, Mapping):
                    return ([_entity(v) for v in value.get("entities", value.get("nodes", []))],
                            [_relation(v) for v in value.get("relations", value.get("edges", []))])
                if isinstance(value, (tuple, list)) and len(value) == 2:
                    return ([_entity(v) for v in value[0]], [_relation(v) for v in value[1]])
            except (TypeError, ValueError):
                pass
        return self.list_entities(), self.list_relations()

    def backlinks(self, entity_id: str) -> list[tuple[Entity, Relation]]:
        method = self._method("backlinks", "get_backlinks")
        if method:
            try:
                result = []
                for item in method(entity_id) or []:
                    if isinstance(item, (tuple, list)) and len(item) >= 2:
                        result.append((_entity(item[0]), _relation(item[1])))
                    elif isinstance(item, Mapping):
                        result.append((_entity(item.get("entity", item)), _relation(item.get("relation", {}))))
                return result
            except (TypeError, ValueError):
                pass
        result = []
        for r in self.list_relations(entity_id):
            if r.target_id == entity_id:
                e = self.get_entity(r.source_id)
                if e:
                    result.append((e, r))
        return result

    def integrity_check(self) -> str:
        method = self._method("integrity_check", "check_integrity", "database_integrity")
        if method:
            try:
                value = method()
                if isinstance(value, Mapping):
                    return str(value.get("status", value.get("result", value)))
                return str(value)
            except Exception as exc:
                return f"ERROR: {exc}"
        return "not available"

    def save_daily_log(self, log_date: str, fields: Mapping[str, Any]) -> Entity:
        """Persist a daily log through the richer core API when available."""
        method = self._method("save_daily_log")
        if method:
            try:
                result = method(log_date, **dict(fields))
                return _entity(result)
            except (TypeError, ValueError, KeyError, sqlite3.Error):
                pass
        existing = next((e for e in self.list_entities("DailyLog") if e.data.get("date") == log_date), None)
        value = Entity(entity_type="DailyLog", title=f"Daily log {log_date}", data={"date": log_date, **dict(fields)}, id=existing.id if existing else None, created_at=existing.created_at if existing else None, version=existing.version if existing else 1)
        return self.update_entity(value) if existing else self.create_entity(value)

    def get_daily_log(self, log_date: str) -> Entity | None:
        method = self._method("get_daily_log")
        if method:
            try:
                value = method(log_date)
                return _entity(value) if value else None
            except (TypeError, ValueError, sqlite3.Error):
                pass
        return next((e for e in self.list_entities("DailyLog") if e.data.get("date") == log_date), None)

    def list_timeline(self, limit: int | None = None) -> list[dict[str, Any]]:
        method = self._method("list_timeline")
        if method:
            try:
                value = method(limit=limit) if limit is not None else method()
                return [dict(item) for item in (value or []) if isinstance(item, Mapping)]
            except (TypeError, ValueError, sqlite3.Error):
                pass
        return []

    def export_formats(self, destination: str | os.PathLike[str]) -> dict[str, str]:
        """Write Markdown, HTML, Graph JSON and CSV export artifacts."""
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        results: dict[str, str] = {}
        requests = (
            ("markdown", "export_markdown", root / "archive.md"),
            ("html", "export_html", root / "research_report.html"),
            ("graph_json", "export_graph_json", root / "graph.json"),
            ("csv", "export_csv", root / "entities.csv"),
        )
        for key, method_name, target in requests:
            method = self._method(method_name)
            if method:
                try:
                    results[key] = str(method(target))
                    continue
                except (TypeError, ValueError, OSError, sqlite3.Error):
                    pass
            entities, relations = self.graph()
            if key == "markdown":
                lines = ["# Research OS Archive", "", f"Generated: {_now()}", ""]
                for entity in entities:
                    lines.extend([f"## {entity.entity_type}: {entity.title}", "", entity.content, "", "```json", json.dumps(entity.data, ensure_ascii=False, indent=2), "```", ""])
                target.write_text("\n".join(lines), encoding="utf-8")
            elif key == "html":
                rows = "".join(f"<tr><td>{entity.entity_type}</td><td>{entity.title}</td><td>{entity.content[:300]}</td></tr>" for entity in entities)
                target.write_text("<!doctype html><meta charset='utf-8'><title>Research OS Report</title><h1>Research OS Report</h1><table><tr><th>Type</th><th>Title</th><th>Content</th></tr>" + rows + "</table>", encoding="utf-8")
            elif key == "graph_json":
                target.write_text(json.dumps({"format": "research-os-graph", "nodes": [e.to_dict() for e in entities], "edges": [r.to_dict() for r in relations]}, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                with target.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=("id", "entity_type", "title", "content", "data", "created_at", "updated_at", "version")); writer.writeheader()
                    for entity in entities:
                        writer.writerow({"id": entity.id, "entity_type": entity.entity_type, "title": entity.title, "content": entity.content, "data": json.dumps(entity.data, ensure_ascii=False), "created_at": entity.created_at, "updated_at": entity.updated_at, "version": entity.version})
            results[key] = str(target)
        return results

    def backup(self, destination: str) -> str:
        method = self._method("backup", "backup_database", "create_backup")
        if method:
            try:
                result = method(destination)
                return str(result or destination)
            except TypeError:
                pass
        if isinstance(self.backend, _FallbackStore):
            return self.backend.backup(destination)
        shutil.copy2(self.path, destination)
        return destination

    def restore(self, source: str) -> None:
        method = self._method("restore", "restore_database")
        if isinstance(self.backend, _FallbackStore):
            # The fallback owns an open connection and exposes an instance
            # restore method; do not close it before invoking that method.
            self.backend.restore(source)
            return
        if method:
            # Close the old WAL connection before the file replacement.  The
            # current ResearchStore reopens itself in place; older adapters
            # return a replacement store or require an explicit destination.
            # Closing first avoids a stale -wal sidecar hiding restored rows.
            old = self.backend
            try:
                old.close()
            except Exception:
                pass
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError:
                        pass
            try:
                restored = method(source, self.path, replace=True)
                if restored is not None and hasattr(restored, "list_entities"):
                    self.backend = restored
            except TypeError:
                # Older instance stores use ``restore(source)``.  Re-open a
                # fresh backend after copying in that case.
                shutil.copy2(source, self.path)
                restored = ResearchStore(str(self.path)) if ResearchStore is not None else _FallbackStore(self.path)
                if restored is not None and hasattr(restored, "list_entities"):
                    self.backend = restored
        else:
            shutil.copy2(source, self.path)

    def close(self) -> None:
        method = self._method("close", "shutdown")
        if method:
            try:
                method()
            except Exception:
                pass

    def save(self) -> None:
        method = self._method("save", "commit")
        if method:
            try:
                method()
            except Exception:
                pass


class GraphCanvas(tk.Canvas):
    """Small interactive graph renderer with pan, zoom and node selection."""

    def __init__(self, master: tk.Misc, app: "ResearchOSApp", **kwargs: Any):
        super().__init__(master, background="#0b1220", highlightthickness=0, **kwargs)
        self.app = app
        self.entities: list[Entity] = []
        self.relations: list[Relation] = []
        self.positions: dict[str, tuple[float, float]] = {}
        self.scale = 1.0
        self.origin = [0.0, 0.0]
        self.selected: str | None = None
        self._drag: tuple[float, float] | None = None
        self._pan_start: tuple[float, float] | None = None
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Button-2>", self._on_pan_start)
        self.bind("<B2-Motion>", self._on_pan)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._zoom(1.12, e.x, e.y))
        self.bind("<Button-5>", lambda e: self._zoom(0.89, e.x, e.y))

    def set_graph(self, entities: Iterable[Entity], relations: Iterable[Relation], reset: bool = False) -> None:
        self.entities = list(entities)
        self.relations = list(relations)
        if reset or not self.positions:
            self.positions.clear()
            n = max(1, len(self.entities))
            radius = max(130, min(330, n * 28))
            for i, entity in enumerate(self.entities):
                theta = 2 * math.pi * i / n
                self.positions[entity.id or str(i)] = (radius * math.cos(theta), radius * math.sin(theta))
            self.origin = [0.0, 0.0]
            self.scale = 1.0
        self.redraw()

    def _xy(self, point: tuple[float, float]) -> tuple[float, float]:
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        return (w / 2 + self.origin[0] + point[0] * self.scale, h / 2 + self.origin[1] + point[1] * self.scale)

    def _world(self, x: float, y: float) -> tuple[float, float]:
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        return ((x - w / 2 - self.origin[0]) / self.scale, (y - h / 2 - self.origin[1]) / self.scale)

    def redraw(self) -> None:
        self.delete("all")
        visible = {e.id for e in self.entities if e.id}
        by_id = {e.id: e for e in self.entities}
        for relation in self.relations:
            if relation.source_id not in visible or relation.target_id not in visible:
                continue
            if relation.source_id not in self.positions or relation.target_id not in self.positions:
                continue
            x1, y1 = self._xy(self.positions[relation.source_id])
            x2, y2 = self._xy(self.positions[relation.target_id])
            self.create_line(x1, y1, x2, y2, fill="#52637b", width=max(1, int(self.scale)), arrow=tk.LAST, tags=("edge",))
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.create_text(mx, my, text=relation.relation_type, fill="#7f91aa", font=("Segoe UI", max(7, int(8 * self.scale))), tags=("edge_label",))
        radius = max(16, 24 * self.scale)
        for entity in self.entities:
            if not entity.id or entity.id not in self.positions:
                continue
            x, y = self._xy(self.positions[entity.id])
            fill = TYPE_COLORS.get(entity.entity_type, "#94a3b8")
            outline = ACCENT if entity.id == self.selected else "#dbeafe"
            width = 3 if entity.id == self.selected else 1
            self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline=outline, width=width, tags=(f"node:{entity.id}", "node"))
            label = entity.title[:20] if entity.title else entity.entity_type
            self.create_text(x, y, text=label, fill="#0b1220", font=("Segoe UI", max(7, int(9 * self.scale)), "bold"), width=radius * 1.8, tags=(f"node:{entity.id}", "node"))
            self.create_text(x, y + radius + 8, text=entity.entity_type, fill="#b8c6d8", font=("Segoe UI", max(7, int(8 * self.scale))), tags=(f"node:{entity.id}", "node"))

    def _hit(self, x: float, y: float) -> str | None:
        wx, wy = self._world(x, y)
        threshold = max(28, 34 / self.scale)
        nearest, dist = None, threshold
        for entity in self.entities:
            if not entity.id or entity.id not in self.positions:
                continue
            px, py = self.positions[entity.id]
            d = math.hypot(wx - px, wy - py)
            if d < dist:
                nearest, dist = entity.id, d
        return nearest

    def _on_click(self, event: tk.Event) -> None:
        node = self._hit(event.x, event.y)
        if node:
            self.selected = node
            self.redraw()
            self.app.select_entity(node)
            self._drag = self.positions.get(node)
        else:
            self._pan_start = (event.x, event.y)

    def _on_drag(self, event: tk.Event) -> None:
        if self.selected and self._drag is not None:
            self.positions[self.selected] = self._world(event.x, event.y)
            self.redraw()
        elif self._pan_start:
            self._on_pan(event)

    def _on_release(self, _event: tk.Event) -> None:
        self._drag = None
        self._pan_start = None

    def _on_pan_start(self, event: tk.Event) -> None:
        self._pan_start = (event.x, event.y)

    def _on_pan(self, event: tk.Event) -> None:
        if self._pan_start:
            dx, dy = event.x - self._pan_start[0], event.y - self._pan_start[1]
            self.origin[0] += dx
            self.origin[1] += dy
            self._pan_start = (event.x, event.y)
            self.redraw()

    def _on_wheel(self, event: tk.Event) -> None:
        self._zoom(1.12 if event.delta > 0 else 0.89, event.x, event.y)

    def _zoom(self, factor: float, x: float, y: float) -> None:
        before = self._world(x, y)
        self.scale = min(3.5, max(0.25, self.scale * factor))
        after = self._world(x, y)
        self.origin[0] += (after[0] - before[0]) * self.scale
        self.origin[1] += (after[1] - before[1]) * self.scale
        self.redraw()


class ResearchOSApp(tk.Tk):
    """Main Research OS desktop application."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        super().__init__()
        self.title("Research OS · 个人科研操作系统")
        self.geometry("1360x860")
        self.minsize(1080, 680)
        self.configure(background=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._style()
        default_path = Path(os.environ.get("RESEARCHOS_HOME", Path.home() / "ResearchOS")) / "researchos.sqlite3"
        self.store = StoreFacade(db_path or default_path)
        self.current_entity: Entity | None = None
        self.current_view = "dashboard"
        self._build_shell()
        self._show_dashboard()
        self.after(250, self._autosave_tick)

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 22, "bold"))
        style.configure("Section.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI", 12, "bold"))
        style.configure("TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, padding=(10, 6))
        style.map("TButton", background=[("active", "#33455f")])
        style.configure("Accent.TButton", background="#168b83", foreground="#06151a", padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#22b8aa")])
        style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=TEXT, insertcolor=TEXT)
        style.configure("TCombobox", fieldbackground=ENTRY_BG, background=PANEL_2, foreground=TEXT)
        style.configure("Treeview", background=ENTRY_BG, fieldbackground=ENTRY_BG, foreground=TEXT, rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=ACCENT, relief="flat")
        style.map("Treeview", background=[("selected", "#225b65")], foreground=[("selected", "#ffffff")])
        style.configure("TNotebook", background=PANEL)
        style.configure("TNotebook.Tab", background=PANEL_2, foreground=TEXT, padding=(12, 6))

    def _build_shell(self) -> None:
        self.header = ttk.Frame(self)
        self.header.pack(fill="x", padx=18, pady=(14, 8))
        ttk.Label(self.header, text="RESEARCH OS", style="Title.TLabel").pack(side="left")
        ttk.Label(self.header, text="  个人科研操作系统 · structured research graph", style="Muted.TLabel").pack(side="left", pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right", pady=(8, 0))
        ttk.Button(self.header, text="＋ New", style="Accent.TButton", command=self.new_entity).pack(side="right", padx=(8, 0))
        ttk.Button(self.header, text="⌕ Search", command=lambda: self.show_view("search")).pack(side="right")

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        # Keep the complete research workspace reachable on small laptop
        # screens.  A fixed stack of every workflow button used to make the
        # DATA section overlap the last navigation item at 768px height.
        self.nav_shell = ttk.Frame(self.body, width=220)
        self.nav_shell.pack(side="left", fill="y", padx=(0, 12))
        self.nav_canvas = tk.Canvas(self.nav_shell, width=220, background=PANEL, highlightthickness=0, borderwidth=0)
        self.nav_scroll = ttk.Scrollbar(self.nav_shell, orient="vertical", command=self.nav_canvas.yview)
        self.nav_canvas.configure(yscrollcommand=self.nav_scroll.set)
        self.nav_canvas.pack(side="left", fill="both", expand=True)
        self.nav_scroll.pack(side="right", fill="y")
        self.nav = ttk.Frame(self.nav_canvas)
        self.nav_window = self.nav_canvas.create_window((0, 0), window=self.nav, anchor="nw")
        self.nav.bind("<Configure>", lambda _event: self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox("all")))
        self.nav_canvas.bind("<Configure>", lambda event: self.nav_canvas.itemconfigure(self.nav_window, width=event.width))
        self.nav_canvas.bind_all("<MouseWheel>", self._scroll_nav, add="+")
        self.content = ttk.Frame(self.body)
        self.content.pack(side="left", fill="both", expand=True)
        self._build_nav()

    def _scroll_nav(self, event: tk.Event) -> None:
        """Scroll the navigation pane only while the pointer is over it."""
        try:
            x, y = self.nav_canvas.winfo_pointerx(), self.nav_canvas.winfo_pointery()
            left = self.nav_canvas.winfo_rootx(); top = self.nav_canvas.winfo_rooty()
            if left <= x <= left + self.nav_canvas.winfo_width() and top <= y <= top + self.nav_canvas.winfo_height():
                self.nav_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        except tk.TclError:
            pass

    def _build_nav(self) -> None:
        ttk.Label(self.nav, text="WORKSPACE", style="Section.TLabel").pack(anchor="w", pady=(8, 8))
        items = [
            ("⌂  Dashboard", "dashboard"),
            ("◎  Research Graph", "graph"),
            ("▤  Entities", "entities"),
            ("▥  Paper Notes", "papers"),
            ("✓  Claim Ledger", "claims"),
            ("⚗  Experiment Notebook", "experiments"),
            ("⌘  Question Tree", "question_tree"),
            ("⌕  Search", "search"),
            ("◈  Timeline", "timeline"),
            ("☷  Daily Research Log", "daily"),
            ("⌘  Question Tree", "questions"),
            ("▣  Templates", "templates"),
        ]
        for label, name in items:
            ttk.Button(self.nav, text=label, command=lambda n=name: self.show_view(n)).pack(fill="x", pady=2)
        ttk.Separator(self.nav).pack(fill="x", pady=13)
        ttk.Label(self.nav, text="DATA", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Button(self.nav, text="↔  Add Relation", command=self.add_relation_dialog).pack(fill="x", pady=2)
        ttk.Button(self.nav, text="⇩  Export Archive", command=self.export_archive).pack(fill="x", pady=2)
        ttk.Button(self.nav, text="⟳  Backup Database", command=self.backup_database).pack(fill="x", pady=2)
        ttk.Button(self.nav, text="✓  Integrity Check", command=self.integrity_check).pack(fill="x", pady=2)
        ttk.Button(self.nav, text="↥  Restore Backup", command=self.restore_backup).pack(fill="x", pady=2)
        ttk.Separator(self.nav).pack(fill="x", pady=13)
        ttk.Label(self.nav, text="DATABASE", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(self.nav, textvariable=tk.StringVar(value=str(self.store.path)), style="Muted.TLabel", wraplength=190).pack(anchor="w", pady=(4, 0))

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def show_view(self, name: str) -> None:
        self.current_view = name
        self._clear_content()
        {
            "dashboard": self._show_dashboard,
            "graph": self._show_graph,
            "entities": self._show_entities,
            "papers": lambda: self._show_specialized("Paper"),
            "claims": lambda: self._show_specialized("Claim"),
            "experiments": lambda: self._show_specialized("Experiment"),
            "question_tree": self._show_question_tree,
            "search": self._show_search,
            "timeline": self._show_timeline,
            "daily": self._show_daily,
            "questions": self._show_question_tree,
            "templates": self._show_templates,
        }.get(name, self._show_dashboard)()

    def _show_dashboard(self) -> None:
        frame = ttk.Frame(self.content)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Research workspace", style="Title.TLabel").pack(anchor="w", pady=(16, 2))
        ttk.Label(frame, text="Trace every claim from source to evidence, experiment, result and next step.", style="Muted.TLabel").pack(anchor="w")
        stats = ttk.Frame(frame)
        stats.pack(fill="x", pady=22)
        entities = self.store.list_entities()
        relations = self.store.list_relations()
        counts = [("Entities", len(entities), "All structured research objects"), ("Relations", len(relations), "Traceable links between objects"),
                  ("Papers", sum(e.entity_type == "Paper" for e in entities), "Sources in your library"),
                  ("Open questions", sum(e.entity_type == "Question" for e in entities), "Questions awaiting evidence")]
        for label, value, note in counts:
            card = tk.Frame(stats, bg=PANEL_2, padx=18, pady=14)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(card, text=str(value), bg=PANEL_2, fg=ACCENT, font=("Segoe UI", 25, "bold")).pack(anchor="w")
            tk.Label(card, text=label.upper(), bg=PANEL_2, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(card, text=note, bg=PANEL_2, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        quick = ttk.Frame(frame)
        quick.pack(fill="x", pady=(0, 20))
        ttk.Label(quick, text="Start a research object", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        for typ in ("Paper", "Claim", "Question", "Hypothesis", "Experiment", "Result", "Idea", "Task"):
            ttk.Button(quick, text=f"＋ {typ}", command=lambda t=typ: self.new_entity(t)).pack(side="left", padx=(0, 7))
        lower = ttk.Frame(frame)
        lower.pack(fill="both", expand=True)
        recent_box = ttk.Frame(lower)
        recent_box.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(recent_box, text="Recent research activity", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        tree = self._entity_tree(recent_box, columns=("type", "title", "updated"), headings=("Type", "Title", "Updated"))
        tree.pack(fill="both", expand=True)
        for e in entities[:18]:
            tree.insert("", "end", iid=e.id, values=(e.entity_type, e.title or "(untitled)", (e.updated_at or "")[:19]))
        tree.bind("<Double-1>", lambda _event: self._open_tree_selection(tree))
        tips = tk.Frame(lower, bg=PANEL_2, padx=18, pady=18)
        tips.pack(side="left", fill="y")
        tk.Label(tips, text="RESEARCH TRACE", bg=PANEL_2, fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(tips, text="Paper → Claim → Evidence\nClaim → Hypothesis\nHypothesis → Experiment\nExperiment → Result\nResult → Decision → Next Step", bg=PANEL_2, fg=TEXT, justify="left", font=("Segoe UI", 10), pady=12).pack(anchor="w")
        ttk.Button(tips, text="Open graph", command=lambda: self.show_view("graph")).pack(anchor="w", pady=(8, 0))

    def _entity_tree(self, parent: tk.Misc, columns: tuple[str, ...], headings: tuple[str, ...]) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for col, heading in zip(columns, headings):
            tree.heading(col, text=heading)
            tree.column(col, width=180 if col != "title" else 360, anchor="w")
        return tree

    def _show_entities(self) -> None:
        outer = ttk.Frame(self.content)
        outer.pack(fill="both", expand=True)
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(12, 10))
        ttk.Label(toolbar, text="Entities", style="Title.TLabel").pack(side="left")
        type_var = tk.StringVar(value="All")
        ttk.Label(toolbar, text="Type", style="Muted.TLabel").pack(side="left", padx=(24, 5))
        type_box = ttk.Combobox(toolbar, textvariable=type_var, values=("All",) + ENTITY_TYPES, state="readonly", width=18)
        type_box.pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=lambda: fill()).pack(side="left", padx=6)
        ttk.Button(toolbar, text="＋ New", style="Accent.TButton", command=self.new_entity).pack(side="right")
        split = ttk.PanedWindow(outer, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=(0, 0, 10, 0)); right = ttk.Frame(split, padding=(10, 0, 0, 0))
        split.add(left, weight=3); split.add(right, weight=2)
        tree = self._entity_tree(left, columns=("type", "title", "updated"), headings=("Type", "Title", "Updated"))
        tree.pack(fill="both", expand=True)
        self._build_editor(right)

        def fill() -> None:
            tree.delete(*tree.get_children())
            for e in self.store.list_entities(type_var.get()):
                tree.insert("", "end", iid=e.id, values=(e.entity_type, e.title or "(untitled)", (e.updated_at or "")[:19]))

        def choose(_event: tk.Event) -> None:
            self.select_entity(tree.selection()[0] if tree.selection() else None)
            self._load_editor(self.current_entity)

        tree.bind("<<TreeviewSelect>>", choose)
        type_var.trace_add("write", lambda *_: fill())
        fill()

    def _build_editor(self, parent: tk.Misc) -> None:
        self.editor = ttk.Frame(parent)
        self.editor.pack(fill="both", expand=True)
        ttk.Label(self.editor, text="Entity details", style="Section.TLabel").pack(anchor="w", pady=(0, 9))
        self.edit_id_var = tk.StringVar(value="New entity")
        ttk.Label(self.editor, textvariable=self.edit_id_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.editor); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Type", width=12).pack(side="left")
        self.edit_type_var = tk.StringVar(value="Concept")
        ttk.Combobox(row, textvariable=self.edit_type_var, values=ENTITY_TYPES, state="readonly").pack(side="left", fill="x", expand=True)
        row = ttk.Frame(self.editor); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Title", width=12).pack(side="left")
        self.edit_title_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.edit_title_var).pack(side="left", fill="x", expand=True)
        ttk.Label(self.editor, text="Content / notes", style="Muted.TLabel").pack(anchor="w", pady=(10, 3))
        self.edit_content = tk.Text(self.editor, height=8, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", padx=8, pady=7)
        self.edit_content.pack(fill="both", expand=True)
        ttk.Label(self.editor, text="Structured data (JSON)", style="Muted.TLabel").pack(anchor="w", pady=(10, 3))
        self.edit_data = tk.Text(self.editor, height=6, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="none", padx=8, pady=7)
        self.edit_data.pack(fill="x")
        buttons = ttk.Frame(self.editor); buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="Save", style="Accent.TButton", command=self.save_entity).pack(side="left")
        ttk.Button(buttons, text="Clear", command=lambda: self._load_editor(None)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Link artifact", command=self.link_artifact).pack(side="left", padx=6)
        ttk.Button(buttons, text="Delete", command=self.delete_current).pack(side="right")
        self.backlink_label = ttk.Label(self.editor, text="Backlinks", style="Section.TLabel")
        self.backlink_label.pack(anchor="w", pady=(12, 5))
        self.backlinks_tree = ttk.Treeview(self.editor, columns=("relation", "entity"), show="headings", height=6)
        self.backlinks_tree.heading("relation", text="Relation"); self.backlinks_tree.heading("entity", text="Referenced by")
        self.backlinks_tree.column("relation", width=140); self.backlinks_tree.column("entity", width=260)
        self.backlinks_tree.pack(fill="x")
        self._backlink_entity_ids: dict[str, str] = {}
        self.backlinks_tree.bind("<Double-1>", self._open_backlink_selection)
        ttk.Label(self.editor, text="Create relation", style="Section.TLabel").pack(anchor="w", pady=(13, 5))
        relation_row = ttk.Frame(self.editor); relation_row.pack(fill="x", pady=2)
        ttk.Label(relation_row, text="Relation", width=12).pack(side="left")
        self.edit_relation_type_var = tk.StringVar(value="SUPPORTS")
        ttk.Combobox(relation_row, textvariable=self.edit_relation_type_var, values=RELATION_TYPES, state="readonly", width=20).pack(side="left", fill="x", expand=True)
        target_row = ttk.Frame(self.editor); target_row.pack(fill="x", pady=2)
        ttk.Label(target_row, text="Target", width=12).pack(side="left")
        self.edit_relation_target_var = tk.StringVar()
        self.edit_relation_targets: dict[str, str] = {}
        self.edit_relation_target_box = ttk.Combobox(target_row, textvariable=self.edit_relation_target_var, state="readonly")
        self.edit_relation_target_box.pack(side="left", fill="x", expand=True)
        ttk.Button(target_row, text="Add", command=self.add_relation).pack(side="left", padx=(6, 0))
        self.outgoing_tree = ttk.Treeview(self.editor, columns=("relation", "target"), show="headings", height=5)
        self.outgoing_tree.heading("relation", text="Relation"); self.outgoing_tree.heading("target", text="Outgoing target")
        self.outgoing_tree.column("relation", width=140); self.outgoing_tree.column("target", width=260)
        self.outgoing_tree.pack(fill="x", pady=(5, 0))
        ttk.Button(self.editor, text="Delete selected relation", command=self.delete_selected_relation).pack(anchor="e", pady=(4, 0))

    def _load_editor(self, entity: Entity | None) -> None:
        self.current_entity = entity
        self.edit_id_var.set(entity.id if entity and entity.id else "New entity")
        self.edit_type_var.set(entity.entity_type if entity else "Concept")
        self.edit_title_var.set(entity.title if entity else "")
        self.edit_content.delete("1.0", "end")
        self.edit_content.insert("1.0", entity.content if entity else "")
        self.edit_data.delete("1.0", "end")
        self.edit_data.insert("1.0", json.dumps(entity.data if entity else {}, ensure_ascii=False, indent=2))
        if hasattr(self, "backlinks_tree"):
            self.backlinks_tree.delete(*self.backlinks_tree.get_children())
            self.outgoing_tree.delete(*self.outgoing_tree.get_children())
            self.edit_relation_targets.clear()
            self._backlink_entity_ids.clear()
            if entity and entity.id:
                for index, (source, relation) in enumerate(self.store.backlinks(entity.id)):
                    row_id = f"back:{relation.id or source.id}:{index}"
                    self._backlink_entity_ids[row_id] = source.id or ""
                    self.backlinks_tree.insert("", "end", iid=row_id, values=(relation.relation_type, source.title or source.entity_type))
                relation_rows = []
                for relation in self.store.list_relations(entity.id):
                    if relation.source_id != entity.id:
                        continue
                    target = self.store.get_entity(relation.target_id)
                    if target:
                        relation_rows.append((relation, target))
                        self.outgoing_tree.insert("", "end", iid=relation.id, values=(relation.relation_type, target.title or target.entity_type))
            else:
                relation_rows = []
            all_targets = [item for item in self.store.list_entities() if item.id and (not entity or item.id != entity.id)]
            labels = []
            for item in all_targets:
                label = f"{item.title or '(untitled)'} · {item.entity_type} · {item.id}"
                self.edit_relation_targets[label] = item.id
                labels.append(label)
            self.edit_relation_target_box["values"] = labels
            if labels:
                self.edit_relation_target_var.set(labels[0])

    def _open_backlink_selection(self, _event: tk.Event) -> None:
        selected = self.backlinks_tree.selection() if hasattr(self, "backlinks_tree") else ()
        if selected:
            self.select_entity(self._backlink_entity_ids.get(selected[0], selected[0]))

    def add_relation(self) -> None:
        if not self.current_entity or not self.current_entity.id:
            messagebox.showinfo("Relation", "Save the entity before adding a relation.", parent=self)
            return
        target_id = self.edit_relation_targets.get(self.edit_relation_target_var.get())
        if not target_id:
            messagebox.showinfo("Relation", "Choose a target entity.", parent=self)
            return
        try:
            self.store.create_relation(Relation(source_id=self.current_entity.id, relation_type=self.edit_relation_type_var.get(), target_id=target_id))
            self.status_var.set(f"Added {self.edit_relation_type_var.get()} relation")
            self._load_editor(self.store.get_entity(self.current_entity.id))
        except Exception as exc:
            messagebox.showerror("Relation failed", str(exc), parent=self)

    def delete_selected_relation(self) -> None:
        selected = self.outgoing_tree.selection() if hasattr(self, "outgoing_tree") else ()
        if not selected:
            return
        if not messagebox.askyesno("Delete relation", "Delete the selected relation?", parent=self):
            return
        try:
            self.store.delete_relation(selected[0])
            self._load_editor(self.current_entity)
            self.status_var.set("Relation deleted")
        except Exception as exc:
            messagebox.showerror("Relation failed", str(exc), parent=self)

    def select_entity(self, entity_id: str | None) -> None:
        if not entity_id:
            return
        entity = self.store.get_entity(entity_id)
        if entity:
            self.current_entity = entity
            self.status_var.set(f"Selected {entity.entity_type}: {entity.title}")
            if hasattr(self, "edit_title_var"):
                self._load_editor(entity)

    def new_entity(self, entity_type: str = "Concept") -> None:
        if self.current_view != "entities":
            self.show_view("entities")
        self._load_editor(Entity(entity_type=entity_type, title=""))
        try:
            self.edit_title_var.focus_set()
        except Exception:
            pass

    def save_entity(self) -> None:
        try:
            data = json.loads(self.edit_data.get("1.0", "end").strip() or "{}")
            if not isinstance(data, dict):
                raise ValueError("Structured data must be a JSON object")
        except Exception as exc:
            messagebox.showerror("Invalid JSON", str(exc), parent=self)
            return
        value = Entity(entity_type=self.edit_type_var.get(), title=self.edit_title_var.get().strip(),
                       content=self.edit_content.get("1.0", "end").strip(), data=data,
                       id=(self.current_entity.id if self.current_entity and self.current_entity.id else None),
                       created_at=(self.current_entity.created_at if self.current_entity else None),
                       version=(self.current_entity.version if self.current_entity else 1))
        try:
            saved = self.store.update_entity(value) if value.id else self.store.create_entity(value)
            self.current_entity = saved
            self.status_var.set(f"Saved {saved.entity_type}: {saved.title}")
            if self.current_view == "entities":
                self.show_view("entities")
                self.select_entity(saved.id)
            else:
                self.show_view(self.current_view)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)

    def delete_current(self) -> None:
        if not self.current_entity or not self.current_entity.id:
            return
        if not messagebox.askyesno("Delete entity", "Move this entity to the deleted state?", parent=self):
            return
        self.store.delete_entity(self.current_entity.id)
        self.current_entity = None
        self.status_var.set("Entity deleted")
        self.show_view(self.current_view)

    def link_artifact(self) -> None:
        """Attach one or more local files/directories to the current entity."""
        if not self.current_entity or not self.current_entity.id:
            messagebox.showinfo("Artifact", "Save the entity before linking an artifact.", parent=self)
            return
        selected = filedialog.askopenfilename(parent=self, title="Choose a local artifact (Cancel to choose a folder)")
        if not selected:
            selected = filedialog.askdirectory(parent=self, title="Choose a local artifact folder")
        if not selected:
            return
        data = dict(self.current_entity.data or {})
        paths = list(data.get("artifact_paths", [])) if isinstance(data.get("artifact_paths", []), list) else []
        if selected not in paths:
            paths.append(selected)
        # When the richer service layer is present, create a first-class
        # Artifact node and DOCUMENTS edge so the file is visible in the
        # research graph rather than living only as an opaque JSON path.
        artifact = None
        try:
            from .services import ResearchService

            artifact = ResearchService(self.store.backend).link_artifact(
                self.current_entity.id,
                selected,
                kind="directory" if Path(selected).is_dir() else "file",
            )
            ids = list(data.get("artifact_ids", [])) if isinstance(data.get("artifact_ids", []), list) else []
            if artifact.id and artifact.id not in ids:
                ids.append(artifact.id)
            data["artifact_ids"] = ids
        except Exception:
            # Custom/fallback stores may not implement the service contract;
            # retaining the path still provides a useful portable link.
            pass
        data["artifact_paths"] = paths
        self.current_entity = self.store.update_entity(Entity(
            id=self.current_entity.id,
            entity_type=self.current_entity.entity_type,
            title=self.current_entity.title,
            content=self.current_entity.content,
            data=data,
            created_at=self.current_entity.created_at,
            version=self.current_entity.version,
        ))
        self._load_editor(self.current_entity)
        self.status_var.set(f"Linked artifact: {Path(selected).name}" + (f" ({artifact.id})" if artifact and artifact.id else ""))

    def _show_graph(self) -> None:
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        toolbar = ttk.Frame(outer); toolbar.pack(fill="x", pady=(12, 8))
        ttk.Label(toolbar, text="Research Graph", style="Title.TLabel").pack(side="left")
        ttk.Label(toolbar, text="Scroll to zoom · drag nodes · middle-drag to pan", style="Muted.TLabel").pack(side="left", padx=18)
        type_vars: dict[str, tk.BooleanVar] = {t: tk.BooleanVar(value=True) for t in ENTITY_TYPES}
        relation_var = tk.StringVar()
        ttk.Label(toolbar, text="Relation", style="Muted.TLabel").pack(side="left", padx=(8, 4))
        ttk.Entry(toolbar, textvariable=relation_var, width=17).pack(side="left")
        canvas = GraphCanvas(outer, self); canvas.pack(fill="both", expand=True)
        controls = ttk.Frame(outer); controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Reset layout", command=lambda: load(True)).pack(side="left")
        ttk.Button(controls, text="Expand selected neighbors", command=lambda: expand()).pack(side="left", padx=6)
        ttk.Button(controls, text="Open selected", command=lambda: self._open_graph_selected(canvas)).pack(side="left")
        filter_frame = ttk.Frame(outer); filter_frame.pack(fill="x", pady=(7, 0))
        ttk.Label(filter_frame, text="Visible types:", style="Muted.TLabel").pack(side="left")
        for t, var in type_vars.items():
            ttk.Checkbutton(filter_frame, text=t, variable=var, command=lambda: load(False)).pack(side="left", padx=2)

        def load(reset: bool = False) -> None:
            entities, relations = self.store.graph()
            allowed = {t for t, var in type_vars.items() if var.get()}
            filtered = [e for e in entities if e.entity_type in allowed]
            ids = {e.id for e in filtered}
            relation_text = relation_var.get().strip().lower()
            filtered_relations = [r for r in relations if r.source_id in ids and r.target_id in ids and (not relation_text or relation_text in r.relation_type.lower())]
            canvas.set_graph(filtered, filtered_relations, reset=reset)
            self.status_var.set(f"Graph: {len(filtered)} nodes · {len(filtered_relations)} relations")

        def expand() -> None:
            if not canvas.selected:
                messagebox.showinfo("Graph", "Select a node first.", parent=self); return
            neighbors = self.store.neighbors(canvas.selected)
            current = {e.id for e in canvas.entities}
            canvas.set_graph(canvas.entities + [e for e in neighbors if e.id not in current], self.store.list_relations(), reset=False)

        relation_var.trace_add("write", lambda *_: load(False))
        self._graph_canvas = canvas
        load(True)

    def _open_graph_selected(self, canvas: GraphCanvas) -> None:
        if canvas.selected:
            self.current_entity = self.store.get_entity(canvas.selected)
            self.show_view("entities")
            self._load_editor(self.current_entity)

    def _show_specialized(self, entity_type: str) -> None:
        """Render a domain-specific notebook while keeping one graph model.

        The three high-frequency research workflows have named fields, but
        they still save into the same typed ``Entity.data`` JSON object.  This
        avoids the common failure mode where a pretty notebook becomes a
        disconnected second database.
        """
        specs: dict[str, tuple[str, str, tuple[str, ...]]] = {
            "Paper": (
                "Paper Notes",
                "Summary · key claims · methods · results · limitations · questions · related papers",
                ("summary", "key_claims", "methods", "results", "limitations", "questions", "related_papers"),
            ),
            "Claim": (
                "Claim Ledger",
                "A traceable ledger: source, evidence, confidence, contradicting evidence and status.",
                ("source", "evidence", "confidence", "contradicting_evidence", "status"),
            ),
            "Experiment": (
                "Experiment Notebook",
                "Question · hypothesis · method · configuration · dataset · code · runs · results · interpretation · limitations · next step",
                ("question", "hypothesis", "method", "configuration", "dataset", "code", "runs", "results", "interpretation", "limitations", "next_step"),
            ),
        }
        title, subtitle, fields = specs[entity_type]
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        toolbar = ttk.Frame(outer); toolbar.pack(fill="x", pady=(12, 10))
        ttk.Label(toolbar, text=title, style="Title.TLabel").pack(side="left")
        ttk.Label(toolbar, text=subtitle, style="Muted.TLabel", wraplength=720).pack(side="left", padx=18)
        ttk.Button(toolbar, text=f"＋ New {entity_type}", style="Accent.TButton", command=lambda: self._start_specialized_new(entity_type)).pack(side="right")
        split = ttk.PanedWindow(outer, orient="horizontal"); split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=(0, 0, 10, 0)); right = ttk.Frame(split, padding=(10, 0, 0, 0))
        split.add(left, weight=2); split.add(right, weight=3)
        tree = self._entity_tree(left, columns=("title", "status", "updated"), headings=("Title", "Status", "Updated"))
        tree.column("title", width=300); tree.column("status", width=140); tree.pack(fill="both", expand=True)
        editor = ttk.Frame(right); editor.pack(fill="both", expand=True)
        ttk.Label(editor, text="Structured record", style="Section.TLabel").pack(anchor="w", pady=(0, 7))
        title_var = tk.StringVar(); ttk.Entry(editor, textvariable=title_var).pack(fill="x", pady=(0, 6))
        fields_frame = ttk.Frame(editor); fields_frame.pack(fill="both", expand=True)
        widgets: dict[str, tk.Text] = {}
        for field in fields:
            row = ttk.Frame(fields_frame); row.pack(fill="x", pady=2)
            label = field.replace("_", " ").title()
            ttk.Label(row, text=label, width=22).pack(side="left", anchor="n")
            text = tk.Text(row, height=2 if field not in {"summary", "methods", "results", "evidence", "configuration", "interpretation"} else 4,
                           bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", padx=6, pady=4)
            text.pack(side="left", fill="x", expand=True); widgets[field] = text
        action = ttk.Frame(editor); action.pack(fill="x", pady=8)
        ttk.Button(action, text="Save structured record", style="Accent.TButton", command=lambda: save()).pack(side="left")
        ttk.Button(action, text="Open full entity editor", command=lambda: open_full()).pack(side="left", padx=6)
        ttk.Label(editor, text="Relations and backlinks remain available in the full entity editor and graph.", style="Muted.TLabel").pack(anchor="w")
        selected: Entity | None = None

        def load_list() -> None:
            tree.delete(*tree.get_children())
            for item in self.store.list_entities(entity_type):
                status = str(item.data.get("status", "")) if isinstance(item.data, dict) else ""
                tree.insert("", "end", iid=item.id, values=(item.title or "(untitled)", status, (item.updated_at or "")[:19]))

        def load_item(item: Entity | None) -> None:
            nonlocal selected
            selected = item
            title_var.set(item.title if item else "")
            for field, widget in widgets.items():
                widget.delete("1.0", "end")
                value = (item.data.get(field, "") if item and isinstance(item.data, dict) else "")
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, indent=2)
                widget.insert("1.0", str(value))

        def choose(_event: tk.Event) -> None:
            ids = tree.selection(); load_item(self.store.get_entity(ids[0]) if ids else None)

        def save() -> None:
            nonlocal selected
            data: dict[str, Any] = {}
            for field, widget in widgets.items():
                raw = widget.get("1.0", "end").strip()
                if field in {"key_claims", "questions", "related_papers", "runs", "contradicting_evidence"}:
                    try:
                        data[field] = json.loads(raw) if raw else []
                    except json.JSONDecodeError:
                        data[field] = [line.strip() for line in raw.splitlines() if line.strip()]
                elif field in {"confidence"}:
                    try: data[field] = float(raw) if raw else None
                    except ValueError: data[field] = raw
                elif field in {"configuration"}:
                    try: data[field] = json.loads(raw) if raw else {}
                    except json.JSONDecodeError: data[field] = {"text": raw}
                else:
                    data[field] = raw
            item = Entity(entity_type=entity_type, title=title_var.get().strip(), data=data,
                          content=(data.get("summary") or data.get("interpretation") or data.get("evidence") or ""),
                          id=selected.id if selected else None,
                          created_at=selected.created_at if selected else None,
                          version=selected.version if selected else 1)
            try:
                selected = self.store.update_entity(item) if item.id else self.store.create_entity(item)
                self.status_var.set(f"Saved {title}: {selected.title}"); load_list(); load_item(selected)
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc), parent=self)

        def open_full() -> None:
            if selected:
                self.current_entity = selected; self.show_view("entities"); self._load_editor(selected)

        def _new() -> None:
            load_item(Entity(entity_type=entity_type, title="", data={field: [] if field in {"key_claims", "questions", "related_papers", "runs", "contradicting_evidence"} else {} if field == "configuration" else "" for field in fields}))

        tree.bind("<<TreeviewSelect>>", choose)
        load_list()
        # The toolbar can rebuild the view before asking the fresh widgets to
        # accept a new record; retaining this closure avoids writing to widgets
        # that were destroyed during the rebuild.
        self._specialized_new_callback = _new

    def _start_specialized_new(self, entity_type: str) -> None:
        view = "papers" if entity_type == "Paper" else "claims" if entity_type == "Claim" else "experiments"
        self.show_view(view)
        callback = getattr(self, "_specialized_new_callback", None)
        if callback:
            callback()

    def _show_search(self) -> None:
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        toolbar = ttk.Frame(outer); toolbar.pack(fill="x", pady=(12, 10))
        ttk.Label(toolbar, text="Search research graph", style="Title.TLabel").pack(side="left")
        query = tk.StringVar(); ttk.Entry(toolbar, textvariable=query, width=46).pack(side="left", padx=18)
        type_var = tk.StringVar(value="All"); ttk.Combobox(toolbar, textvariable=type_var, values=("All",) + ENTITY_TYPES, state="readonly", width=15).pack(side="left")
        ttk.Button(toolbar, text="Search", style="Accent.TButton", command=lambda: run()).pack(side="left", padx=7)
        result = self._entity_tree(outer, columns=("type", "title", "snippet", "updated"), headings=("Type", "Title", "Match", "Updated"))
        result.column("snippet", width=430)
        result.pack(fill="both", expand=True)
        result.bind("<Double-1>", lambda _e: self._open_tree_selection(result))
        query.bind if False else None
        query.trace_add("write", lambda *_: run())

        def run() -> None:
            result.delete(*result.get_children())
            text = query.get().strip()
            if not text:
                hits = self.store.list_entities(type_var.get())[:100]
            else:
                hits = self.store.search(text, type_var.get())[:100]
            for e in hits:
                hay = (e.content + " " + json.dumps(e.data, ensure_ascii=False)).replace("\n", " ")
                result.insert("", "end", iid=e.id, values=(e.entity_type, e.title or "(untitled)", hay[:120], (e.updated_at or "")[:19]))

        type_var.trace_add("write", lambda *_: run())

    def _open_tree_selection(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if selected:
            self.current_entity = self.store.get_entity(selected[0])
            self.show_view("entities")
            self._load_editor(self.current_entity)

    def _show_timeline(self) -> None:
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Research Timeline", style="Title.TLabel").pack(anchor="w", pady=(12, 3))
        ttk.Label(outer, text="See when ideas appeared, experiments ran, and claims changed status.", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(outer, columns=("date", "type", "title", "status"), show="headings")
        for c, h, w in (("date", "When", 180), ("type", "Type", 130), ("title", "Research object", 410), ("status", "Status / next step", 360)):
            tree.heading(c, text=h); tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True)
        timeline_rows: list[tuple[str, str, str, str, str, str]] = []
        for entity in self.store.list_entities():
            status = str(entity.data.get("status", entity.data.get("next_step", ""))) if isinstance(entity.data, dict) else ""
            timeline_rows.append((entity.created_at or "", entity.id or "", entity.entity_type, entity.title, status, "entity"))
        for event in self.store.list_timeline(limit=200):
            event_id = str(event.get("id", ""))
            if not event_id:
                continue
            linked = self.store.get_entity(str(event.get("entity_id"))) if event.get("entity_id") else None
            timeline_rows.append((str(event.get("occurred_at", "")), f"event:{event_id}", str(event.get("event_type", "EVENT")), str(event.get("title", "")), linked.title if linked else "", "event"))
        for occurred, row_id, typ, title_text, status, row_kind in sorted(timeline_rows, key=lambda row: row[0], reverse=True):
            tree.insert("", "end", iid=row_id, values=(occurred[:19], typ, title_text, status))

        def open_timeline_item(_event: tk.Event) -> None:
            selected = tree.selection()
            if not selected:
                return
            iid = selected[0]
            if iid.startswith("event:"):
                values = tree.item(iid, "values")
                self.status_var.set(f"Timeline event: {values[1]} — {values[2]}")
            else:
                self._open_tree_selection(tree)

        tree.bind("<Double-1>", open_timeline_item)

    def _show_question_tree(self) -> None:
        """Show research questions as a navigable decomposition tree."""
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Research Question Tree", style="Title.TLabel").pack(anchor="w", pady=(12, 3))
        ttk.Label(outer, text="Question → sub-question → hypothesis → experiment; links are explicit graph relations.", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(outer, columns=("type", "status", "id"), show="tree headings")
        tree.heading("#0", text="Research thread")
        tree.heading("type", text="Type"); tree.heading("status", text="Status"); tree.heading("id", text="ID")
        tree.column("#0", width=560); tree.column("type", width=130); tree.column("status", width=160); tree.column("id", width=220)
        tree.pack(fill="both", expand=True)
        entities = {e.id: e for e in self.store.list_entities() if e.id}
        relations = self.store.list_relations()
        outgoing: dict[str, list[tuple[str, Relation]]] = {}
        for relation in relations:
            if relation.source_id in entities and relation.target_id in entities:
                outgoing.setdefault(relation.source_id, []).append((relation.target_id, relation))
        roots = [e for e in entities.values() if e.entity_type == "Question"]
        visited: set[str] = set()

        def add_node(parent: str, entity_id: str, relation_label: str = "") -> None:
            if entity_id not in entities:
                return
            entity = entities[entity_id]
            if entity_id in visited:
                return
            visited.add(entity_id)
            status = str(entity.data.get("status", "")) if isinstance(entity.data, dict) else ""
            label = f"{relation_label}  {entity.title or '(untitled)'}" if relation_label else (entity.title or "(untitled)")
            iid = tree.insert(parent, "end", iid=f"qtree:{entity_id}", text=label, values=(entity.entity_type, status, entity.id))
            for child_id, relation in outgoing.get(entity_id, []):
                if relation.relation_type in {"SUBQUESTION_OF", "PART_OF", "MOTIVATES", "INSPIRES", "TESTED_BY", "NEXT_STEP", "FOLLOWS"}:
                    add_node(iid, child_id, relation.relation_type)

        for root in roots:
            add_node("", root.id)
        # Keep otherwise-unconnected nodes visible so a new question is never
        # mistaken for a lost record.
        for entity in entities.values():
            if entity.entity_type in {"Question", "Hypothesis", "Experiment"} and entity.id not in visited:
                add_node("", entity.id)
        tree.bind("<Double-1>", lambda _event: self._open_tree_selection_by_id(tree))

    def _open_tree_selection_by_id(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            return
        values = tree.item(selected[0], "values")
        if values:
            self.current_entity = self.store.get_entity(values[-1])
            self.show_view("entities")
            self._load_editor(self.current_entity)

    def _show_daily(self) -> None:
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Daily Research Log", style="Title.TLabel").pack(anchor="w", pady=(12, 3))
        ttk.Label(outer, text="Read · Built · Tested · Learned · Questions · Tomorrow", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        fields = [("Read", "read"), ("Built", "built"), ("Tested", "tested"), ("Learned", "learned"), ("Questions", "questions"), ("Tomorrow", "tomorrow")]
        vars_: dict[str, tk.Text] = {}
        for label, key in fields:
            row = ttk.Frame(outer); row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=12).pack(side="left", anchor="n")
            text = tk.Text(row, height=2, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
            text.pack(side="left", fill="x", expand=True); vars_[key] = text
        existing = self.store.get_daily_log(str(date.today()))
        if existing:
            for _key, _text in vars_.items():
                _text.insert("1.0", str(existing.data.get(_key, "")))
        ttk.Button(outer, text="Save today's log", style="Accent.TButton", command=lambda: save()).pack(anchor="w", pady=12)

        def save() -> None:
            payload = {key: text.get("1.0", "end").strip() for key, text in vars_.items()}
            saved = self.store.save_daily_log(str(date.today()), payload)
            self.status_var.set(f"Saved daily log {saved.title}")

    def _show_templates(self) -> None:
        outer = ttk.Frame(self.content); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Research Templates", style="Title.TLabel").pack(anchor="w", pady=(12, 3))
        ttk.Label(outer, text="Create a structured starting point; every template becomes an editable graph entity.", style="Muted.TLabel").pack(anchor="w", pady=(0, 14))
        templates = {
            "Paper Review": ("Paper", {"summary": "", "key_claims": [], "methods": "", "results": "", "limitations": "", "questions": []}),
            "Experiment": ("Experiment", {"question": "", "hypothesis": "", "method": "", "configuration": {}, "dataset": "", "code": "", "runs": [], "results": "", "interpretation": "", "limitations": "", "next_step": ""}),
            "Replication": ("Experiment", {"template": "replication", "source_paper": "", "baseline": "", "deviations": [], "result": "", "next_step": ""}),
            "Idea": ("Idea", {"origin": "", "motivation": "", "testable_question": "", "next_step": ""}),
            "Weekly Review": ("DailyLog", {"week": "", "wins": [], "blocked": [], "learned": [], "next_week": []}),
            "Research Question": ("Question", {"scope": "", "sub_questions": [], "success_criteria": ""}),
        }
        for name, (typ, data) in templates.items():
            card = tk.Frame(outer, bg=PANEL_2, padx=16, pady=12); card.pack(fill="x", pady=4)
            tk.Label(card, text=name, bg=PANEL_2, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
            tk.Label(card, text=typ, bg=PANEL_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=15)
            ttk.Button(card, text="Use template", command=lambda t=typ, d=data, n=name: self._use_template(t, d, n)).pack(side="right")

    def _use_template(self, entity_type: str, data: dict[str, Any], name: str) -> None:
        self.show_view("entities")
        self._load_editor(Entity(entity_type=entity_type, title=name, data=data))

    def add_relation_dialog(self) -> None:
        """Create a typed edge without hiding it inside a note field."""
        entities = self.store.list_entities()
        if len(entities) < 2:
            messagebox.showinfo("Relation", "Create at least two entities first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Add research relation")
        dialog.configure(background=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        labels = [f"{e.entity_type} · {e.title or '(untitled)'} · {e.id}" for e in entities]
        by_label = dict(zip(labels, entities))
        ttk.Label(dialog, text="Source", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 5))
        source_var = tk.StringVar(value=labels[0])
        ttk.Combobox(dialog, textvariable=source_var, values=labels, state="readonly", width=72).grid(row=1, column=0, padx=16, pady=4)
        ttk.Label(dialog, text="Relation", style="Section.TLabel").grid(row=2, column=0, sticky="w", padx=16, pady=(10, 5))
        relation_var = tk.StringVar(value="SUPPORTS")
        ttk.Combobox(dialog, textvariable=relation_var, values=RELATION_TYPES, state="readonly", width=28).grid(row=3, column=0, sticky="w", padx=16, pady=4)
        ttk.Label(dialog, text="Target", style="Section.TLabel").grid(row=4, column=0, sticky="w", padx=16, pady=(10, 5))
        target_var = tk.StringVar(value=labels[1])
        ttk.Combobox(dialog, textvariable=target_var, values=labels, state="readonly", width=72).grid(row=5, column=0, padx=16, pady=4)
        ttk.Label(dialog, text="Metadata (optional JSON)", style="Muted.TLabel").grid(row=6, column=0, sticky="w", padx=16, pady=(10, 3))
        metadata = tk.Text(dialog, height=4, width=72, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT, relief="flat")
        metadata.insert("1.0", "{}")
        metadata.grid(row=7, column=0, padx=16, pady=4)

        def save() -> None:
            if source_var.get() == target_var.get():
                messagebox.showerror("Relation", "Source and target must be different entities.", parent=dialog)
                return
            try:
                parsed = json.loads(metadata.get("1.0", "end").strip() or "{}")
                if not isinstance(parsed, dict):
                    raise ValueError("metadata must be a JSON object")
                self.store.create_relation(Relation(
                    source_id=by_label[source_var.get()].id or "",
                    relation_type=relation_var.get(),
                    target_id=by_label[target_var.get()].id or "",
                    metadata=parsed,
                ))
                self.status_var.set(f"Added relation {relation_var.get()}")
                dialog.destroy()
                if self.current_view == "graph":
                    self.show_view("graph")
            except Exception as exc:
                messagebox.showerror("Relation failed", str(exc), parent=dialog)

        buttons = ttk.Frame(dialog)
        buttons.grid(row=8, column=0, sticky="e", padx=16, pady=14)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Create relation", style="Accent.TButton", command=save).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def export_archive(self) -> None:
        directory = filedialog.askdirectory(title="Choose export folder", parent=self)
        if not directory:
            return
        try:
            root = Path(directory)
            root.mkdir(parents=True, exist_ok=True)
            entities = self.store.list_entities(); relations = self.store.list_relations()
            graph_payload = {
                "format": "research-os-graph", "format_version": 1, "generated_at": _now(),
                "nodes": [e.to_dict() for e in entities], "edges": [r.to_dict() for r in relations],
                "entities": [e.to_dict() for e in entities], "relations": [r.to_dict() for r in relations],
            }
            # Keep a simple top-level graph JSON even when the production
            # exporter is not available; it is convenient for scripts and
            # remains human-readable.
            (root / "graph.json").write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with (root / "entities.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "entity_type", "title", "content", "data", "created_at", "updated_at", "version"))
                writer.writeheader()
                for e in entities:
                    writer.writerow({"id": e.id, "entity_type": e.entity_type, "title": e.title, "content": e.content, "data": json.dumps(e.data, ensure_ascii=False), "created_at": e.created_at, "updated_at": e.updated_at, "version": e.version})
            with (root / "relations.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "source_id", "relation_type", "target_id", "metadata", "created_at"))
                writer.writeheader()
                for r in relations:
                    writer.writerow({"id": r.id, "source_id": r.source_id, "relation_type": r.relation_type, "target_id": r.target_id, "metadata": json.dumps(r.metadata, ensure_ascii=False), "created_at": r.created_at})
            # Use the production exporter for the richer projections when it
            # is available; the explicit files above remain a compatibility
            # fallback for lightweight stores.
            backend_export = getattr(self.store.backend, "export_markdown", None)
            if callable(backend_export):
                backend_export(root / "markdown")
            backend_export = getattr(self.store.backend, "export_html", None)
            if callable(backend_export):
                backend_export(root / "report.html")
            md = ["# Research OS Archive", "", f"Exported: {_now()}", ""]
            for e in entities:
                md += [f"## {e.entity_type}: {e.title}", "", e.content, "", "```json", json.dumps(e.data, ensure_ascii=False, indent=2), "```", ""]
            (root / "README.md").write_text("\n".join(md), encoding="utf-8")
            # The durable exporter adds the canonical Markdown archive and
            # HTML report alongside the quick human-readable README above.
            formats = self.store.export_formats(root)
            self.status_var.set(f"Exported {len(entities)} entities to {root}")
            messagebox.showinfo("Export complete", "Archive written to:\n" + str(root) + "\n\n" + "\n".join(f"{key}: {value}" for key, value in formats.items()), parent=self)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)

    def backup_database(self) -> None:
        destination = filedialog.asksaveasfilename(parent=self, title="Save Research OS backup", defaultextension=".sqlite3", filetypes=(("SQLite backup", "*.sqlite3"), ("All files", "*.*")))
        if not destination:
            return
        try:
            self.store.backup(destination)
            self.status_var.set(f"Backup saved: {destination}")
            messagebox.showinfo("Backup complete", destination, parent=self)
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)

    def restore_backup(self) -> None:
        source = filedialog.askopenfilename(parent=self, title="Select Research OS backup", filetypes=(("SQLite backup", "*.sqlite3 *.db"), ("All files", "*.*")))
        if not source or not messagebox.askyesno("Restore backup", "Replace the current database with this backup?", parent=self):
            return
        try:
            self.store.restore(source)
            self.status_var.set("Backup restored")
            self.show_view(self.current_view)
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc), parent=self)

    def integrity_check(self) -> None:
        result = self.store.integrity_check()
        ok = str(result).lower() in {"ok", "true", "passed", "pass"} or "ok" in str(result).lower()
        self.status_var.set(f"Integrity: {result}")
        messagebox.showinfo("Database integrity", str(result), parent=self) if ok else messagebox.showwarning("Database integrity", str(result), parent=self)

    def _autosave_tick(self) -> None:
        # The store commits each mutation; this heartbeat gives a visible cue
        # and leaves room for future draft snapshots without blocking the UI.
        if self.winfo_exists():
            self.status_var.set(self.status_var.get() if self.status_var.get() else "Autosave ready")
            self.after(15000, self._autosave_tick)

    def _on_close(self) -> None:
        try:
            self.store.save()
            self.store.close()
        finally:
            self.destroy()


def main() -> None:
    """Launch the desktop app."""
    app = ResearchOSApp()
    app.mainloop()


__all__ = ["ResearchOSApp", "StoreFacade", "GraphCanvas", "main"]
