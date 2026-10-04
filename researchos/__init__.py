"""Research OS — a durable, graph-oriented personal research workspace."""

from .models import ENTITY_TYPES, Entity, Relation, SearchHit
from .store import IntegrityError, NotFoundError, ResearchStore, StoreError, create_workspace, open_workspace, utc_now
from .templates import TEMPLATES, get_template, list_templates
from .services import ResearchService, WorkspaceService

try:  # exporter is optional only during very early bootstrap
    from .exporter import ResearchExporter
except ImportError:  # pragma: no cover
    ResearchExporter = None  # type: ignore[assignment]

__all__ = [
    "ENTITY_TYPES",
    "Entity",
    "Relation",
    "SearchHit",
    "ResearchStore",
    "ResearchExporter",
    "StoreError",
    "NotFoundError",
    "IntegrityError",
    "create_workspace",
    "open_workspace",
    "utc_now",
    "TEMPLATES",
    "get_template",
    "list_templates",
    "ResearchService",
    "WorkspaceService",
]
