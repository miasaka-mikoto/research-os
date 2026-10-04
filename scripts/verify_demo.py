#!/usr/bin/env python3
"""Run deterministic end-to-end checks against the Research OS demo.

The command deliberately exercises the durable data path rather than a UI
smoke test.  It exits non-zero for a missing entity, relation, search result,
export, backup or integrity check so CI/build scripts cannot silently ship an
empty notes shell.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable


EXPECTED_COUNTS = {
    "Paper": 5,
    "Claim": 10,
    "Hypothesis": 3,
    "Experiment": 4,
}


def _ok_integrity(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.lower() in {"ok", "pass", "passed", "integrity ok", "true"}
    if isinstance(value, dict):
        status = value.get("status", value.get("ok", value.get("result")))
        return _ok_integrity(status)
    return bool(value) if value is not None else False


def _entities(store: Any) -> list[Any]:
    rows = store.list_entities()
    return list(rows or [])


def _relations(store: Any) -> list[Any]:
    rows = store.list_relations()
    return list(rows or [])


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _call_export(store: Any, method_name: str, path: Path) -> None:
    method = getattr(store, method_name, None)
    if method is None:
        raise AssertionError(f"missing export method: {method_name}")
    result = method(path)
    # Implementations may return the path or simply write it.  Either is fine,
    # but an explicitly returned path should also exist.
    returned = Path(result) if isinstance(result, (str, Path)) else None
    candidate = returned if returned and returned.exists() else path
    if not candidate.exists() or candidate.stat().st_size == 0:
        raise AssertionError(f"{method_name} produced no file")


def run_checks(workspace: Path | None = None) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from researchos.demo import seed_demo
    from researchos.storage import ResearchStore

    with tempfile.TemporaryDirectory(prefix="researchos-verify-") as temp_dir:
        root = Path(temp_dir)
        db_path = workspace if workspace is not None else root / "workspace.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        store = ResearchStore(db_path)
        try:
            seed_summary = seed_demo(store)
            rows = _entities(store)
            rels = _relations(store)
            type_counts = Counter(_field(row, "entity_type") for row in rows)
            for entity_type, expected in EXPECTED_COUNTS.items():
                actual = type_counts[entity_type]
                if actual != expected:
                    raise AssertionError(f"{entity_type}: expected {expected}, got {actual}")
            if len(rels) < 30:
                raise AssertionError(f"demo graph too small: {len(rels)} relations")

            # Search must index title/content/structured data, not just a UI
            # label.  Both terms are deliberately present in different fields.
            hits = list(store.search("episodic"))
            if not hits:
                raise AssertionError("full-text search returned no episodic hit")
            json_hits = list(store.search("horizon"))
            if not json_hits:
                raise AssertionError("full-text search returned no horizon hit")

            # Graph traversal and backlinks are separate durable operations.
            graph = store.graph("paper-001") if hasattr(store, "graph") else None
            if graph is not None:
                graph_text = json.dumps(graph, default=lambda obj: getattr(obj, "__dict__", str(obj)))
                if "claim-001" not in graph_text:
                    raise AssertionError("graph traversal omitted claim-001")
            neighbors = list(store.neighbors("paper-001")) if hasattr(store, "neighbors") else []
            if neighbors and not any(_field(n, "id") == "claim-001" for n in neighbors):
                raise AssertionError("neighbor expansion omitted claim-001")

            integrity = store.integrity_check()
            if not _ok_integrity(integrity):
                raise AssertionError(f"integrity check failed: {integrity!r}")

            export_dir = root / "exports"
            export_dir.mkdir()
            _call_export(store, "export_markdown", export_dir / "archive.md")
            _call_export(store, "export_html", export_dir / "report.html")
            _call_export(store, "export_graph_json", export_dir / "graph.json")
            _call_export(store, "export_csv", export_dir / "entities.csv")

            # SQLite online backup + restore should retain both entities and
            # relations.  Use a second store so an in-memory cache cannot mask
            # a broken backup.
            backup_path = root / "backups" / "demo.sqlite3"
            backup_path.parent.mkdir()
            backed = store.backup(backup_path)
            actual_backup = Path(backed) if isinstance(backed, (str, Path)) else backup_path
            if not actual_backup.exists() or actual_backup.stat().st_size == 0:
                raise AssertionError("backup file was not created")
            restored_path = root / "restored.sqlite3"
            restored = ResearchStore(restored_path)
            try:
                restored.restore(actual_backup)
                restored_rows = _entities(restored)
                restored_rels = _relations(restored)
                if len(restored_rows) != len(rows) or len(restored_rels) != len(rels):
                    raise AssertionError("backup/restore changed graph cardinality")
                if not _ok_integrity(restored.integrity_check()):
                    raise AssertionError("restored database integrity failed")
            finally:
                close = getattr(restored, "close", None)
                if close:
                    close()

            return {
                "status": "PASS",
                "entities": len(rows),
                "relations": len(rels),
                "type_counts": dict(type_counts),
                "seed": seed_summary,
            }
        finally:
            close = getattr(store, "close", None)
            if close:
                close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Optional explicit SQLite path")
    args = parser.parse_args(argv)
    try:
        report = run_checks(args.workspace)
    except Exception as exc:  # noqa: BLE001 - CLI must report every failed check
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
