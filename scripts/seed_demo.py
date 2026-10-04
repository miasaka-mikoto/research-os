#!/usr/bin/env python3
"""Create or refresh the deterministic Agent Memory Research Demo workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("demo_workspace") / "research.sqlite3",
        help="SQLite database path (default: demo_workspace/research.sqlite3)",
    )
    args = parser.parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from researchos.demo import seed_demo
    from researchos.storage import ResearchStore

    args.workspace.parent.mkdir(parents=True, exist_ok=True)
    store = ResearchStore(args.workspace)
    try:
        summary = seed_demo(store)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        close = getattr(store, "close", None)
        if close:
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
