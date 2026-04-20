"""
Invoice Ingestion Pipeline
--------------------------
Modes:
  --mode image   reads from sample_data/input_images/  (JPG -> PDF -> text -> OpenAI -> Supabase)
  --mode pdf     reads from sample_data/input_pdfs/    (PDF -> text -> OpenAI -> Supabase)

Features:
- Batch processing with threading (10 concurrent OpenAI calls)
- Checkpoint system (resume from last processed file)
- Single test company auto-created if not exists
- Stores: image_binary, pdf_binary, raw_text, extraction_json in Supabase
"""

import os
import json
import uuid
import time
import base64
import logging
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import img2pdf
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

IMAGE_INPUT_DIR = BASE_DIR / "sample_data" / "input_images"
PDF_INPUT_DIR   = BASE_DIR / "sample_data" / "input_pdfs"
PDF_OUTPUT_DIR  = BASE_DIR / "sample_data" / "pdf_data"
CHECKPOINT_FILE = BASE_DIR / "ingest_checkpoint.json"

SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY   = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MAX_WORKERS       = 3  # Reduced to stay within 30k TPM rate limit
TEST_COMPANY_NAME = "Test Company"

# Tesseract path (Windows)
pytesseract.pytesseract.tesseract_cmd = r"D:\tess\tesseract.exe"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "ingest.log"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Extraction Prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are an expert financial document parser specialized in extracting structured data from invoices.

Your task is to extract ALL relevant information from the provided invoice text and return ONLY a valid JSON object that strictly follows the schema below.

You MUST:
- Return ONLY valid JSON (no explanations, no text outside JSON)
- Fill all required fields
- Use null for missing optional values
- Ensure all numeric fields are numbers (not strings)
- Ensure all dates follow YYYY-MM-DD format
- Ensure totals are mathematically consistent
- Do not hallucinate values — if unsure, use null

If data is inconsistent:
- Still return best-effort values
- Do NOT fix numbers silently
- Let totals reflect the document, even if incorrect

### EXTRACTION RULES:
1. Currency: always return ISO code (USD, EUR, TRY). If you see $ infer USD, € infer EUR, ₺ infer TRY. Never return the symbol itself.
2. For addresses in format "City, STATE ZIP": extract city before the comma, state code after the comma, 5-digit number as postal_code. If no country is written figure the country based on the state code and write as 3-letter ISO abbreviation (like USA, KSA, EGY, DEN, FIN, BAH). Always use exactly 3 letters.
3. If a field is genuinely absent from the document, return null. Do not hallucinate.

### JSON SCHEMA:
{
  "schema_version": "1.0",
  "document_metadata": {
    "document_type": "invoice",
    "extraction_timestamp": "ISO-8601",
    "confidence_score": 0.0
  },
  "invoice": {
    "invoice_number": "string",
    "issue_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD or null",
    "currency": "string",
    "tax_percent": 0.0,
    "subtotal": 0.0,
    "total_tax": 0.0,
    "grand_total": 0.0,
    "payment_method": "string or null",
    "description": "string or null",
    "discount": 0.0,
    "status": "draft"
  },
  "vendor": {
    "name": "string",
    "tax_id": "string",
    "email": "string or null",
    "phone": "string or null",
    "address": {
      "street": "string or null",
      "city": "string or null",
      "state": "string or null",
      "postal_code": "string or null",
      "country": "string or null"
    }
  },
  "client": {
    "name": "string",
    "tax_id": "string",
    "email": "string or null",
    "phone": "string or null",
    "address": {
      "street": "string or null",
      "city": "string or null",
      "state": "string or null",
      "postal_code": "string or null",
      "country": "string or null"
    }
  },
  "line_items": [
    {
      "description": "string",
      "quantity": 0.0,
      "unit_price": 0.0,
      "line_subtotal": 0.0,
      "discount": 0.0
    }
  ],
  "payments": [
    {
      "payment_date": "YYYY-MM-DD",
      "amount": 0.0,
      "method": "string or null",
      "reference": "string or null"
    }
  ]
}

Return ONLY the JSON object. No markdown. No explanation.

### INPUT TEXT:
"""

# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

checkpoint_lock = threading.Lock()


def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            return set(json.load(f).get("processed", []))
    return set()


def save_checkpoint(processed: set):
    with checkpoint_lock:
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump({"processed": list(processed)}, f)


# ---------------------------------------------------------------------------
# Step 1: Image -> PDF
# ---------------------------------------------------------------------------

def convert_image_to_pdf(image_path: Path) -> Path:
    PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_OUTPUT_DIR / (image_path.stem + ".pdf")
    if not pdf_path.exists():
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(str(image_path)))
    return pdf_path


# ---------------------------------------------------------------------------
# Step 2: Image -> raw text via Tesseract OCR
# ---------------------------------------------------------------------------

def extract_text_from_image(image_path: Path) -> str:
    image = Image.open(str(image_path))
    text = pytesseract.image_to_string(image, lang="eng")
    return text.strip()


# ---------------------------------------------------------------------------
# Step 2b: PDF -> raw text via Tesseract OCR (pdf mode)
# Converts each PDF page to image first, then runs OCR
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    full_text = ""
    for page in doc:
        # Render page to image at 300 DPI for good OCR quality
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        full_text += pytesseract.image_to_string(img, lang="eng") + "\n"
    doc.close()
    return full_text.strip()


# ---------------------------------------------------------------------------
# Step 3: OpenAI text extraction
# ---------------------------------------------------------------------------

def extract_invoice_data(raw_text: str, openai_client: OpenAI) -> dict:
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                max_tokens=2000,
                messages=[{"role": "user", "content": EXTRACTION_PROMPT + raw_text}],
            )

            content = response.choices[0].message.content.strip()

            # Strip markdown fences if model ignores instructions
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            return json.loads(content)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                wait = 60  # wait 60 seconds on rate limit
                log.warning(f"Rate limit hit, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Step 4: Supabase insertions
# ---------------------------------------------------------------------------

def get_or_create_company(supabase: Client) -> str:
    result = supabase.table("companies").select("id").eq("name", TEST_COMPANY_NAME).execute()
    if result.data:
        return result.data[0]["id"]
    insert = supabase.table("companies").insert({"name": TEST_COMPANY_NAME}).execute()
    company_id = insert.data[0]["id"]
    log.info(f"Created test company: {company_id}")
    return company_id


def insert_address(supabase: Client, company_id: str, address: dict) -> str | None:
    if not any([address.get("street"), address.get("city"), address.get("postal_code"), address.get("country"), address.get("state")]):
        return None
    result = supabase.table("addresses").insert({
        "company_id": company_id,
        "street":      address.get("street"),
        "city":        address.get("city"),
        "state":       address.get("state"),
        "postal_code": address.get("postal_code"),
        "country":     address.get("country"),
    }).execute()
    return result.data[0]["id"]


def insert_vendor(supabase: Client, company_id: str, vendor: dict) -> str:
    result = supabase.table("vendors").insert({
        "company_id": company_id,
        "name":   vendor.get("name", "Unknown Vendor"),
        "tax_id": vendor.get("tax_id") or "N/A",
        "email":  vendor.get("email"),
        "phone":  vendor.get("phone"),
    }).execute()
    return result.data[0]["id"]


def insert_client(supabase: Client, company_id: str, client: dict) -> str:
    result = supabase.table("clients").insert({
        "company_id": company_id,
        "name":   client.get("name", "Unknown Client"),
        "tax_id": client.get("tax_id") or "N/A",
        "email":  client.get("email"),
        "phone":  client.get("phone"),
    }).execute()
    return result.data[0]["id"]


def insert_invoice(
    supabase: Client,
    company_id: str,
    extraction: dict,
    vendor_id: str,
    client_id: str,
    vendor_address_id: str | None,
    client_address_id: str | None,
    confidence_score: float,
) -> str:
    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number", f"UNKNOWN-{uuid.uuid4().hex[:8]}")

    # Check if already exists
    existing = supabase.table("invoices").select("id")\
        .eq("company_id", company_id)\
        .eq("invoice_number", invoice_number)\
        .execute()
    if existing.data:
        return existing.data[0]["id"]

    issue_date = inv.get("issue_date") or "1900-01-01"
    result = supabase.table("invoices").insert({
        "company_id":        company_id,
        "invoice_number":    invoice_number,
        "issue_date":        issue_date,
        "due_date":          inv.get("due_date"),
        "currency":          inv.get("currency", "USD"),
        "tax_percent":       inv.get("tax_percent", 0),
        "subtotal":          inv.get("subtotal", 0),
        "total_tax":         inv.get("total_tax", 0),
        "grand_total":       inv.get("grand_total", 0),
        "payment_method":    inv.get("payment_method"),
        "description":       inv.get("description"),
        "discount":          inv.get("discount", 0),
        "status":            "draft",
        "vendor_id":         vendor_id,
        "client_id":         client_id,
        "vendor_address_id": vendor_address_id,
        "client_address_id": client_address_id,
        "confidence_score":  confidence_score,
    }).execute()
    return result.data[0]["id"]


def insert_line_items(supabase: Client, company_id: str, invoice_id: str, line_items: list):
    if not line_items:
        return
    rows = [{
        "company_id":    company_id,
        "invoice_id":    invoice_id,
        "description":   item.get("description", ""),
        "quantity":      item.get("quantity", 1),
        "unit_price":    item.get("unit_price", 0),
        "line_subtotal": item.get("line_subtotal", 0),
        "discount":      item.get("discount", 0),
    } for item in line_items]
    supabase.table("line_items").insert(rows).execute()


def insert_payments(supabase: Client, company_id: str, invoice_id: str, payments: list):
    if not payments:
        return
    rows = [{
        "company_id":   company_id,
        "invoice_id":   invoice_id,
        "payment_date": p.get("payment_date"),
        "amount":       p.get("amount", 0),
        "method":       p.get("method"),
        "reference":    p.get("reference"),
    } for p in payments if p.get("payment_date")]
    if rows:
        supabase.table("payments").insert(rows).execute()


def insert_raw_document(
    supabase: Client,
    company_id: str,
    invoice_id: str,
    raw_text: str,
    extraction: dict,
    pdf_binary: bytes,
    image_binary: bytes | None,
):
    supabase.table("invoice_raw_documents").insert({
        "company_id":      company_id,
        "invoice_id":      invoice_id,
        "raw_text":        raw_text,
        "extraction_json": extraction,
        "schema_version":  "1.0",
        "pdf_binary":      pdf_binary.decode("latin-1"),
        "image_binary":    image_binary.decode("latin-1") if image_binary else None,
    }).execute()


# ---------------------------------------------------------------------------
# Full pipeline per file
# ---------------------------------------------------------------------------

def process_single_file(
    file_path: Path,
    mode: str,
    company_id: str,
    openai_client: OpenAI,
    supabase: Client,
    processed: set,
) -> bool:
    filename = file_path.name

    if filename in processed:
        log.info(f"[SKIP] {filename}")
        return True

    try:
        log.info(f"[START] {filename}")

        image_binary = None

        if mode == "image":
            with open(file_path, "rb") as f:
                image_binary = f.read()
            pdf_path = convert_image_to_pdf(file_path)

            # OCR directly on original image (faster, better quality than PDF render)
            raw_text = extract_text_from_image(file_path)
        else:
            pdf_path = file_path
            raw_text = extract_text_from_pdf(pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_binary = f.read()

        if not raw_text.strip():
            log.warning(f"[WARN] No text extracted from {filename} — skipping")
            return False

        extraction = extract_invoice_data(raw_text, openai_client)
        confidence = extraction.get("document_metadata", {}).get("confidence_score", 0.8)

        vendor_address_id = insert_address(supabase, company_id, extraction.get("vendor", {}).get("address", {}))
        client_address_id = insert_address(supabase, company_id, extraction.get("client", {}).get("address", {}))
        vendor_id         = insert_vendor(supabase, company_id, extraction.get("vendor", {}))
        client_id         = insert_client(supabase, company_id, extraction.get("client", {}))

        invoice_id = insert_invoice(
            supabase, company_id, extraction,
            vendor_id, client_id,
            vendor_address_id, client_address_id,
            confidence,
        )

        insert_line_items(supabase, company_id, invoice_id, extraction.get("line_items", []))
        insert_payments(supabase, company_id, invoice_id, extraction.get("payments", []))
        insert_raw_document(
            supabase, company_id, invoice_id,
            raw_text, extraction,
            pdf_binary, image_binary,
        )

        processed.add(filename)
        save_checkpoint(processed)

        log.info(f"[DONE] {filename} -> invoice_id: {invoice_id}")
        return True

    except Exception as e:
        log.error(f"[FAIL] {filename}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Invoice Ingestion Pipeline")
    parser.add_argument(
        "--mode",
        choices=["image", "pdf"],
        required=True,
        help="image: JPG->PDF->text->DB  |  pdf: PDF->text->DB",
    )
    args = parser.parse_args()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY must be set in .env")

    input_dir    = IMAGE_INPUT_DIR if args.mode == "image" else PDF_INPUT_DIR
    glob_pattern = "*.jpg"         if args.mode == "image" else "*.pdf"
    input_dir.mkdir(parents=True, exist_ok=True)

    openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    company_id = get_or_create_company(supabase)
    log.info(f"Using company_id: {company_id}")

    processed = load_checkpoint()
    log.info(f"Already processed: {len(processed)}")

    files     = sorted(input_dir.glob(glob_pattern))
    remaining = [f for f in files if f.name not in processed]
    log.info(f"Total: {len(files)} | Remaining: {len(remaining)}")

    if not remaining:
        log.info("Nothing to process.")
        return

    success = 0
    failed  = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                process_single_file,
                f, args.mode, company_id, openai_client, supabase, processed
            ): f
            for f in remaining
        }
        for future in as_completed(futures):
            try:
                if future.result():
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Unexpected error: {e}")
                failed += 1

    log.info("--- INGESTION COMPLETE ---")
    log.info(f"Success: {success} | Failed: {failed} | Total: {success + failed}")


if __name__ == "__main__":
    main()