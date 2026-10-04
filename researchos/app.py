"""Application entry point for Research OS.

Running ``python -m researchos.app`` opens the Windows-friendly Tkinter
desktop application.  Keeping this tiny entry point separate makes it easy to
package with PyInstaller while retaining importable UI classes for tests.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    # Normal package execution: ``python -m researchos.app``.
    from .ui import ResearchOSApp
except ImportError:  # pragma: no cover - PyInstaller executes app.py as __main__
    # PyInstaller's Windows entry script can execute this file without a
    # package parent.  The absolute import keeps the same source tree usable
    # in that mode when ``--paths .`` is supplied by the build script.
    from researchos.ui import ResearchOSApp


def main(argv: list[str] | None = None) -> None:
    """Launch the desktop app.

    ``--demo`` is deterministic and idempotent, making it useful for a first
    launch, screenshots and Windows smoke tests.  ``--workspace`` keeps the
    database location explicit for portable installations.
    """
    parser = argparse.ArgumentParser(prog="researchos", description="Research OS desktop workspace")
    parser.add_argument("--workspace", default=None, help="SQLite workspace path")
    parser.add_argument("--demo", action="store_true", help="seed the fictional Agent Memory Research Demo")
    args = parser.parse_args(argv)
    if args.workspace:
        db_path = Path(args.workspace)
    else:
        db_path = Path(os.environ.get("RESEARCHOS_HOME", Path.home() / "ResearchOS")) / "researchos.sqlite3"
    if args.demo:
        try:
            from .demo import seed_demo
            from .ui import StoreFacade
        except ImportError:  # bundled one-file execution
            from researchos.demo import seed_demo
            from researchos.ui import StoreFacade

        seed_store = StoreFacade(db_path)
        seed_demo(seed_store.backend)
        seed_store.close()
    app = ResearchOSApp(db_path=db_path)
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
