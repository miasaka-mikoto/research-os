"""Backward-compatible import surface for the Research OS storage layer.

The implementation lives in :mod:`researchos.store`; this alias keeps early
scripts and third-party integrations stable while the project evolves.
"""

from .store import IntegrityError, NotFoundError, ResearchStore, StoreError, create_workspace, open_workspace, utc_now

__all__ = [
    "ResearchStore",
    "StoreError",
    "NotFoundError",
    "IntegrityError",
    "create_workspace",
    "open_workspace",
    "utc_now",
]
