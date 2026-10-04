from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from researchos import Entity, ResearchService, ResearchStore


class ResearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="researchos-service-")
        self.store = ResearchStore(Path(self.tmp.name) / "research.sqlite3")
        self.service = ResearchService(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_structured_paper_claim_experiment_and_artifact_workflows(self) -> None:
        paper = self.service.create_paper("Synthetic paper", summary="A controlled note", key_claims=["c"])
        evidence = self.store.create_entity(Entity(entity_type="Evidence", title="Trace table"))
        claim = self.service.add_claim("Memory helps", source_ids=[paper.id], evidence_ids=[evidence.id], confidence=0.8, status="Supported")
        notes = self.service.paper_notes(paper.id)
        self.assertEqual(notes["summary"], "A controlled note")
        ledger = self.service.claim_ledger()
        row = next(item for item in ledger if item["id"] == claim.id)
        self.assertEqual(row["status"], "Supported")
        self.assertEqual(len(row["source"]), 1)
        self.assertEqual(len(row["evidence"]), 1)

        dataset = self.store.create_entity(Entity(entity_type="Dataset", title="Synthetic set"))
        hypothesis = self.store.create_entity(Entity(entity_type="Hypothesis", title="Testable hypothesis"))
        experiment = self.service.create_experiment("Ablation", question="Does it help?", hypothesis_id=hypothesis.id, dataset_ids=[dataset.id], configuration={"seed": 7})
        notebook = self.service.experiment_notebook(experiment.id)
        self.assertEqual(notebook["configuration"]["seed"], 7)
        result = self.service.record_result(experiment.id, "Positive result", hypothesis_id=hypothesis.id, supports=True, metrics={"score": 0.9})
        artifact = self.service.link_artifact(experiment.id, "C:/research/run.csv", kind="csv")
        relation_keys = {(r.source_id, r.relation_type, r.target_id) for r in self.store.list_relations()}
        self.assertIn((experiment.id, "PRODUCES", result.id), relation_keys)
        self.assertIn((artifact.id, "DOCUMENTS", experiment.id), relation_keys)

    def test_question_tree_and_bundle_export(self) -> None:
        root = self.store.create_entity(Entity(entity_type="Question", title="Root"))
        child = self.service.add_sub_question(root.id, "Child")
        tree = self.service.question_tree(root.id)
        self.assertEqual(tree["children"][0]["entity"]["id"], child.id)
        bundle = self.service.export_bundle(Path(self.tmp.name) / "bundle")
        self.assertEqual(set(bundle), {"markdown", "html", "graph_json", "entities_csv"})
        self.assertTrue(all(path.exists() and path.stat().st_size for path in bundle.values()))


if __name__ == "__main__":
    unittest.main()
