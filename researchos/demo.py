"""Deterministic synthetic workspace used by the Research OS demo and tests.

The demo is intentionally fictional.  It exercises the provenance chain that
Research OS is built around (paper -> claim -> hypothesis -> experiment ->
result) as well as contradictions, backlinks, artifacts and research
questions.  Keeping the seed data in a small, importable module means the UI,
CLI and verification script all use exactly the same workspace.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Entity, Relation


DEMO_WORKSPACE_NAME = "Agent Memory Research Demo"


# (id, title, content, structured data)
PAPERS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    (
        "paper-001",
        "A Synthetic Study of Episodic Agent Memory",
        "A fictional benchmark study comparing short and episodic memory on long-horizon tasks.",
        {"authors": ["M. Ito", "R. Chen"], "year": 2024, "venue": "Synthetic Systems Review", "tags": ["memory", "agents"]},
    ),
    (
        "paper-002",
        "Retrieval Policies for Long-Horizon Tool Use",
        "Fictional paper proposing uncertainty-aware retrieval for tool-using agents.",
        {"authors": ["A. Silva"], "year": 2023, "venue": "Imaginary ML Workshop", "tags": ["retrieval", "tools"]},
    ),
    (
        "paper-003",
        "When Memory Summaries Lose the Plot",
        "Fictional analysis of information loss caused by aggressive memory compression.",
        {"authors": ["Y. Park", "S. Khan"], "year": 2024, "venue": "Mock NLP Conference", "tags": ["compression", "failure"]},
    ),
    (
        "paper-004",
        "A Controlled Evaluation of Agent Reflection",
        "Fictional controlled evaluation of reflection prompts and delayed feedback.",
        {"authors": ["L. Gomez"], "year": 2022, "venue": "Toy Agents Journal", "tags": ["reflection", "evaluation"]},
    ),
    (
        "paper-005",
        "Benchmark Design for Persistent Artificial Memory",
        "Fictional design note describing a reproducible benchmark for persistent memory.",
        {"authors": ["N. Sato", "K. Wu"], "year": 2025, "venue": "Research OS Notes", "tags": ["benchmark", "reproducibility"]},
    ),
)


CLAIMS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("claim-001", "Episodic memory improves long-horizon agent performance", "The synthetic study reports fewer repeated tool mistakes when episodic traces are available.", {"confidence": 0.72, "status": "provisional"}),
    ("claim-002", "Uncertainty-aware retrieval reduces irrelevant context", "Retrieval is selectively expanded when the agent is uncertain.", {"confidence": 0.66, "status": "provisional"}),
    ("claim-003", "Aggressive summaries remove rare but decisive facts", "Compression preserves frequent facts but can erase a one-off constraint.", {"confidence": 0.81, "status": "supported"}),
    ("claim-004", "Reflection can improve delayed-credit tasks", "A reflection pass helps only when feedback arrives after several actions.", {"confidence": 0.58, "status": "inconclusive"}),
    ("claim-005", "Memory benefits depend on task horizon", "Short tasks show little difference between memory policies.", {"confidence": 0.63, "status": "provisional"}),
    ("claim-006", "Retrieval latency is a meaningful agent cost", "More retrieval calls improve recall but increase wall-clock time.", {"confidence": 0.76, "status": "supported"}),
    ("claim-007", "Persistent memory needs an explicit forgetting policy", "Unbounded traces create stale and contradictory context.", {"confidence": 0.69, "status": "provisional"}),
    ("claim-008", "Benchmark leakage can mimic memory gains", "Overlapping task templates make a memory system appear stronger than it is.", {"confidence": 0.84, "status": "supported"}),
    ("claim-009", "Reflection and retrieval have interacting effects", "Reflection may compensate for weaker retrieval on some tasks.", {"confidence": 0.44, "status": "inconclusive"}),
    ("claim-010", "Reproducible seeds are required for memory comparisons", "Fixed seeds make stochastic runs comparable across policies.", {"confidence": 0.9, "status": "supported"}),
)


HYPOTHESES: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("hypothesis-001", "Episodic memory helps only after the task horizon exceeds four steps", "The benefit should emerge at longer horizons, not on one-shot tasks.", {"confidence": 0.62, "status": "untested"}),
    ("hypothesis-002", "Uncertainty-gated retrieval dominates always-retrieve under a fixed latency budget", "Selective retrieval should preserve useful context while reducing calls.", {"confidence": 0.55, "status": "untested"}),
    ("hypothesis-003", "A bounded memory with explicit forgetting is more robust than an unbounded trace", "Forgetting should reduce stale-context errors in long runs.", {"confidence": 0.6, "status": "untested"}),
)


EXPERIMENTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("experiment-001", "Horizon sweep: short vs long tasks", "Compare no-memory, summary and episodic policies over horizons 1, 4 and 8.", {"question": "When does memory help?", "method": "synthetic horizon sweep", "status": "complete"}),
    ("experiment-002", "Retrieval gate ablation", "Compare always-retrieve with uncertainty-gated retrieval at the same token budget.", {"question": "Does gating improve efficiency?", "method": "ablation", "status": "complete"}),
    ("experiment-003", "Forgetting-window stress test", "Vary the retention window and count stale-context failures.", {"question": "What is a safe memory window?", "method": "window sweep", "status": "complete"}),
    ("experiment-004", "Seeded replication run", "Re-run the strongest configuration with fixed seeds and a held-out split.", {"question": "Is the effect reproducible?", "method": "replication", "status": "running"}),
)


RESULTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("result-001", "Long horizons reveal an episodic-memory advantage", "The episodic policy scored highest at horizon eight in the synthetic run.", {"metric": "task_success", "value": 0.78, "run_count": 12}),
    ("result-002", "Gated retrieval saves calls with a small recall tradeoff", "The gate reduced retrieval calls while keeping most relevant facts.", {"metric": "retrieval_calls", "value": 0.61, "run_count": 12}),
    ("result-003", "A finite forgetting window reduces stale-context errors", "The middle window had fewer stale references than the unbounded trace.", {"metric": "stale_error_rate", "value": 0.18, "run_count": 12}),
    ("result-004", "Replication is currently inconclusive", "The held-out split is still running; no conclusion is recorded yet.", {"metric": "task_success", "value": 0.74, "run_count": 4}),
)


OTHER_ENTITIES: tuple[tuple[str, str, str, str, dict[str, Any]], ...] = (
    ("evidence-001", "Horizon sweep table", "Synthetic table comparing success by task horizon.", "Evidence", {"format": "csv", "path": "demo/evidence/horizon.csv"}),
    ("evidence-002", "Retrieval call trace", "Logged retrieval decisions from the ablation run.", "Evidence", {"format": "jsonl", "path": "demo/evidence/retrieval.jsonl"}),
    ("evidence-003", "Forgetting error examples", "Hand-reviewed examples of stale context.", "Evidence", {"format": "md", "path": "demo/evidence/forgetting.md"}),
    ("evidence-004", "Held-out replication log", "Partial log from the seeded replication.", "Evidence", {"format": "log", "path": "demo/evidence/replication.log"}),
    ("concept-001", "Episodic memory", "A memory store retaining event-level traces.", "Concept", {"aliases": ["event memory"]}),
    ("concept-002", "Retrieval gating", "A policy deciding when to query memory.", "Concept", {}),
    ("concept-003", "Forgetting policy", "Rules for removing or down-weighting old traces.", "Concept", {}),
    ("question-001", "When does memory help?", "Find the smallest horizon at which memory changes outcomes.", "Question", {"status": "open"}),
    ("question-002", "How much retrieval is affordable?", "Measure quality against latency and token budgets.", "Question", {"status": "open"}),
    ("question-003", "Can the result replicate?", "Test the effect on a held-out synthetic split.", "Question", {"status": "open"}),
    ("dataset-001", "Synthetic Long Horizon Tasks v1", "Generated tasks with controlled horizon and distractors.", "Dataset", {"rows": 1200, "split": "train/test"}),
    ("dataset-002", "Retrieval Trace Set v1", "Tool-call traces annotated for relevance.", "Dataset", {"rows": 480, "split": "evaluation"}),
    ("dataset-003", "Held-out Memory Tasks v1", "A fixed-seed held-out replication set.", "Dataset", {"rows": 300, "split": "held-out"}),
    ("artifact-001", "Horizon sweep notebook", "Executable notebook for experiment 001.", "Artifact", {"kind": "code", "path": "demo/code/horizon_sweep.ipynb"}),
    ("artifact-002", "Retrieval gate implementation", "Reference implementation of the gate.", "Artifact", {"kind": "code", "path": "demo/code/retrieval_gate.py"}),
    ("artifact-003", "Results figure", "Synthetic line chart of success and horizon.", "Artifact", {"kind": "image", "path": "demo/figures/horizon.png"}),
    ("artifact-004", "Replication report", "Draft report for the seeded replication.", "Artifact", {"kind": "report", "path": "demo/reports/replication.md"}),
    ("idea-001", "Adaptive memory budgets", "Allocate memory bandwidth based on uncertainty.", "Idea", {"status": "candidate"}),
    ("idea-002", "Counterfactual trace replay", "Replay memories to test whether a decision depended on them.", "Idea", {"status": "candidate"}),
    ("decision-001", "Use fixed seeds in all comparisons", "Adopt reproducible seeds before interpreting memory effects.", "Decision", {"status": "accepted"}),
    ("decision-002", "Treat replication as provisional", "Do not promote the held-out result until it completes.", "Decision", {"status": "accepted"}),
    ("task-001", "Finish held-out replication", "Complete experiment 004 and attach the final log.", "Task", {"status": "in_progress"}),
    ("task-002", "Review contradiction between claims 001 and 005", "Check whether horizon moderates the apparent disagreement.", "Task", {"status": "todo"}),
)


def _entity(entity_id: str, entity_type: str, title: str, content: str, data: dict[str, Any]) -> Entity:
    return Entity(id=entity_id, entity_type=entity_type, title=title, content=content, data=dict(data))


def demo_entities() -> list[Entity]:
    """Return a fresh list of all synthetic entities."""

    entities: list[Entity] = []
    entities.extend(_entity(i, "Paper", t, c, d) for i, t, c, d in PAPERS)
    entities.extend(_entity(i, "Claim", t, c, d) for i, t, c, d in CLAIMS)
    entities.extend(_entity(i, "Hypothesis", t, c, d) for i, t, c, d in HYPOTHESES)
    entities.extend(_entity(i, "Experiment", t, c, d) for i, t, c, d in EXPERIMENTS)
    entities.extend(_entity(i, "Result", t, c, d) for i, t, c, d in RESULTS)
    entities.extend(_entity(i, typ, t, c, d) for i, t, c, typ, d in OTHER_ENTITIES)
    return entities


def demo_relations() -> list[Relation]:
    """Return the directed, typed edges for the synthetic graph."""

    edges: list[tuple[str, str, str]] = []
    # Provenance chain.
    edges += [(f"paper-{i:03d}", "SUPPORTS", f"claim-{i:03d}") for i in range(1, 6)]
    edges += [("paper-001", "SUPPORTS", "claim-006"), ("paper-002", "SUPPORTS", "claim-002"), ("paper-003", "SUPPORTS", "claim-003"), ("paper-004", "SUPPORTS", "claim-004"), ("paper-005", "SUPPORTS", "claim-008")]
    edges += [("claim-001", "INSPIRES", "hypothesis-001"), ("claim-002", "INSPIRES", "hypothesis-002"), ("claim-007", "INSPIRES", "hypothesis-003"), ("claim-005", "INSPIRES", "hypothesis-001"), ("claim-006", "INSPIRES", "hypothesis-002"), ("claim-003", "INSPIRES", "hypothesis-003")]
    edges += [("hypothesis-001", "TESTED_BY", "experiment-001"), ("hypothesis-002", "TESTED_BY", "experiment-002"), ("hypothesis-003", "TESTED_BY", "experiment-003"), ("hypothesis-001", "TESTED_BY", "experiment-004")]
    edges += [("experiment-001", "USES", "dataset-001"), ("experiment-002", "USES", "dataset-002"), ("experiment-003", "USES", "dataset-001"), ("experiment-004", "USES", "dataset-003")]
    edges += [("experiment-001", "PRODUCES", "result-001"), ("experiment-002", "PRODUCES", "result-002"), ("experiment-003", "PRODUCES", "result-003"), ("experiment-004", "PRODUCES", "result-004")]
    edges += [("result-001", "SUPPORTS", "hypothesis-001"), ("result-002", "SUPPORTS", "hypothesis-002"), ("result-003", "SUPPORTS", "hypothesis-003"), ("result-004", "NEEDS_VERIFICATION", "hypothesis-001"), ("result-002", "REFUTES", "hypothesis-003")]
    # Evidence, contradictions and research-question tree.
    edges += [("evidence-001", "SUPPORTS", "claim-001"), ("evidence-002", "SUPPORTS", "claim-002"), ("evidence-003", "SUPPORTS", "claim-003"), ("evidence-004", "NEEDS_VERIFICATION", "claim-010")]
    edges += [("claim-001", "CONTRADICTS", "claim-005"), ("claim-004", "CONTRADICTS", "claim-009"), ("claim-006", "NEEDS_VERIFICATION", "claim-009")]
    edges += [("paper-002", "CITES", "paper-001"), ("paper-003", "CITES", "paper-001"), ("paper-004", "CITES", "paper-002"), ("paper-005", "CITES", "paper-003")]
    edges += [("question-001", "MOTIVATES", "hypothesis-001"), ("question-002", "MOTIVATES", "hypothesis-002"), ("question-003", "MOTIVATES", "hypothesis-001"), ("question-003", "MOTIVATES", "hypothesis-003")]
    edges += [("artifact-001", "DOCUMENTS", "experiment-001"), ("artifact-002", "DOCUMENTS", "experiment-002"), ("artifact-003", "VISUALIZES", "result-001"), ("artifact-004", "DOCUMENTS", "experiment-004")]
    edges += [("idea-001", "EXTENDS", "hypothesis-002"), ("idea-002", "EXTENDS", "experiment-004"), ("decision-001", "INFORMS", "experiment-004"), ("decision-002", "INFORMS", "result-004"), ("task-001", "FOLLOWS", "experiment-004"), ("task-002", "FOLLOWS", "claim-001")]
    # Keep the synthetic graph deterministic and free of duplicate edge keys;
    # SQLite also enforces this invariant with a UNIQUE constraint.
    unique_edges = list(dict.fromkeys(edges))
    return [Relation(source_id=s, relation_type=r, target_id=t) for s, r, t in unique_edges]


def _upsert(store: Any, entity: Entity) -> Entity:
    """Use the store's upsert API while retaining compatibility with early builds."""

    if hasattr(store, "upsert_entity"):
        return store.upsert_entity(entity)
    existing = store.get_entity(entity.id) if hasattr(store, "get_entity") else None
    if existing is None:
        return store.create_entity(entity)
    return store.update_entity(entity.id, entity)


def seed_demo(store: Any, *, include_daily_logs: bool = True) -> dict[str, int | str]:
    """Populate ``store`` with the deterministic Agent Memory demo.

    The operation is idempotent: existing entities are updated and duplicate
    edges are skipped.  A compact count summary is returned for CLI scripts.
    """

    entities = demo_entities()
    for entity in entities:
        _upsert(store, entity)

    existing = {(r.source_id, r.relation_type, r.target_id) for r in store.list_relations()}
    relation_count = 0
    for relation in demo_relations():
        key = (relation.source_id, relation.relation_type, relation.target_id)
        if key in existing:
            continue
        store.create_relation(relation)
        existing.add(key)
        relation_count += 1

    if include_daily_logs and hasattr(store, "save_daily_log"):
        # Keep this best-effort so a store can be used with the seed before the
        # optional daily-log service is enabled.
        try:
            store.save_daily_log(
                "2026-10-01",
                read="Read the five fictional memory papers; extracted ten claims.",
            )
            store.save_daily_log(
                "2026-10-02",
                built="Built and ran four synthetic experiments; replication remains open.",
            )
        except (TypeError, ValueError, AttributeError):
            pass

    counts = Counter(entity.entity_type for entity in entities)
    result: dict[str, int | str] = {"workspace": DEMO_WORKSPACE_NAME, "entities": len(entities), "relations_added": relation_count}
    # Use readable plural keys in CLI/verification output (``hypothesiss``
    # is an easy typo to introduce with a blind ``+ 's'`` rule).
    plural_keys = {"Hypothesis": "hypotheses", "DailyLog": "daily_logs"}
    result.update({plural_keys.get(key, f"{key.lower()}s"): value for key, value in counts.items()})
    return result


__all__ = [
    "DEMO_WORKSPACE_NAME",
    "demo_entities",
    "demo_relations",
    "seed_demo",
]
