"""Application entry point for Research OS.

Running ``python -m researchos.app`` opens the Tkinter desktop application.
The UI import is lazy so ``--headless`` works on Linux servers and cloud
computers without a display server or a Tk installation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop app.

    ``--demo`` is deterministic and idempotent, making it useful for a first
    launch, screenshots and Windows smoke tests.  ``--workspace`` keeps the
    database location explicit for portable installations.
    """
    parser = argparse.ArgumentParser(prog="researchos", description="Research OS desktop workspace")
    parser.add_argument("--workspace", default=None, help="SQLite workspace path")
    parser.add_argument("--demo", action="store_true", help="seed the fictional Agent Memory Research Demo")
    parser.add_argument("--headless", action="store_true", help="run the display-free JSON agent CLI")
    parser.add_argument("--verify", action="store_true", help="with --headless, verify the demo workspace")
    args = parser.parse_args(argv)
    if args.workspace:
        db_path = Path(args.workspace)
    else:
        db_path = Path(os.environ.get("RESEARCHOS_HOME", Path.home() / "ResearchOS")) / "researchos.sqlite3"

    if args.headless:
        # Keep this branch completely free of Tk imports.  It is the easiest
        # compatibility path for Linux containers and cloud-computer agents.
        try:
            from .agent_cli import main as agent_main
        except ImportError:  # pragma: no cover - direct source execution fallback
            from researchos.agent_cli import main as agent_main
        command = "verify" if args.verify else ("demo" if args.demo else "init")
        return int(agent_main(["--workspace", str(db_path), command]))

    try:
        # Normal package execution: ``python -m researchos.app``.
        from .ui import ResearchOSApp
    except ImportError:  # pragma: no cover - PyInstaller executes app.py as __main__
        # PyInstaller's Windows entry script can execute this file without a
        # package parent.  The absolute import keeps the source tree usable in
        # that mode when ``--paths .`` is supplied by the build script.
        from researchos.ui import ResearchOSApp

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
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
