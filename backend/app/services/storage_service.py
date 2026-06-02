"""
Storage Service
---------------
Handles Supabase Storage for payable invoice PDFs.

Bucket: "invoices" (private)
Path:   {company_id}/{invoice_id}.pdf

upload_invoice_pdf() — uploads a payable PDF, keyed by invoice_id
get_signed_url()     — generates a 5-minute signed URL for retrieval
"""

import logging

from supabase import Client

log = logging.getLogger(__name__)

BUCKET = "invoices"


def upload_invoice_pdf(
    db: Client,
    company_id: str,
    invoice_id: str,
    pdf_bytes: bytes,
) -> str:
    """
    Upload a payable invoice PDF to the private "invoices" bucket.

    Path: {company_id}/{invoice_id}.pdf
    Uses upsert=True — re-ingestion overwrites cleanly.

    Args:
        db:          Supabase client.
        company_id:  Tenant UUID.
        invoice_id:  Invoice UUID — used as the filename.
        pdf_bytes:   Raw PDF bytes.

    Returns:
        storage_path: "{company_id}/{invoice_id}.pdf"

    Raises:
        ValueError on upload failure.
    """
    storage_path = f"{company_id}/{invoice_id}.pdf"

    try:
        db.storage.from_(BUCKET).upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={
                "content-type": "application/pdf",
                "upsert":        "true",
            },
        )
        log.info(f"PDF uploaded  bucket={BUCKET}  path={storage_path}")
        return storage_path
    except Exception as e:
        log.error(f"upload_invoice_pdf failed  invoice_id={invoice_id}  error={e}")
        raise ValueError(f"Failed to upload payable PDF to storage: {e}")


def get_signed_url(
    db: Client,
    storage_path: str,
    expires_in: int = 300,
) -> str:
    """
    Generate a signed URL for a file in the "invoices" bucket.

    Args:
        db:           Supabase client.
        storage_path: Path returned by upload_invoice_pdf.
        expires_in:   Seconds until expiry (default 5 minutes).

    Returns:
        Signed URL string.

    Raises:
        ValueError if signed URL cannot be generated.
    """
    try:
        result = db.storage.from_(BUCKET).create_signed_url(
            storage_path, expires_in
        )
        signed_url = (
            result.get("signedURL")
            or result.get("signedUrl")
            or result.get("signed_url")
        )
        if not signed_url:
            raise ValueError(f"Signed URL not found in response: {result}")
        return signed_url
    except ValueError:
        raise
    except Exception as e:
        log.error ( f"get_signed_url failed  path={storage_path}  error={e}")
        raise ValueError(f"Failed to generate signed URL: {e}")