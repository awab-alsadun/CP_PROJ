"""
Document Service
----------------
Handles upload, classification, section-aware chunking, and embedding
of regulatory/compliance documents.

Flow:
  PDF bytes → PyMuPDF text extraction → document classification →
  section-aware chunking → embed → store in company_documents

Section-aware chunking:
  - Detects section boundaries via regex (Article X, Section X, Chapter X,
    numbered headings 1., 1.1, etc.)
  - Splits long sections at sentence boundaries (~500 tokens, 100 overlap)
  - Each chunk carries page_number, section_title, section_number metadata

Provider-agnostic: uses get_embedding_provider().
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from supabase import Client

from app.core.config import get_settings
from app.providers import get_embedding_provider

log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

MAX_PAGES = 100
CHUNK_SIZE_TOKENS = 500         # approximate, using 1 token ≈ 4 chars
CHUNK_OVERLAP_TOKENS = 100
CHARS_PER_TOKEN = 4
CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
CHUNK_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN

# ── Section detection ────────────────────────────────────────────────────────

_SECTION_PATTERN = re.compile(
    r"^("
    r"(?:Article|ARTICLE|Section|SECTION|Chapter|CHAPTER)\s+\d+[\.\:]?"
    r"|"
    r"\d+\.\d*(?:\.\d+)*[\.\:]?\s"
    r"|"
    r"[A-Z][A-Z\s]{5,}$"  # ALL CAPS lines (headings)
    r")",
    re.MULTILINE,
)


@dataclass
class TextSection:
    title: str
    number: str
    text: str
    page_number: int


@dataclass
class DocumentChunk:
    chunk_text: str
    chunk_type: str           # 'section', 'header', 'full_page'
    chunk_index: int
    section_title: str | None
    section_number: str | None
    page_number: int | None


# ── Document classification ──────────────────────────────────────────────────

_REGULATION_KEYWORDS = [
    "regulation", "article", "section", "chapter", "law",
    "compliance", "obligation", "penalty", "requirement",
    "tax", "vat", "customs", "tariff", "decree", "statute",
    "guideline", "policy", "directive", "e-invoice", "e-invoicing",
    "authority", "ministry", "government", "enacted", "amended",
    "pursuant", "herein", "thereof", "notwithstanding",
]

_INVOICE_KEYWORDS = [
    "invoice", "bill to", "ship to", "subtotal", "grand total",
    "due date", "payment terms", "unit price", "qty", "quantity",
    "remit to", "purchase order", "po number",
]


def classify_document(text: str) -> str:
    """
    Classify document as 'regulation' or 'invoice' based on keyword frequency.

    Scans the entire document text, not just the first page.
    Returns: 'regulation' or 'invoice'
    """
    text_lower = text.lower()

    reg_score = sum(1 for kw in _REGULATION_KEYWORDS if kw in text_lower)
    inv_score = sum(1 for kw in _INVOICE_KEYWORDS if kw in text_lower)

    if reg_score > inv_score:
        return "regulation"
    if inv_score > reg_score:
        return "invoice"

    # Tie or no matches — default to regulation since this endpoint
    # is specifically for regulation uploads
    return "regulation"


# ── PDF extraction ───────────────────────────────────────────────────────────

def extract_text_with_pages(file_bytes: bytes) -> list[dict]:
    """
    Extract text from PDF with page numbers.

    Returns:
        List of {"page": int, "text": str} dicts.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    if len(doc) > MAX_PAGES:
        raise ValueError(
            f"Document has {len(doc)} pages. Maximum allowed is {MAX_PAGES}."
        )

    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages.append({"page": i + 1, "text": text.strip()})

    doc.close()
    return pages


# ── Section-aware chunking ───────────────────────────────────────────────────

def _detect_sections(pages: list[dict]) -> list[TextSection]:
    """
    Detect section boundaries across all pages.
    Returns a list of TextSection objects.
    """
    sections = []
    current_title = "Introduction"
    current_number = ""
    current_text = ""
    current_page = pages[0]["page"] if pages else 1

    for page_info in pages:
        page_num = page_info["page"]
        lines = page_info["text"].split("\n")

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            match = _SECTION_PATTERN.match(line_stripped)
            if match:
                # Save previous section
                if current_text.strip():
                    sections.append(TextSection(
                        title=current_title,
                        number=current_number,
                        text=current_text.strip(),
                        page_number=current_page,
                    ))

                # Start new section
                header = match.group(1).strip()
                # Extract number if present
                num_match = re.match(r"[\d\.]+", header)
                current_number = num_match.group(0) if num_match else ""
                current_title = line_stripped[:200]  # cap title length
                current_text = line_stripped + "\n"
                current_page = page_num
            else:
                current_text += line_stripped + "\n"

    # Don't forget the last section
    if current_text.strip():
        sections.append(TextSection(
            title=current_title,
            number=current_number,
            text=current_text.strip(),
            page_number=current_page,
        ))

    return sections


def _split_long_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """
    Split text at sentence boundaries, respecting max_chars with overlap.
    """
    if len(text) <= max_chars:
        return [text]

    # Split into sentences (rough but effective)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            # Overlap: keep the last overlap_chars of current chunk
            overlap = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else current_chunk
            current_chunk = overlap + " " + sentence
        else:
            current_chunk += (" " + sentence if current_chunk else sentence)

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def chunk_document(pages: list[dict]) -> list[DocumentChunk]:
    """
    Section-aware chunking with sub-splitting for long sections.

    Returns list of DocumentChunk with full metadata.
    """
    sections = _detect_sections(pages)
    chunks = []
    chunk_index = 0

    for section in sections:
        sub_texts = _split_long_text(
            section.text,
            max_chars=CHUNK_SIZE_CHARS,
            overlap_chars=CHUNK_OVERLAP_CHARS,
        )

        for sub_text in sub_texts:
            chunks.append(DocumentChunk(
                chunk_text=sub_text,
                chunk_type="section",
                chunk_index=chunk_index,
                section_title=section.title,
                section_number=section.number,
                page_number=section.page_number,
            ))
            chunk_index += 1

    return chunks


# ── Store document ───────────────────────────────────────────────────────────

def upload_and_embed_document(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
    document_type: str = "general",
    country: str | None = None,
) -> dict:
    """
    Full pipeline: extract → classify → chunk → embed → store.

    Args:
        db: Supabase client.
        company_id: Tenant UUID.
        file_bytes: Raw PDF bytes.
        filename: Original filename.
        document_type: 'tax_regulation', 'compliance_guide', 'vat_rules', etc.
        country: ISO country code.

    Returns:
        Summary dict with document_id, chunk_count, classification.
    """
    settings = get_settings()
    document_id = str(uuid.uuid4())

    # 1. Extract text with page numbers
    log.info(f"Extracting text from {filename}...")
    pages = extract_text_with_pages(file_bytes)
    if not pages:
        raise ValueError("No text could be extracted from the PDF.")

    full_text = "\n".join(p["text"] for p in pages)

    # 2. Classify document
    classification = classify_document(full_text)
    log.info(f"Document classified as: {classification}")

    if classification == "invoice":
        log.warning(
            f"Document '{filename}' appears to be an invoice, not a regulation. "
            "Proceeding anyway — user can re-tag if needed."
        )

    # 3. Chunk with section awareness
    chunks = chunk_document(pages)
    log.info(f"Generated {len(chunks)} chunks from {len(pages)} pages")

    if not chunks:
        raise ValueError("No chunks generated from the document.")

    # 4. Check for existing versions and deactivate
    existing = (
        db.table("company_documents")
        .select("document_id, version")
        .eq("company_id", company_id)
        .eq("document_name", filename)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    new_version = 1
    if existing.data:
        old_doc_id = existing.data[0]["document_id"]
        old_version = existing.data[0].get("version", 1)
        new_version = old_version + 1

        # Deactivate old version (not delete — preserves audit trail)
        db.table("company_documents").update(
            {"is_active": False}
        ).eq("document_id", old_doc_id).execute()

        log.info(f"Deactivated previous version {old_version} of '{filename}'")

    # 5. Embed all chunks
    embedder = get_embedding_provider()
    texts = [c.chunk_text for c in chunks]

    # Batch embed — provider handles rate limiting internally
    log.info(f"Embedding {len(texts)} chunks...")
    vectors = embedder.embed(texts)

    # 6. Insert into company_documents
    rows = []
    for chunk, vector in zip(chunks, vectors):
        rows.append({
            "company_id": company_id,
            "document_id": document_id,
            "document_name": filename,
            "document_type": document_type,
            "country": country,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.chunk_text,
            "chunk_type": chunk.chunk_type,
            "section_title": chunk.section_title,
            "section_number": chunk.section_number,
            "page_number": chunk.page_number,
            "embedding": vector,
            "model_name": (
                settings.OPENAI_EMBEDDING_MODEL
                if settings.LLM_PROVIDER == "openai"
                else settings.OLLAMA_EMBEDDING_MODEL
            ),
            "metadata": {
                "filename": filename,
                "document_type": document_type,
                "country": country,
                "classification": classification,
            },
            "version": new_version,
            "is_active": True,
        })

    # Insert in batches of 50 to avoid payload limits
    batch_size = 50
    stored = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            db.table("company_documents").insert(batch).execute()
            stored += len(batch)
        except Exception as e:
            log.error(f"Failed to insert chunk batch {i}-{i+len(batch)}: {e}")

    log.info(f"Stored {stored}/{len(chunks)} chunks for document '{filename}'")

    return {
        "document_id": document_id,
        "document_name": filename,
        "document_type": document_type,
        "country": country,
        "classification": classification,
        "chunk_count": stored,
        "page_count": len(pages),
        "version": new_version,
    }


# ── List / Delete / Update ───────────────────────────────────────────────────

def list_documents(db: Client, company_id: str) -> list[dict]:
    """List all active documents for a company (one row per document)."""
    result = (
        db.table("company_document_summary")
        .select("*")
        .eq("company_id", company_id)
        .eq("is_active", True)
        .order("uploaded_at", desc=True)
        .execute()
    )
    return result.data or []


def delete_document(db: Client, company_id: str, document_id: str) -> bool:
    """
    Delete a document and all its chunks.
    Actually deletes rows — not soft delete, since deactivated versions
    are already preserved via the versioning system.
    """
    result = (
        db.table("company_documents")
        .delete()
        .eq("company_id", company_id)
        .eq("document_id", document_id)
        .execute()
    )
    deleted = len(result.data) if result.data else 0
    log.info(f"Deleted {deleted} chunks for document {document_id}")
    return deleted > 0


def update_document_metadata(
    db: Client,
    company_id: str,
    document_id: str,
    document_type: str | None = None,
    country: str | None = None,
) -> bool:
    """Update document_type and/or country for all chunks of a document."""
    updates = {}
    if document_type is not None:
        updates["document_type"] = document_type
    if country is not None:
        updates["country"] = country

    if not updates:
        return False

    result = (
        db.table("company_documents")
        .update(updates)
        .eq("company_id", company_id)
        .eq("document_id", document_id)
        .execute()
    )
    updated = len(result.data) if result.data else 0
    log.info(f"Updated {updated} chunks for document {document_id}")
    return updated > 0