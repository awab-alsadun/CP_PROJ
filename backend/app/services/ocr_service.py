"""
OCR Service
-----------
Extracts text from invoice files (images and PDFs).

Extracted from rag_pipeline/ingest_invoices.py and adapted for FastAPI:
- Accepts bytes instead of file paths (FastAPI UploadFile gives bytes)
- Tesseract path from Settings, not hardcoded
- No file I/O for intermediate steps — works in memory

Two extraction paths:
  Image (JPG/PNG) → Pillow → Tesseract OCR → text
  PDF             → PyMuPDF render to image → Tesseract OCR → text
"""

import io
import logging

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.core.config import get_settings

log = logging.getLogger(__name__)


def _configure_tesseract():
    """Set Tesseract binary path from env if provided."""
    settings = get_settings()
    if settings.TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from an image file using Tesseract OCR.

    Args:
        file_bytes: Raw bytes of a JPG/PNG image.

    Returns:
        Extracted text string. Empty string if OCR fails.
    """
    _configure_tesseract()
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image, lang="eng")
        return text.strip()
    except Exception as e:
        log.error(f"Image OCR failed: {e}")
        return ""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF file.

    Strategy:
      1. Try PyMuPDF native text extraction first (fast, works on text-based PDFs).
      2. If no text found, fall back to rendering each page as an image
         and running Tesseract OCR (handles scanned/image-based PDFs).

    Args:
        file_bytes: Raw bytes of a PDF file.

    Returns:
        Extracted text string. Empty string if all methods fail.
    """
    _configure_tesseract()
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        # Attempt 1: Native text extraction (fast path)
        native_text = ""
        for page in doc:
            native_text += page.get_text() + "\n"

        if native_text.strip():
            doc.close()
            log.info("PDF text extracted via PyMuPDF native (fast path)")
            return native_text.strip()

        # Attempt 2: OCR fallback (image-based PDFs)
        log.info("No native text found, falling back to Tesseract OCR")
        ocr_text = ""
        for page in doc:
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text += pytesseract.image_to_string(img, lang="eng") + "\n"

        doc.close()
        return ocr_text.strip()

    except Exception as e:
        log.error(f"PDF text extraction failed: {e}")
        return ""