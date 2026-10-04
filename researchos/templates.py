"""Structured starter templates used by the Research OS UI.

Templates are data, not hidden Markdown blobs.  A panel can render the fields,
let the user edit them, and save them into an Entity's ``data`` object.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TEMPLATES: dict[str, dict[str, Any]] = {
    "Paper Review": {
        "entity_type": "Paper",
        "fields": ["summary", "key_claims", "methods", "results", "limitations", "questions", "related_papers"],
        "data": {"summary": "", "key_claims": [], "methods": "", "results": "", "limitations": "", "questions": [], "related_papers": []},
    },
    "Experiment": {
        "entity_type": "Experiment",
        "fields": ["question", "hypothesis", "method", "configuration", "dataset", "code", "runs", "results", "interpretation", "limitations", "next_step"],
        "data": {"question": "", "hypothesis": "", "method": "", "configuration": {}, "dataset": "", "code": "", "runs": [], "results": [], "interpretation": "", "limitations": "", "next_step": ""},
    },
    "Replication": {
        "entity_type": "Experiment",
        "fields": ["source_paper", "target_claim", "dataset", "baseline", "implementation_plan", "deviations", "result", "conclusion"],
        "data": {"source_paper": "", "target_claim": "", "dataset": "", "baseline": "", "implementation_plan": "", "deviations": [], "result": "", "conclusion": ""},
    },
    "Idea": {
        "entity_type": "Idea",
        "fields": ["problem", "observation", "proposed_direction", "assumptions", "risks", "next_step"],
        "data": {"problem": "", "observation": "", "proposed_direction": "", "assumptions": [], "risks": [], "next_step": ""},
    },
    "Weekly Review": {
        "entity_type": "DailyLog",
        "fields": ["wins", "read", "built", "tested", "learned", "blocked", "next_week"],
        "data": {"wins": [], "read": [], "built": [], "tested": [], "learned": [], "blocked": [], "next_week": []},
    },
    "Research Question": {
        "entity_type": "Question",
        "fields": ["scope", "motivation", "known_facts", "unknowns", "sub_questions", "success_criteria"],
        "data": {"scope": "", "motivation": "", "known_facts": [], "unknowns": [], "sub_questions": [], "success_criteria": []},
    },
}


def list_templates() -> list[str]:
    return list(TEMPLATES)


def get_template(name: str) -> dict[str, Any]:
    if name not in TEMPLATES:
        raise KeyError(name)
    return deepcopy(TEMPLATES[name])


__all__ = ["TEMPLATES", "get_template", "list_templates"]

