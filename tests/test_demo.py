from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from researchos.demo import demo_entities, demo_relations, seed_demo
from researchos.models import Entity, Relation
from researchos.storage import ResearchStore


class DemoSeedTests(unittest.TestCase):
    def make_store(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="researchos-test-")
        return ResearchStore(Path(self.tmp.name) / "research.sqlite3")

    def tearDown(self):
        if hasattr(self, "store") and self.store is not None:
            self.store.close()
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def test_seed_has_required_entity_counts(self):
        self.store = self.make_store()
        summary = seed_demo(self.store)
        rows = self.store.list_entities()
        counts = Counter(row.entity_type for row in rows)
        self.assertEqual(counts["Paper"], 5)
        self.assertEqual(counts["Claim"], 10)
        self.assertEqual(counts["Hypothesis"], 3)
        self.assertEqual(counts["Experiment"], 4)
        self.assertGreaterEqual(counts["Result"], 4)
        self.assertEqual(summary["papers"], 5)
        self.assertEqual(summary["claims"], 10)

    def test_seed_is_idempotent(self):
        self.store = self.make_store()
        seed_demo(self.store)
        first_entities = len(self.store.list_entities())
        first_relations = len(self.store.list_relations())
        seed_demo(self.store)
        self.assertEqual(len(self.store.list_entities()), first_entities)
        self.assertEqual(len(self.store.list_relations()), first_relations)

    def test_provenance_chain_and_contradiction_are_queryable(self):
        self.store = self.make_store()
        seed_demo(self.store)
        relations = {(r.source_id, r.relation_type, r.target_id) for r in self.store.list_relations()}
        self.assertIn(("paper-001", "SUPPORTS", "claim-001"), relations)
        self.assertIn(("claim-001", "INSPIRES", "hypothesis-001"), relations)
        self.assertIn(("hypothesis-001", "TESTED_BY", "experiment-001"), relations)
        self.assertIn(("experiment-001", "PRODUCES", "result-001"), relations)
        self.assertIn(("result-001", "SUPPORTS", "hypothesis-001"), relations)
        self.assertIn(("claim-001", "CONTRADICTS", "claim-005"), relations)

    def test_search_indexes_structured_content(self):
        self.store = self.make_store()
        seed_demo(self.store)
        hits = self.store.search("episodic")
        ids = {hit.entity.id for hit in hits}
        self.assertIn("paper-001", ids)
        self.assertIn("claim-001", ids)
        self.assertTrue(self.store.search("horizon"))

    def test_graph_neighbors_and_backlinks(self):
        self.store = self.make_store()
        seed_demo(self.store)
        neighbors = list(self.store.neighbors("paper-001"))
        neighbor_ids = {getattr(item, "id", item.get("id")) for item in neighbors}
        self.assertIn("claim-001", neighbor_ids)
        backlinks = list(self.store.backlinks("paper-001"))
        backlink_ids = {getattr(item, "id", item.get("id")) for item in backlinks}
        self.assertIn("paper-002", backlink_ids)

    def test_backup_restore_and_exports(self):
        self.store = self.make_store()
        seed_demo(self.store)
        root = Path(self.tmp.name)
        backup = root / "backup.sqlite3"
        self.store.backup(backup)
        self.assertTrue(backup.exists())
        restored = ResearchStore(root / "restored.sqlite3")
        try:
            restored.restore(backup)
            self.assertEqual(len(restored.list_entities()), len(self.store.list_entities()))
            self.assertEqual(len(restored.list_relations()), len(self.store.list_relations()))
            self.assertTrue(restored.integrity_check())
        finally:
            restored.close()

        exports = {
            "export_markdown": "archive.md",
            "export_html": "report.html",
            "export_graph_json": "graph.json",
            "export_csv": "entities.csv",
        }
        for method_name, filename in exports.items():
            output = root / filename
            getattr(self.store, method_name)(output)
            self.assertTrue(output.exists(), method_name)
            self.assertGreater(output.stat().st_size, 0, method_name)


class DomainRecordTests(unittest.TestCase):
    def test_demo_records_are_fresh_and_serialisable(self):
        entities_a = demo_entities()
        entities_b = demo_entities()
        self.assertEqual(len(entities_a), len(entities_b))
        entities_a[0].data["mutated"] = True
        self.assertNotIn("mutated", entities_b[0].data)
        self.assertEqual(json.loads(json.dumps(entities_b[0].to_dict()))["id"], entities_b[0].id)

    def test_relation_keys_are_unique(self):
        relations = demo_relations()
        keys = [(r.source_id, r.relation_type, r.target_id) for r in relations]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
