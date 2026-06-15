"""
OCR Service
-----------
Extracts text from invoice files.

extract_text_from_pdf returns (text, used_fallback) so callers can detect
when Tesseract was invoked vs. PyMuPDF native — used by the compliance
ocr_fallback_used flag.

extract_text_from_image always uses Tesseract — there is no fallback
concept for images, so it returns text only.
"""

import io
import logging

import fitz
import pytesseract
from PIL import Image

from app.core.config import get_settings

log = logging.getLogger(__name__)


def _configure_tesseract():
    settings = get_settings()
    if settings.TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH


def extract_text_from_image(file_bytes: bytes) -> str:
    _configure_tesseract()
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image, lang="eng")
        return text.strip()
    except Exception as e:
        log.error(f"Image OCR failed: {e}")
        return ""


def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, bool]:
    """
    Returns (text, used_tesseract_fallback).

    used_tesseract_fallback is True only when PyMuPDF native returned
    empty/whitespace and we had to rasterize + OCR each page.
    """
    _configure_tesseract()
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        native_text = ""
        for page in doc:
            native_text += page.get_text() + "\n"

        if native_text.strip():
            doc.close()
            log.info("PDF text extracted via PyMuPDF native")
            return native_text.strip(), False

        log.info("No native text — using Tesseract fallback")
        ocr_text = ""
        for page in doc:
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text += pytesseract.image_to_string(img, lang="eng") + "\n"

        doc.close()
        return ocr_text.strip(), True

    except Exception as e:
        log.error(f"PDF text extraction failed: {e}")
        return "", False