"""Headless smoke tests for the desktop adapter.

These tests deliberately avoid constructing Tk (CI and Windows packaging
checks may not have a display).  They exercise the exact persistence paths
used by the UI: typed entities, relations, search, exports and restore.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from researchos.models import Entity, Relation
from researchos.ui import StoreFacade


class StoreFacadeSmokeTests(unittest.TestCase):
    def test_graph_search_export_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "workspace.sqlite3"
            store = StoreFacade(db)
            paper = store.create_entity(Entity("Paper", "Synthetic paper", content="episodic memory"))
            claim = store.create_entity(Entity("Claim", "Memory claim", data={"confidence": 0.8}))
            store.create_relation(Relation(paper.id or "", "SUPPORTS", claim.id or ""))

            self.assertEqual(len(store.list_entities()), 2)
            self.assertEqual(store.search("episodic")[0].title, "Synthetic paper")
            nodes, edges = store.graph()
            self.assertEqual((len(nodes), len(edges)), (2, 1))
            self.assertEqual(store.neighbors(paper.id or "")[0].title, "Memory claim")
            self.assertEqual(store.backlinks(claim.id or "")[0][0].title, "Synthetic paper")

            exported = store.export_formats(root / "export")
            for path in exported.values():
                self.assertTrue(Path(path).exists(), path)
            backup = root / "backup.sqlite3"
            store.backup(str(backup))
            store.close()

            restored = StoreFacade(root / "restored.sqlite3")
            restored.restore(str(backup))
            self.assertEqual(len(restored.list_entities()), 2)
            self.assertIn("ok", str(restored.integrity_check()).lower())
            restored.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

