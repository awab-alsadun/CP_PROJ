"""
Retrieval Source Registry
-------------------------
Central registry of all retrieval sources. The query service
iterates this list — never references individual sources directly.

To add a new source:
1. Create a new file implementing RetrievalSource
2. Import and append it to _SOURCES below
3. Done. Query service picks it up automatically.
"""

from app.services.retrieval.base import RetrievalSource
from app.services.retrieval.invoice_source import InvoiceSource
from app.services.retrieval.document_source import DocumentSource

# ── Active sources ──────────────────────────────────────────────────────────
# Order matters: sources listed first get retrieved first.
# Add new sources here.

_SOURCES: list[RetrievalSource] = [
    InvoiceSource(),
    DocumentSource(),
]


def get_all_sources() -> list[RetrievalSource]:
    """Return all registered retrieval sources."""
    return list(_SOURCES)


def get_source(name: str) -> RetrievalSource | None:
    """Get a specific source by name."""
    for source in _SOURCES:
        if source.name == name:
            return source
    return None


def get_source_names() -> list[str]:
    """Return names of all registered sources."""
    return [s.name for s in _SOURCES]