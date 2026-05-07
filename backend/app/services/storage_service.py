"""
Storage Service
---------------
Uploads invoice files to Supabase Storage bucket 'invoice-files'.

Two paths:
  Image (JPG/PNG/BMP/TIFF) → convert to PDF via img2pdf → upload as PDF
  PDF                      → upload as-is

Returns the storage path (e.g. "company-uuid/invoice-number.pdf")
which gets saved in invoice_raw_documents.storage_path.

To get the full public URL later:
  {SUPABASE_URL}/storage/v1/object/public/invoice-files/{storage_path}
"""

import io
import logging
import uuid

import img2pdf
from supabase import Client

log = logging.getLogger(__name__)

BUCKET_NAME = "invoice-files"


def _convert_image_to_pdf(image_bytes: bytes) -> bytes:
    """Convert image bytes (JPG/PNG/BMP/TIFF) to PDF bytes using img2pdf."""
    try:
        pdf_bytes = img2pdf.convert(image_bytes)
        return pdf_bytes
    except Exception as e:
        log.error(f"Image to PDF conversion failed: {e}")
        raise ValueError(f"Failed to convert image to PDF: {e}")


def upload_to_storage(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
    invoice_number: str | None = None,
) -> str:
    """
    Upload a file to Supabase Storage.

    For images: converts to PDF first, then uploads.
    For PDFs: uploads as-is.

    Args:
        db: Supabase client.
        company_id: Tenant company ID (used as folder prefix).
        file_bytes: Raw bytes of the uploaded file.
        filename: Original filename (used to detect file type).
        invoice_number: Optional invoice number for naming. Falls back to UUID.

    Returns:
        storage_path: The path in the bucket (e.g. "company-uuid/INV-001.pdf")
    """
    lower_name = filename.lower()
    is_image = lower_name.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff"))

    # Convert images to PDF
    if is_image:
        pdf_bytes = _convert_image_to_pdf(file_bytes)
        content_type = "application/pdf"
    else:
        pdf_bytes = file_bytes
        content_type = "application/pdf"

    # Build storage path: company_id/filename.pdf
    safe_name = invoice_number or filename.rsplit(".", 1)[0]
    # Remove characters that cause issues in storage paths
    safe_name = safe_name.replace("/", "-").replace("\\", "-").replace(" ", "_")
    storage_path = f"{company_id}/{safe_name}.pdf"

    # Check if file already exists at this path — add UUID suffix if so
    try:
        existing = db.storage.from_(BUCKET_NAME).list(company_id)
        existing_names = [f["name"] for f in existing] if existing else []
        if f"{safe_name}.pdf" in existing_names:
            unique_suffix = uuid.uuid4().hex[:8]
            storage_path = f"{company_id}/{safe_name}_{unique_suffix}.pdf"
    except Exception:
        # If list fails, proceed with original path — upload will overwrite or fail clearly
        pass

    # Upload
    try:
        db.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": content_type},
        )
        log.info(f"File uploaded to storage: {storage_path}")
        return storage_path
    except Exception as e:
        log.error(f"Storage upload failed: {e}")
        raise ValueError(f"Failed to upload to storage: {e}")


def get_public_url(supabase_url: str, storage_path: str) -> str:
    """
    Build the full public URL for a stored file.

    Args:
        supabase_url: Base Supabase URL (e.g. https://xxx.supabase.co)
        storage_path: Path returned by upload_to_storage.

    Returns:
        Full public URL to the file.
    """
    return f"{supabase_url}/storage/v1/object/public/{BUCKET_NAME}/{storage_path}"