"""
Storage Service
---------------
Handles Supabase Storage for invoice PDFs and company branding assets.

Buckets:
  - "invoices"  (private)  → invoice PDFs, accessed via signed URLs
  - "branding"  (public)   → company logos, accessed via permanent public URLs
                             (signed URLs would expire and break embedded
                              images in already-rendered PDFs)

Paths:
  invoices: {company_id}/{company_name} - {invoice_number}.pdf
            (caller-provided via storage_path; falls back to
             {company_id}/{invoice_id}.pdf if not supplied)
  branding: {company_id}/logo.{ext}
"""

import logging

from supabase import Client

log = logging.getLogger(__name__)

BUCKET          = "invoices"
BRANDING_BUCKET = "branding"


def upload_invoice_pdf(
    db: Client,
    company_id: str,
    invoice_id: str,
    pdf_bytes: bytes,
    storage_path: str | None = None,
) -> str:
    """
    Upload an invoice PDF to the private "invoices" bucket.

    Args:
        db:           Supabase client.
        company_id:   Tenant UUID.
        invoice_id:   Invoice UUID — used as the filename in the
                      legacy fallback path only.
        pdf_bytes:    Raw PDF bytes.
        storage_path: Optional pre-computed path. When supplied, this is
                      written as-is. When None, the legacy UUID-based
                      path is used. Callers (invoice_processor) compose
                      "{company_id}/{company_name} - {invoice_number}.pdf"
                      so storage objects are human-readable.

    Uses upsert=True — re-ingestion overwrites cleanly.

    Returns:
        storage_path used for the upload.

    Raises:
        ValueError on upload failure.
    """
    if storage_path is None:
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
        raise ValueError(f"Failed to upload invoice PDF to storage: {e}")


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
        log.error(f"get_signed_url failed  path={storage_path}  error={e}")
        raise ValueError(f"Failed to generate signed URL: {e}")


def upload_branding_logo(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    ext: str,
) -> str:
    """
    Upload a company logo to the public "branding" bucket.

    Path: {company_id}/logo.{ext}
    Uses upsert=True — replaces previous logo cleanly.

    Args:
        db:         Supabase client.
        company_id: Tenant UUID.
        file_bytes: Raw image bytes.
        ext:        File extension without dot (png, jpg, jpeg, webp).

    Returns:
        Permanent public URL string.

    Raises:
        ValueError on upload failure or URL build failure.
    """
    content_type_map = {
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }
    storage_path = f"{company_id}/logo.{ext}"

    # ── Upload to storage ──
    try:
        db.storage.from_(BRANDING_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": content_type_map.get(ext, "image/png"),
                "upsert":       "true",
            },
        )
        log.info(f"Logo uploaded  bucket={BRANDING_BUCKET}  path={storage_path}")
    except Exception as e:
        log.error(f"upload_branding_logo failed  company_id={company_id}  error={e}")
        raise ValueError(f"Failed to upload logo: {e}")

    # ── Build permanent public URL ──
    # supabase-py may expose `supabase_url` as a httpx URL object rather than a
    # plain str. Wrap in str() so .rstrip() (and any other string method) works
    # regardless of the installed client version.
    try:
        supabase_url = str(db.supabase_url).rstrip("/")
        public_url = (
            f"{supabase_url}/storage/v1/object/public/"
            f"{BRANDING_BUCKET}/{storage_path}"
        )
    except Exception as e:
        log.error(f"upload_branding_logo url_build_failed  company_id={company_id}  error={e}")
        raise ValueError(f"Logo uploaded but URL build failed: {e}")

    return public_url