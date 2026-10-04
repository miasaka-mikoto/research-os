"""Higher-level research workflows built on :mod:`researchos.store`.

The database deliberately exposes generic entities and relations.  This
service layer provides named operations for the workflows people actually use
— paper reviews, claim ledgers, experiment notebooks, artifact links and
question trees — without hiding the underlying graph records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import Entity
from .store import ResearchStore


class ResearchService:
    """Application-level operations for one Research OS workspace."""

    def __init__(self, store: ResearchStore) -> None:
        self.store = store

    # --------------------------------------------------------------
    # Paper and claim ledger
    # --------------------------------------------------------------
    def create_paper(
        self,
        title: str,
        *,
        summary: str = "",
        key_claims: Sequence[str] | None = None,
        methods: str = "",
        results: str = "",
        limitations: str = "",
        questions: Sequence[str] | None = None,
        related_papers: Sequence[str] | None = None,
        content: str = "",
        paper_id: str | None = None,
        **extra: Any,
    ) -> Entity:
        data = {
            "summary": summary,
            "key_claims": list(key_claims or []),
            "methods": methods,
            "results": results,
            "limitations": limitations,
            "questions": list(questions or []),
            "related_papers": list(related_papers or []),
            **extra,
        }
        paper = self.store.create_entity(Entity(id=paper_id, entity_type="Paper", title=title, content=content, data=data))
        for related_id in related_papers or []:
            self.store.create_relation(source_id=paper.id, relation_type="RELATED_TO", target_id=related_id)
        return paper

    def paper_notes(self, paper_id: str) -> dict[str, Any]:
        paper = self.store.require_entity(paper_id)
        if paper.entity_type != "Paper":
            raise ValueError(f"not a Paper entity: {paper_id}")
        defaults = {"summary": "", "key_claims": [], "methods": "", "results": "", "limitations": "", "questions": [], "related_papers": []}
        defaults.update(paper.data)
        defaults.update({"id": paper.id, "title": paper.title, "content": paper.content, "updated_at": paper.updated_at})
        return defaults

    def add_claim(
        self,
        statement: str,
        *,
        source_ids: Iterable[str] = (),
        evidence_ids: Iterable[str] = (),
        contradicting_evidence_ids: Iterable[str] = (),
        confidence: float | None = None,
        status: str = "Unreviewed",
        content: str = "",
        claim_id: str | None = None,
        **extra: Any,
    ) -> Entity:
        source_ids, evidence_ids, contradicting_evidence_ids = list(source_ids), list(evidence_ids), list(contradicting_evidence_ids)
        data = {"source_ids": source_ids, "evidence_ids": evidence_ids, "contradicting_evidence_ids": contradicting_evidence_ids, "confidence": confidence, "status": status, **extra}
        claim = self.store.create_entity(Entity(id=claim_id, entity_type="Claim", title=statement, content=content, data=data))
        for source_id in source_ids:
            self.store.create_relation(source_id=source_id, relation_type="SUPPORTS", target_id=claim.id)
        for evidence_id in evidence_ids:
            self.store.create_relation(source_id=evidence_id, relation_type="SUPPORTS", target_id=claim.id)
        for evidence_id in contradicting_evidence_ids:
            self.store.create_relation(source_id=evidence_id, relation_type="REFUTES", target_id=claim.id)
        return claim

    @staticmethod
    def _unwrap_link(item: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        entity = item.get("entity", item)
        relation = item.get("relation", {})
        return (dict(entity) if isinstance(entity, Mapping) else {}, dict(relation) if isinstance(relation, Mapping) else {})

    def claim_ledger(self, *, status: str | None = None) -> list[dict[str, Any]]:
        claims = self.store.list_entities(entity_type="Claim", order_by="updated_at", descending=True)
        rows: list[dict[str, Any]] = []
        for claim in claims:
            incoming = self.store.backlinks(claim.id)
            sources, evidence, contradicting = [], [], []
            for link in incoming:
                entity, relation = self._unwrap_link(link)
                relation_kind = relation.get("relation_type")
                if relation_kind == "REFUTES":
                    contradicting.append(entity)
                elif relation_kind == "SUPPORTS":
                    if entity.get("entity_type") == "Evidence":
                        evidence.append(entity)
                    else:
                        sources.append(entity)
            data = dict(claim.data)
            current_status = data.get("status", "Unreviewed")
            if status and str(current_status).lower() != status.lower():
                continue
            rows.append({
                **claim.to_dict(),
                "statement": claim.title,
                "source": sources,
                "evidence": evidence,
                "contradicting_evidence": contradicting,
                "confidence": data.get("confidence"),
                "status": current_status,
            })
        return rows

    # --------------------------------------------------------------
    # Experiments, results and artifact links
    # --------------------------------------------------------------
    def create_experiment(
        self,
        title: str,
        *,
        question: str = "",
        hypothesis: str = "",
        hypothesis_id: str | None = None,
        method: str = "",
        configuration: Mapping[str, Any] | None = None,
        dataset_ids: Iterable[str] = (),
        code: str = "",
        runs: Sequence[Mapping[str, Any]] | None = None,
        content: str = "",
        experiment_id: str | None = None,
        **extra: Any,
    ) -> Entity:
        dataset_ids = list(dataset_ids)
        data = {"question": question, "hypothesis": hypothesis, "method": method, "configuration": dict(configuration or {}), "dataset_ids": dataset_ids, "code": code, "runs": list(runs or []), **extra}
        experiment = self.store.create_entity(Entity(id=experiment_id, entity_type="Experiment", title=title, content=content, data=data))
        if hypothesis_id:
            self.store.create_relation(source_id=hypothesis_id, relation_type="TESTED_BY", target_id=experiment.id)
        for dataset_id in dataset_ids:
            self.store.create_relation(source_id=experiment.id, relation_type="USES", target_id=dataset_id)
        return experiment

    def experiment_notebook(self, experiment_id: str) -> dict[str, Any]:
        experiment = self.store.require_entity(experiment_id)
        if experiment.entity_type != "Experiment":
            raise ValueError(f"not an Experiment entity: {experiment_id}")
        fields = {"question": "", "hypothesis": "", "method": "", "configuration": {}, "dataset_ids": [], "code": "", "runs": [], "results": [], "interpretation": "", "limitations": "", "next_step": ""}
        fields.update(experiment.data)
        fields.update({"id": experiment.id, "title": experiment.title, "content": experiment.content, "updated_at": experiment.updated_at})
        return fields

    def record_result(
        self,
        experiment_id: str,
        title: str,
        *,
        interpretation: str = "",
        metrics: Mapping[str, Any] | None = None,
        hypothesis_id: str | None = None,
        supports: bool | None = None,
        content: str = "",
        result_id: str | None = None,
        **extra: Any,
    ) -> Entity:
        result = self.store.create_entity(Entity(id=result_id, entity_type="Result", title=title, content=content, data={"experiment_id": experiment_id, "interpretation": interpretation, "metrics": dict(metrics or {}), **extra}))
        self.store.create_relation(source_id=experiment_id, relation_type="PRODUCES", target_id=result.id)
        if hypothesis_id and supports is not None:
            self.store.create_relation(source_id=result.id, relation_type="SUPPORTS" if supports else "REFUTES", target_id=hypothesis_id)
        return result

    def link_artifact(
        self,
        owner_id: str,
        path: str,
        *,
        title: str | None = None,
        kind: str = "file",
        artifact_id: str | None = None,
        **extra: Any,
    ) -> Entity:
        artifact = self.store.create_entity(Entity(id=artifact_id, entity_type="Artifact", title=title or Path(path).name or path, data={"path": path, "kind": kind, **extra}))
        self.store.create_relation(source_id=artifact.id, relation_type="DOCUMENTS", target_id=owner_id)
        return artifact

    # --------------------------------------------------------------
    # Questions, logs and export
    # --------------------------------------------------------------
    def add_sub_question(self, parent_id: str, title: str, *, content: str = "", question_id: str | None = None, **data: Any) -> Entity:
        parent = self.store.require_entity(parent_id)
        if parent.entity_type != "Question":
            raise ValueError(f"parent is not a Question entity: {parent_id}")
        child = self.store.create_entity(Entity(id=question_id, entity_type="Question", title=title, content=content, data=data))
        self.store.create_relation(source_id=parent_id, relation_type="HAS_SUBQUESTION", target_id=child.id)
        return child

    def question_tree(self, root_id: str, *, _visited: set[str] | None = None) -> dict[str, Any]:
        visited = set(_visited or ())
        if root_id in visited:
            return {"entity": {"id": root_id}, "children": [], "cycle": True}
        visited.add(root_id)
        root = self.store.require_entity(root_id)
        result = {"entity": root.to_dict(), "children": []}
        for relation in self.store.list_relations(source_id=root_id, relation_type="HAS_SUBQUESTION"):
            result["children"].append(self.question_tree(relation.target_id, _visited=visited))
        return result

    def export_bundle(self, directory: str | Path) -> dict[str, Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        return {
            "markdown": self.store.export_markdown(root / "archive.md"),
            "html": self.store.export_html(root / "report.html"),
            "graph_json": self.store.export_graph_json(root / "graph.json"),
            "entities_csv": self.store.export_csv(root / "entities.csv"),
        }


WorkspaceService = ResearchService

__all__ = ["ResearchService", "WorkspaceService"]
