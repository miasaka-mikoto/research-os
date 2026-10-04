"""Portable exports for a :class:`~researchos.store.ResearchStore`.

Exports are deliberately dependency-free so a workspace remains useful even
when opened on a clean Windows machine.  Every format carries IDs and relation
types; no information is reduced to an untraceable prose dump.
"""

from __future__ import annotations

import csv as csv_module
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Entity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ResearchExporter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def graph_json(self, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "research-os-graph",
            "format_version": 1,
            "generated_at": _now(),
            "graph": self.store.graph(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def csv(self, destination: str | Path) -> Path:
        """Export entity rows to CSV, with JSON kept in a stable column."""
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        entities = self.store.list_entities(order_by="created_at", descending=False)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv_module.DictWriter(
                handle,
                fieldnames=["id", "entity_type", "title", "content", "data", "created_at", "updated_at", "version"],
            )
            writer.writeheader()
            for entity in entities:
                writer.writerow(
                    {
                        "id": entity.id,
                        "entity_type": entity.entity_type,
                        "title": entity.title,
                        "content": entity.content,
                        "data": json.dumps(entity.data, ensure_ascii=False, sort_keys=True),
                        "created_at": entity.created_at,
                        "updated_at": entity.updated_at,
                        "version": entity.version,
                    }
                )
        return path

    def relations_csv(self, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv_module.DictWriter(handle, fieldnames=["id", "source_id", "relation_type", "target_id", "metadata", "created_at"])
            writer.writeheader()
            for relation in self.store.list_relations(include_deleted_entities=True):
                writer.writerow({**relation.to_dict(), "metadata": json.dumps(relation.metadata, ensure_ascii=False, sort_keys=True)})
        return path

    def markdown(self, destination: str | Path) -> Path:
        target = Path(destination)
        # A .md destination is a single self-contained archive.  A directory
        # receives an index and one file per entity, which is convenient for Git.
        if target.suffix.lower() == ".md":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._markdown_document(), encoding="utf-8")
            return target
        target.mkdir(parents=True, exist_ok=True)
        entities = self.store.list_entities(order_by="entity_type", descending=False)
        index_lines = ["# Research OS Archive", "", f"Generated: {_now()}", "", "## Entities", ""]
        for entity in entities:
            filename = self._entity_filename(entity)
            (target / filename).write_text(self._entity_markdown(entity), encoding="utf-8")
            index_lines.append(f"- [{entity.entity_type}: {entity.title or entity.id}](entities/{filename})")
        entity_dir = target / "entities"
        entity_dir.mkdir(exist_ok=True)
        # Move files into entities after writing to avoid path assumptions in
        # callers that already created the destination directory.
        for entity in entities:
            filename = self._entity_filename(entity)
            source = target / filename
            if source.exists():
                source.replace(entity_dir / filename)
        index_lines.extend(["", "## Relations", ""])
        for relation in self.store.list_relations(include_deleted_entities=True):
            index_lines.append(f"- `{relation.relation_type}` `{relation.source_id}` → `{relation.target_id}`")
        (target / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        return target

    def _markdown_document(self) -> str:
        lines = ["# Research OS Archive", "", f"Generated: {_now()}", ""]
        for entity in self.store.list_entities(order_by="entity_type", descending=False):
            lines.extend(self._entity_markdown(entity).splitlines())
            lines.append("\n---\n")
        lines.extend(["## Relations", ""])
        for relation in self.store.list_relations(include_deleted_entities=True):
            lines.append(f"- `{relation.relation_type}` `{relation.source_id}` → `{relation.target_id}`")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _entity_filename(entity: Entity) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in (entity.id or "entity"))
        return f"{safe}.md"

    def _entity_markdown(self, entity: Entity) -> str:
        lines = [f"# {entity.title or '(untitled)'}", "", f"- **Type:** `{entity.entity_type}`", f"- **ID:** `{entity.id}`", f"- **Created:** {entity.created_at}", f"- **Updated:** {entity.updated_at}", ""]
        if entity.content:
            lines.extend(["## Notes", "", entity.content, ""])
        if entity.data:
            lines.extend(["## Structured Data", "", "```json", json.dumps(entity.data, ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
        incoming = self.store.backlinks(entity.id) if entity.id else []
        outgoing = self.store.outlinks(entity.id) if entity.id else []
        if incoming:
            lines.extend(["## Backlinks", ""])
            lines.extend(f"- `{item['relation']['relation_type']}` from {item['entity']['title'] or item['entity']['id']}" for item in incoming)
            lines.append("")
        if outgoing:
            lines.extend(["## Links", ""])
            lines.extend(f"- `{item['relation']['relation_type']}` to {item['entity']['title'] or item['entity']['id']}" for item in outgoing)
            lines.append("")
        return "\n".join(lines)

    def html(self, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        graph = self.store.graph()
        rows = []
        for node in graph["nodes"]:
            rows.append(
                "<tr data-type=\"{typ}\"><td><code>{id}</code></td><td>{typ}</td><td>{title}</td><td>{content}</td></tr>".format(
                    id=html.escape(str(node.get("id", ""))),
                    typ=html.escape(str(node.get("entity_type", ""))),
                    title=html.escape(str(node.get("title", ""))),
                    content=html.escape(str(node.get("content", ""))[:300]),
                )
            )
        edge_rows = [
            f"<li><code>{html.escape(str(edge.get('source_id')))}</code> — <b>{html.escape(str(edge.get('relation_type')))}</b> → <code>{html.escape(str(edge.get('target_id')))}</code></li>"
            for edge in graph["edges"]
        ]
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research OS Report</title>
<style>body{{font:15px system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#18202a}} table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d7dce2;padding:.5rem;text-align:left;vertical-align:top}} th{{background:#f3f5f7}} code{{font-size:.9em}} input{{padding:.55rem;width:22rem;max-width:95%}} .muted{{color:#667}}</style>
</head><body><h1>Research OS Report</h1><p class="muted">Generated {_now()} · {len(graph['nodes'])} entities · {len(graph['edges'])} relations</p>
<p><input id="filter" placeholder="Filter entities…" oninput="filterRows()"></p>
<table id="entities"><thead><tr><th>ID</th><th>Type</th><th>Title</th><th>Notes</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Relations</h2><ul>{''.join(edge_rows) or '<li>No relations</li>'}</ul>
<script>function filterRows(){{const q=document.getElementById('filter').value.toLowerCase();document.querySelectorAll('#entities tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none')}}</script>
</body></html>"""
        path.write_text(document, encoding="utf-8")
        return path


__all__ = ["ResearchExporter"]

