"""Contract tests for the display-free JSON agent interface."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from researchos.agent_cli import main
from researchos.app import main as app_main


class AgentCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> dict:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(args))
        self.assertEqual(code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def test_demo_search_graph_export_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace.sqlite3"
            demo = self.run_cli("demo", "--workspace", str(workspace))
            self.assertEqual(demo["status"], "ok")
            self.assertEqual(demo["integrity"]["counts"]["entities"], 51)

            search = self.run_cli("search", "episodic", "--workspace", str(workspace))
            self.assertGreaterEqual(search["count"], 1)
            self.assertIn("claim-001", {hit["id"] for hit in search["hits"]})

            graph = self.run_cli("graph", "--entity", "paper-001", "--depth", "1", "--workspace", str(workspace))
            self.assertGreaterEqual(graph["node_count"], 2)
            self.assertGreaterEqual(graph["edge_count"], 1)

            export = self.run_cli("export", "--workspace", str(workspace), "--output-dir", str(root / "export"))
            self.assertEqual(set(export["files"]), {"markdown", "html", "graph_json", "csv", "relations_csv"})
            self.assertTrue(all(Path(path).exists() for path in export["files"].values()))

            integrity = self.run_cli("integrity", "--workspace", str(workspace))
            self.assertEqual(integrity["status"], "ok")

    def test_backup_restore_and_headless_app_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace.sqlite3"
            self.run_cli("demo", "--workspace", str(workspace))
            backup = self.run_cli("backup", "--workspace", str(workspace), "--destination", str(root / "backup.sqlite3"))
            self.assertGreater(backup["bytes"], 0)
            restored = self.run_cli("restore", str(root / "backup.sqlite3"), str(root / "restored.sqlite3"), "--replace")
            self.assertEqual(restored["integrity"]["counts"]["relations"], 55)

            headless_workspace = root / "headless.sqlite3"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = app_main(["--headless", "--verify", "--workspace", str(headless_workspace)])
            self.assertEqual(code, 0, output.getvalue())
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

