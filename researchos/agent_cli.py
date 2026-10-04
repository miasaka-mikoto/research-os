"""Display-free JSON command line interface for Research OS.

The desktop shell is intentionally optional.  This module only imports the
SQLite domain layer, so it works on Linux servers, containers and cloud
computers without an X server or a Tk installation.  Every command writes one
JSON document to stdout and uses a non-zero exit code on failure, which makes
it safe for an automation agent to call and parse.

Examples::

    python -m researchos.agent_cli demo --workspace /tmp/research.sqlite3
    python -m researchos.agent_cli search episodic --workspace /tmp/research.sqlite3
    python -m researchos.agent_cli graph --entity paper-001 --depth 2 \
        --workspace /tmp/research.sqlite3
    python -m researchos.agent_cli export --output-dir /tmp/research-export \
        --workspace /tmp/research.sqlite3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Sequence


def default_workspace() -> Path:
    """Return a predictable per-user workspace path.

    ``RESEARCHOS_WORKSPACE`` is the most convenient setting for agents.  The
    older ``RESEARCHOS_HOME`` setting remains supported by the desktop app.
    Unlike the GUI, the CLI never assumes a current working directory is
    writable when a user-level path is available.
    """

    explicit = os.environ.get("RESEARCHOS_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("RESEARCHOS_HOME")
    if home:
        return Path(home).expanduser() / "researchos.sqlite3"
    return Path.home() / "ResearchOS" / "researchos.sqlite3"


def _json_dump(value: Any, *, pretty: bool = True) -> None:
    kwargs: dict[str, Any] = {
        "ensure_ascii": False,
        "sort_keys": True,
        "default": str,
    }
    if pretty:
        kwargs["indent"] = 2
    print(json.dumps(value, **kwargs))


def _workspace_from_args(args: argparse.Namespace) -> Path:
    value = getattr(args, "workspace", None)
    return Path(value).expanduser() if value else default_workspace()


def _open_store(workspace: Path):
    # Importing this module is deliberately Tk-free.  A neighbouring backup
    # directory gives agent workflows safe, explicit recovery points without
    # needing a separate configuration file.
    from .storage import ResearchStore

    workspace = workspace.expanduser()
    backup_dir = workspace.parent / "backups"
    return ResearchStore(workspace, backup_dir=backup_dir)


def _entity_dict(entity: Any) -> dict[str, Any]:
    if hasattr(entity, "to_dict"):
        return dict(entity.to_dict())
    if isinstance(entity, dict):
        return dict(entity)
    return dict(vars(entity))


def _relation_dict(relation: Any) -> dict[str, Any]:
    if hasattr(relation, "to_dict"):
        return dict(relation.to_dict())
    if isinstance(relation, dict):
        return dict(relation)
    return dict(vars(relation))


def _close(store: Any) -> None:
    close = getattr(store, "close", None)
    if close:
        close()


def _integrity_report(store: Any) -> dict[str, Any]:
    report = store.integrity_check()
    return dict(report) if isinstance(report, dict) else {"ok": bool(report), "result": report}


def _run_init(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        integrity = _integrity_report(store)
        return {
            "status": "ok",
            "command": "init",
            "workspace": str(workspace.resolve()),
            "schema_version": integrity.get("schema_version"),
            "counts": integrity.get("counts", {}),
        }
    finally:
        _close(store)


def _run_demo(args: argparse.Namespace) -> dict[str, Any]:
    from .demo import seed_demo

    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        summary = seed_demo(store)
        integrity = _integrity_report(store)
        if not integrity.get("ok", False):
            raise RuntimeError(f"database integrity check failed: {integrity}")
        return {
            "status": "ok",
            "command": "demo",
            "workspace": str(workspace.resolve()),
            "seed": summary,
            "integrity": integrity,
        }
    finally:
        _close(store)


def _run_stats(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        entities = store.list_entities()
        relations = store.list_relations()
        return {
            "status": "ok",
            "command": "stats",
            "workspace": str(workspace.resolve()),
            "entities": len(entities),
            "relations": len(relations),
            "entities_by_type": dict(sorted(Counter(e.entity_type for e in entities).items())),
            "relations_by_type": dict(sorted(Counter(r.relation_type for r in relations).items())),
            "integrity": _integrity_report(store),
        }
    finally:
        _close(store)


def _run_search(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        hits = store.search(args.query, entity_type=args.entity_type, limit=args.limit)
        return {
            "status": "ok",
            "command": "search",
            "workspace": str(workspace.resolve()),
            "query": args.query,
            "count": len(hits),
            "hits": [_entity_dict(hit) for hit in hits],
        }
    finally:
        _close(store)


def _run_graph(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        graph = store.graph(
            args.entity,
            entity_type=args.entity_type,
            relation_type=args.relation_type,
            depth=args.depth,
        )
        result = dict(graph)
        result.update({"status": "ok", "command": "graph", "workspace": str(workspace.resolve())})
        return result
    finally:
        _close(store)


def _run_neighbors(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        rows = store.neighbors(
            args.entity_id,
            direction=args.direction,
            relation_type=args.relation_type,
            depth=args.depth,
        )
        return {
            "status": "ok",
            "command": "neighbors",
            "workspace": str(workspace.resolve()),
            "entity_id": args.entity_id,
            "count": len(rows),
            "neighbors": rows,
        }
    finally:
        _close(store)


def _run_backlinks(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        backlinks = store.backlinks(args.entity_id, relation_type=args.relation_type)
        outlinks = store.outlinks(args.entity_id, relation_type=args.relation_type)
        return {
            "status": "ok",
            "command": "backlinks",
            "workspace": str(workspace.resolve()),
            "entity_id": args.entity_id,
            "backlinks": backlinks,
            "outlinks": outlinks,
        }
    finally:
        _close(store)


def _run_integrity(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        integrity = _integrity_report(store)
        return {
            "status": "ok" if integrity.get("ok") else "fail",
            "command": "integrity",
            "workspace": str(workspace.resolve()),
            "integrity": integrity,
        }
    finally:
        _close(store)


def _run_verify(args: argparse.Namespace) -> dict[str, Any]:
    """Verify an existing workspace without importing the desktop UI."""

    from .demo import seed_demo

    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        # Seeding is idempotent and ensures a fresh cloud workspace can be
        # verified with one command.  It also exercises the exact mutations
        # used by the packaged demo path.
        seed = seed_demo(store)
        entities = store.list_entities()
        relations = store.list_relations()
        hits = store.search("episodic")
        graph = store.graph("paper-001")
        integrity = _integrity_report(store)
        if len([e for e in entities if e.entity_type == "Paper"]) != 5:
            raise RuntimeError("demo verification expected 5 Paper entities")
        if len([e for e in entities if e.entity_type == "Claim"]) != 10:
            raise RuntimeError("demo verification expected 10 Claim entities")
        if len([e for e in entities if e.entity_type == "Hypothesis"]) != 3:
            raise RuntimeError("demo verification expected 3 Hypothesis entities")
        if len([e for e in entities if e.entity_type == "Experiment"]) != 4:
            raise RuntimeError("demo verification expected 4 Experiment entities")
        if len(relations) < 30 or not hits or "claim-001" not in json.dumps(graph, ensure_ascii=False):
            raise RuntimeError("demo verification graph/search checks failed")
        if not integrity.get("ok"):
            raise RuntimeError(f"demo verification integrity check failed: {integrity}")
        return {
            "status": "PASS",
            "command": "verify",
            "workspace": str(workspace.resolve()),
            "entities": len(entities),
            "relations": len(relations),
            "seed": seed,
            "search_hits": len(hits),
            "graph": {"nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", []))},
            "integrity": integrity,
        }
    finally:
        _close(store)


def _run_export(args: argparse.Namespace) -> dict[str, Any]:
    from .exporter import ResearchExporter

    workspace = _workspace_from_args(args)
    destination = Path(args.output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    store = _open_store(workspace)
    try:
        exporter = ResearchExporter(store)
        paths = {
            "markdown": store.export_markdown(destination / "archive.md"),
            "html": store.export_html(destination / "report.html"),
            "graph_json": store.export_graph_json(destination / "graph.json"),
            "csv": store.export_csv(destination / "entities.csv"),
            "relations_csv": exporter.relations_csv(destination / "relations.csv"),
        }
        return {
            "status": "ok",
            "command": "export",
            "workspace": str(workspace.resolve()),
            "output_dir": str(destination.resolve()),
            "files": {key: str(Path(value).resolve()) for key, value in paths.items()},
        }
    finally:
        _close(store)


def _run_backup(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    destination = Path(args.destination).expanduser() if args.destination else None
    store = _open_store(workspace)
    try:
        result = Path(store.backup(destination))
        return {
            "status": "ok",
            "command": "backup",
            "workspace": str(workspace.resolve()),
            "backup": str(result.resolve()),
            "bytes": result.stat().st_size,
        }
    finally:
        _close(store)


def _run_restore(args: argparse.Namespace) -> dict[str, Any]:
    from .storage import ResearchStore

    source = Path(args.source).expanduser()
    destination = Path(args.destination).expanduser()
    restored = ResearchStore.restore_to(source, destination, replace=args.replace)
    try:
        integrity = _integrity_report(restored)
        return {
            "status": "ok" if integrity.get("ok") else "fail",
            "command": "restore",
            "source": str(source.resolve()),
            "workspace": str(destination.resolve()),
            "integrity": integrity,
        }
    finally:
        _close(restored)


def _run_timeline(args: argparse.Namespace) -> dict[str, Any]:
    workspace = _workspace_from_args(args)
    store = _open_store(workspace)
    try:
        events = store.list_timeline(entity_id=args.entity_id, event_type=args.event_type, limit=args.limit)
        return {
            "status": "ok",
            "command": "timeline",
            "workspace": str(workspace.resolve()),
            "count": len(events),
            "events": events,
        }
    finally:
        _close(store)


def _add_workspace_option(parser: argparse.ArgumentParser) -> None:
    # SUPPRESS prevents a subcommand's default from overwriting a global
    # --workspace supplied before the subcommand.
    parser.add_argument("--workspace", type=Path, default=argparse.SUPPRESS, help="SQLite workspace path")
    parser.add_argument("--compact", action="store_true", default=argparse.SUPPRESS, help="emit one-line JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchos-agent", description=__doc__)
    parser.add_argument("--workspace", type=Path, default=None, help="SQLite workspace path")
    parser.add_argument("--compact", action="store_true", help="emit one-line JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, handler: Callable[[argparse.Namespace], dict[str, Any]], help_text: str):
        child = sub.add_parser(name, help=help_text)
        _add_workspace_option(child)
        child.set_defaults(handler=handler)
        return child

    command("init", _run_init, "create/open a workspace and report schema status")
    command("demo", _run_demo, "seed the fictional Agent Memory Research Demo")
    command("stats", _run_stats, "report entity/relation counts")
    search = command("search", _run_search, "full-text search across structured entities")
    search.add_argument("query")
    search.add_argument("--type", dest="entity_type", help="filter by entity type")
    search.add_argument("--limit", type=int, default=50)
    graph = command("graph", _run_graph, "return graph nodes and edges as JSON")
    graph.add_argument("--entity", action="append", default=None, help="seed entity ID; repeat for multiple seeds")
    graph.add_argument("--depth", type=int, default=None, help="neighbour expansion depth")
    graph.add_argument("--type", dest="entity_type", help="filter by entity type")
    graph.add_argument("--relation", dest="relation_type", help="filter by relation type")
    neighbors = command("neighbors", _run_neighbors, "expand neighbours from one entity")
    neighbors.add_argument("entity_id")
    neighbors.add_argument("--direction", choices=("both", "out", "in"), default="both")
    neighbors.add_argument("--relation", dest="relation_type")
    neighbors.add_argument("--depth", type=int, default=1)
    backlinks = command("backlinks", _run_backlinks, "show incoming and outgoing links")
    backlinks.add_argument("entity_id")
    backlinks.add_argument("--relation", dest="relation_type")
    command("integrity", _run_integrity, "run SQLite integrity and foreign-key checks")
    command("verify", _run_verify, "seed and verify the demo data path")
    export = command("export", _run_export, "write Markdown, HTML, Graph JSON and CSV")
    export.add_argument("--output-dir", type=Path, required=True)
    backup = command("backup", _run_backup, "create a consistent SQLite backup")
    backup.add_argument("--destination", type=Path)
    restore = command("restore", _run_restore, "restore a validated backup to a new workspace")
    restore.add_argument("source", type=Path)
    restore.add_argument("destination", type=Path)
    restore.add_argument("--replace", action="store_true", help="replace an existing destination")
    timeline = command("timeline", _run_timeline, "list durable research timeline events")
    timeline.add_argument("--entity", dest="entity_id")
    timeline.add_argument("--event-type")
    timeline.add_argument("--limit", type=int, default=200)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = args.handler(args)
        _json_dump(result, pretty=not args.compact)
        return 0 if result.get("status") not in {"fail", "FAIL"} else 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary must be machine-readable
        _json_dump({"status": "error", "command": getattr(args, "command", None), "error": str(exc)})
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main())
