"""
Invoice Batch Ingestion via Backend API
"""

import os
import json
import time
import logging
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PDF_INPUT_DIR   = BASE_DIR / "sample_data" / "input_pdfs"
CHECKPOINT_FILE = BASE_DIR / "ingest_checkpoint.json"

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
UPLOAD_ENDPOINT = f"{BACKEND_URL}/api/v1/upload"
HEALTH_ENDPOINT = f"{BACKEND_URL}/health"

DEFAULT_WORKERS = 3
REQUEST_TIMEOUT = 180

MIME_MAP = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "ingest_via_backend.log"),
    ],
)
log = logging.getLogger(__name__)

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


def check_backend():
    try:
        r = requests.get(HEALTH_ENDPOINT, timeout=5)
        if r.status_code == 200:
            log.info(f"Backend OK: {r.json()}")
            return True
        log.error(f"Backend health check failed: {r.status_code}")
        return False
    except Exception as e:
        log.error(f"Cannot reach backend at {BACKEND_URL}: {e}")
        log.error("Start backend first: cd backend && uvicorn app.main:app --reload --port 8000")
        return False


def upload_file(file_path, processed):
    filename = file_path.name

    if filename in processed:
        log.info(f"[SKIP] {filename}")
        return True

    try:
        log.info(f"[START] {filename}")

        ext = filename.rsplit(".", 1)[-1].lower()
        content_type = MIME_MAP.get(ext, "application/octet-stream")

        with open(file_path, "rb") as f:
            file_payload = {"file": (filename, f, content_type)}
            r = requests.post(UPLOAD_ENDPOINT, files=file_payload, timeout=REQUEST_TIMEOUT)

        if r.status_code in (200, 201):
            payload = r.json()
            data = payload.get("data", {})
            invoice_num = data.get("invoice_number", "?")
            confidence = data.get("confidence_score", 0)
            status = data.get("status", "ok")
            log.info(f"[DONE] {filename} -> {invoice_num} | conf={confidence} | {status}")
            processed.add(filename)
            save_checkpoint(processed)
            return True

        log.error(f"[FAIL] {filename}: HTTP {r.status_code} -> {r.text[:300]}")
        return False

    except requests.Timeout:
        log.error(f"[TIMEOUT] {filename} > {REQUEST_TIMEOUT}s")
        return False
    except Exception as e:
        log.error(f"[FAIL] {filename}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--reset-checkpoint", action="store_true")
    args = parser.parse_args()

    PDF_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.reset_checkpoint and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        log.info("Checkpoint reset")

    if not check_backend():
        return

    processed = load_checkpoint()
    log.info(f"Already processed: {len(processed)}")

    extensions = ["*.pdf", "*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
    files = sorted([f for ext in extensions for f in PDF_INPUT_DIR.glob(ext)])
    remaining = [f for f in files if f.name not in processed]

    log.info(f"Input: {PDF_INPUT_DIR}")
    log.info(f"Total: {len(files)} | Remaining: {len(remaining)}")

    if not remaining:
        log.info("Nothing to process.")
        return

    success = 0
    failed = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(upload_file, f, processed): f for f in remaining}
        for future in as_completed(futures):
            try:
                if future.result():
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Unexpected: {e}")
                failed += 1

    elapsed = time.time() - start
    log.info("-" * 50)
    log.info(f"COMPLETE in {elapsed:.1f}s")
    log.info(f"Success: {success} | Failed: {failed} | Total: {success + failed}")
    if success > 0:
        log.info(f"Avg: {elapsed/success:.1f}s/file")


if __name__ == "__main__":
    main()