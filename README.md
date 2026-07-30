# InVox — AI-Driven Invoice Intelligence System

A full-stack invoice management and financial intelligence platform combining OCR-based document ingestion, LLM extraction, RAG-powered natural language querying, compliance monitoring, and analytics — built with FastAPI, React, and Supabase.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Running the Backend](#running-the-backend)
- [Running the Frontend](#running-the-frontend)
- [AI Provider Configuration](#ai-provider-configuration)
  - [OpenAI (default)](#openai-default)
  - [Gemini](#gemini)
  - [Ollama (local)](#ollama-local)
  - [Grok](#grok)
- [Reranker Configuration](#reranker-configuration)
  - [Cohere](#cohere)
  - [BGE (local)](#bge-local)
- [Switching Models via Config](#switching-models-via-config)
- [Database Setup (Supabase)](#database-setup-supabase)
- [Seeding the Database](#seeding-the-database)
- [Embedding Backfill](#embedding-backfill)
- [Key Features](#key-features)
- [API Reference](#api-reference)
- [Compliance Engine](#compliance-engine)
- [RAG Query Pipeline](#rag-query-pipeline)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)

---

## Overview

InVox automates the full invoice lifecycle for both accounts payable and accounts receivable:

- **Payable invoices** are uploaded as PDFs or images, run through OCR, and structured by an LLM — no manual data entry.
- **Receivable invoices** are created via a form, generating a branded PDF automatically.
- A **natural language query interface** lets users ask questions like _"What did we spend on vendors last quarter?"_ and receive grounded, cited answers.
- A **compliance engine** continuously validates invoices for tax mismatches, missing fields, duplicates, and overdue status.
- An **analytics dashboard** provides spending, revenue, trend, and aging breakdowns.

The system was validated on a dataset of 253 invoices (102 payable via OCR, 151 receivable via form) across 10 vendors and 8 clients over a 13-month period.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│               React Frontend (Vite)             │
│  Dashboard · Invoices · AI Chat · Analytics     │
└───────────────────┬─────────────────────────────┘
                    │ REST /api/v1
┌───────────────────▼─────────────────────────────┐
│              FastAPI Backend                    │
│  Routers → Services → Provider Abstraction      │
│  (invoices, upload, query, analytics, ...)      │
└───────┬──────────────────────┬──────────────────┘
        │                      │
┌───────▼──────┐     ┌─────────▼────────┐
│  Supabase    │     │   AI Providers   │
│  PostgreSQL  │     │  OpenAI / Gemini │
│  + pgvector  │     │  Ollama / Grok   │
│  + Storage   │     │  Cohere / BGE    │
└──────────────┘     └──────────────────┘
```

The backend uses a **thin router, fat service** pattern. Routers handle HTTP concerns only; all domain logic lives in service modules. The AI layer is provider-agnostic — swap models via a single environment variable with no code changes.

---

## Tech Stack

| Layer          | Technology                                         |
| -------------- | -------------------------------------------------- |
| Frontend       | React 18, Vite 5, Tailwind CSS, Recharts           |
| Backend        | FastAPI, Python 3.11+, APScheduler                 |
| Database       | Supabase (PostgreSQL + pgvector + Storage)         |
| OCR            | PyMuPDF (primary), Tesseract (fallback)            |
| LLM            | OpenAI GPT-4o / Gemini / Ollama / Grok             |
| Embeddings     | text-embedding-3-small / nomic-embed-text (Ollama) |
| Reranking      | Cohere rerank-v3.5 / BGE (local)                   |
| PDF Generation | ReportLab                                          |

---

## Project Structure

```
CP_PROJ/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                  # FastAPI entrypoint, router registration, scheduler
│       ├── core/
│       │   ├── config.py            # All settings via Pydantic + .env
│       │   ├── exceptions.py        # Custom domain exceptions
│       │   └── supabase.py          # Service-role Supabase client
│       ├── models/
│       │   └── schemas.py           # Pydantic request/response schemas
│       ├── providers/               # AI provider abstraction layer
│       │   ├── base.py              # Abstract interfaces for LLM + embedding
│       │   ├── openai_provider.py
│       │   ├── gemini_provider.py
│       │   ├── grok_provider.py
│       │   ├── ollama_provider.py
│       │   ├── cohere_reranker.py
│       │   └── bge_reranker.py
│       ├── routers/                 # HTTP layer (thin)
│       │   ├── invoices.py
│       │   ├── upload.py
│       │   ├── query.py
│       │   ├── analytics.py
│       │   ├── documents.py
│       │   ├── clients.py
│       │   ├── vendors.py
│       │   ├── notifications.py
│       │   ├── payments.py
│       │   ├── settings.py
│       │   └── admin.py
│       └── services/                # Business logic layer (fat)
│           ├── invoice_processor.py  # 9-stage payable ingestion pipeline
│           ├── invoice_service.py    # Invoice CRUD + state machine
│           ├── ocr_service.py        # PyMuPDF + Tesseract OCR
│           ├── extraction_service.py # LLM structured extraction
│           ├── embedding_service.py  # Vector chunk generation + storage
│           ├── query_service.py      # RAG + SQL query engine
│           ├── intent_classifier.py  # Keyword pre-filter + LLM classifier
│           ├── compliance_service.py # Rule-based compliance checks + flags
│           ├── analytics_service.py  # Aggregation metrics
│           ├── document_service.py   # Regulatory PDF chunking + embedding
│           ├── receivable_pdf_renderer.py  # Branded invoice PDF generation
│           ├── storage_service.py    # Supabase Storage uploads
│           ├── overdue_service.py    # Nightly overdue detection
│           └── retrieval/            # RAG retrieval sources + registry
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                  # Router + auth gate
│       ├── context/
│       │   ├── ChatContext.jsx      # AI chat state
│       │   └── ThemeContext.jsx
│       ├── lib/
│       │   └── api.js               # Centralized API client
│       └── pages/
│           ├── Dashboard.jsx
│           ├── AiChat.jsx
│           ├── Analytics.jsx
│           ├── Invoices.jsx / Payables.jsx / Receivables.jsx
│           ├── InvoiceDetail.jsx
│           ├── CreateInvoice.jsx
│           ├── UploadExtract.jsx
│           ├── CompanyDocuments.jsx
│           ├── Vendors.jsx / Clients.jsx
│           └── Settings.jsx
├── sample_data/
│   ├── dataset.json
│   ├── generate_dataset.py
│   ├── render_pdfs.py
│   └── payable_pdfs/ receivable_pdfs/ template_1/ ... template_5_freelance/
└── backend/scripts/
    ├── seed_database.py
    ├── backfill_embeddings.py
    ├── refresh_all_headers.py
    └── test_providers.py
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A [Supabase](https://supabase.com) project with pgvector enabled
- Tesseract OCR installed on your OS
- At least one AI provider API key (OpenAI, Gemini, or a running Ollama instance)

**Install Tesseract:**

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract

# Windows — download installer from https://github.com/tesseract-ocr/tesseract
```

---

## Environment Setup

Copy the example environment file and fill in your values:

```bash
cd backend
cp .env.example .env
```

**Core `.env` variables:**

```env
# App
APP_NAME=InVox
DEBUG=false
API_V1_PREFIX=/api/v1
CORS_ORIGINS=["http://localhost:5173"]

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# Tenant (multi-tenant MVP)
MVP_COMPANY_ID=your-company-uuid

# AI Providers — set LLM_PROVIDER to one of: openai | gemini | grok | ollama
LLM_PROVIDER=gemini

# OpenAI
OPENAI_API_KEY=sk-...

# Gemini
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-1.5-flash

# Grok
GROK_API_KEY=your-grok-key
GROK_MODEL=grok-beta

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text/bge-m3

# Reranker — set RERANKER_PROVIDER to: cohere | bge
RERANKER_PROVIDER=bge

# Cohere
COHERE_API_KEY=your-cohere-key

# OCR
TESSERACT_CMD=/usr/bin/tesseract   # path to your tesseract binary
```

---

## Running the Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start the server (without --reload when using the scheduler)
uvicorn app.main:app --port 8000

# Development (manual restarts required — see note below)
uvicorn app.main:app --port 8000 --reload
```

> **Note on `--reload` and the scheduler:** APScheduler (which runs the nightly overdue check) conflicts with Uvicorn's `--reload` flag because `--reload` spawns child processes, causing the scheduler to initialize multiple times. Do not use `--reload` in any environment where you need the scheduler to work correctly. Restart the server manually during development instead.

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/health` to confirm Supabase connectivity.

---

## Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

The frontend reads `VITE_API_BASE_URL` from a `.env` file in the `frontend/` directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

---

## AI Provider Configuration

All provider switching is done through the `LLM_PROVIDER` variable in `backend/.env`. No code changes are needed.

### OpenAI (default)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Uses `gpt-4o` for extraction and query answering, and `text-embedding-3-small` (1536-dim) for embeddings.

### Gemini

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-x.x-flash      # or gemini-x.x-pro
```

Gemini is fully supported for extraction, intent classification, query answering, and multi-query rewriting. Tested and confirmed working.

### Ollama (local)

Install [Ollama](https://ollama.ai) and pull the models you want:

```bash
ollama pull llama3:8b
ollama pull bge-m3
```

Then configure:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_EMBED_MODEL=bge-m3
```

Ollama is confirmed working for extraction, intent classification, and query answering. Embedding vectors from `nomic-embed-text` are 768-dimensional and are zero-padded to 1536 to match the database column. This is mathematically valid for cosine similarity but represents a known quality trade-off versus the OpenAI embeddings.
Currently the setup is using Bge-m3 embedder as a singular embedding model to avoid dimensional mismatches, we recommend whoever tries this project to stick to one model as you have to re populate the database with those embeddings each time you change the embedder, or build it to where your db can have both formats.

### Grok

```env
LLM_PROVIDER=grok
GROK_API_KEY=your-key
GROK_MODEL=grok-beta
```

Grok uses an OpenAI-compatible API. Not yet personally tested by the team — use with caution and verify extraction output quality before trusting it in production.

---

## Reranker Configuration

### Cohere

```env
RERANKER_PROVIDER=cohere
COHERE_API_KEY=your-key
```

Uses `rerank-v3.5` (cross-encoder). Provides the highest reranking quality.

### BGE (local)

```env
RERANKER_PROVIDER=bge
```

Uses a locally-running BGE reranker. No API key required. Tested and confirmed working. Slightly lower quality than Cohere but fully offline and free.

---

## Switching Models via Config

The table below shows every AI decision point and how to control it:

| What it controls                             | Environment variable         | Options                                                      |
| -------------------------------------------- | ---------------------------- | ------------------------------------------------------------ |
| LLM for extraction, querying, classification | `LLM_PROVIDER`               | `openai`, `gemini`, `ollama`, `grok`                         |
| Embedding model                              | Determined by `LLM_PROVIDER` | OpenAI: `text-embedding-3-small`; Ollama: `nomic-embed-text` |
| Gemini model                                 | `GEMINI_MODEL`               | `gemini-1.5-flash`, `gemini-1.5-pro`, etc.                   |
| Ollama chat model                            | `OLLAMA_MODEL`               | `llama3:8b`, `mistral`, etc.                                 |
| Ollama embed model                           | `OLLAMA_EMBED_MODEL`         | `nomic-embed-text`, etc.                                     |
| Reranker                                     | `RERANKER_PROVIDER`          | `cohere`, `bge`                                              |

After changing any of these, restart the backend. No database migration or code change is required.

---

## Database Setup (Supabase)

1. Create a new Supabase project.
2. Enable the `pgvector` extension: in the Supabase dashboard go to **Database → Extensions** and enable `vector`.
3. Run the schema SQL from `backend/scripts/schema.sql` (or the migration files in your project) in the Supabase SQL editor to create all 15 tables.
4. Copy your **Project URL** and **service role key** (from **Settings → API**) into `backend/.env`.

> The backend uses a **service-role key** which bypasses row-level security. All tenant isolation is enforced at the application layer via `company_id` filtering. This is appropriate for the multi-tenant MVP. Do not expose this key to the frontend.

---

## Seeding the Database

To populate the database with the synthetic 253-invoice dataset for testing:

```bash
cd backend
python scripts/seed_database.py
```

To generate and render the synthetic PDF invoices from scratch (requires ReportLab):

```bash
cd sample_data
python generate_dataset.py
python render_pdfs.py
```

---

## Embedding Backfill

If you add invoices outside the normal upload pipeline, or switch embedding models, run the backfill to generate/refresh embeddings for all invoices:

```bash
cd backend
python scripts/backfill_embeddings.py

# To reset all embeddings and regenerate from scratch:
python scripts/reset_and_backfill_embeddings.py

# To refresh only the header chunk (status/payment-sensitive chunk) for all invoices:
python scripts/refresh_all_headers.py
```

> Header chunks are automatically refreshed after status transitions and payment events via the invoice service. The backfill scripts are for bulk operations only.

---

## Key Features

### Payable Invoice Ingestion (9-stage pipeline)

1. File validation (PDF, JPG, PNG, BMP, TIFF — max 20 MB)
2. OCR: PyMuPDF native text extraction → Tesseract fallback at 300 DPI
3. LLM structured extraction with retry logic (up to 5 attempts, markdown fence stripping)
4. Vendor resolution (tax ID exact match → name ILIKE partial match → unmatched flag)
5. Duplicate detection (same invoice number + vendor → compliance flag, no duplicate record)
6. Database write (invoices, line items, payments tables)
7. PDF upload to Supabase Storage at human-readable path `{company_id}/{company_name} - {invoice_number}.pdf`
8. Raw document record insertion
9. Embedding generation (3-chunk strategy) + compliance validation

Manual invoice data entry: ~90 seconds. Automated extraction pipeline: ~11 seconds.

### Receivable Invoice Generation

- Form-based creation with line items, tax rate, currency, due date
- Auto-assigned invoice numbers: `REC-{YYYY}-{N:04d}`
- Branded PDF rendered via ReportLab (logo, brand colors, line item table, totals)
- Logo stored in a public bucket with permanent URLs (no signed URL expiry issues)

### AI Query Interface

Four query modes handled through a unified endpoint (`POST /api/v1/query`):

- **SQL aggregation** — totals, counts, averages, rankings, monthly breakdowns (18 templates, no raw SQL generated by the LLM)
- **RAG invoice** — semantic search over invoice content and line items
- **RAG compliance** — semantic search over uploaded regulatory documents
- **Hybrid** — cross-references invoice data against regulatory requirements

### Three-Chunk Embedding Strategy

Each invoice is stored as three distinct embedding chunks:

- **Header chunk** (index 0): metadata, status, totals, dates, party — refreshed on status changes
- **Line items chunk** (index 1): per-line descriptions, quantities, unit prices
- **Full text chunk** (index 2): head (65%) + tail (35%) of raw OCR text

### Compliance Engine (5 checks)

| Check                     | Severity | Condition                                          |
| ------------------------- | -------- | -------------------------------------------------- |
| `tax_mismatch`            | High     | subtotal + tax ≠ grand total (±0.01)               |
| `missing_required_fields` | Medium   | missing due date, invoice number, or party ID      |
| `duplicate_invoice`       | High     | same invoice number + same vendor/client ID exists |
| `line_item_mismatch`      | Medium   | sum of line subtotals ≠ invoice subtotal (±0.01)   |
| `overdue_no_action`       | Low      | overdue >30 days with no payment recorded          |

Flags are upserted on every create/update and auto-resolved when the violation is corrected.

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

### Invoices

| Method | Endpoint                          | Description                                    |
| ------ | --------------------------------- | ---------------------------------------------- |
| POST   | `/invoices/`                      | Create invoice (payable or receivable)         |
| GET    | `/invoices/`                      | List invoices (filter by status, type, search) |
| GET    | `/invoices/{id}`                  | Get invoice detail                             |
| PATCH  | `/invoices/{id}`                  | Update invoice                                 |
| DELETE | `/invoices/{id}`                  | Soft delete                                    |
| GET    | `/invoices/{id}/line-items`       | Line items                                     |
| GET    | `/invoices/{id}/payments`         | Payment history                                |
| GET    | `/invoices/{id}/raw-document`     | Raw OCR/extraction metadata                    |
| GET    | `/invoices/{id}/compliance-flags` | Active compliance flags                        |
| POST   | `/invoices/{id}/validate`         | Manually trigger compliance validation         |
| POST   | `/invoices/{id}/transition`       | Status transition (state machine enforced)     |
| GET    | `/invoices/{id}/pdf`              | Signed PDF URL redirect                        |
| POST   | `/invoices/{id}/payments`         | Record a payment                               |
| POST   | `/invoices/{id}/credit-note`      | Apply credit note                              |
| POST   | `/invoices/{id}/refund`           | Process refund                                 |

### Upload

| Method | Endpoint        | Description                               |
| ------ | --------------- | ----------------------------------------- |
| POST   | `/upload`       | Upload single invoice file (payable only) |
| POST   | `/upload/batch` | Upload multiple files sequentially        |

### Query (AI Assistant)

| Method | Endpoint | Description                                  |
| ------ | -------- | -------------------------------------------- |
| POST   | `/query` | Natural language question → answer + sources |

### Analytics

| Method | Endpoint                    | Description                                           |
| ------ | --------------------------- | ----------------------------------------------------- |
| GET    | `/analytics/dashboard`      | Dashboard summary metrics                             |
| GET    | `/analytics/spending`       | Spending over time (`?months=6`)                      |
| GET    | `/analytics/revenue`        | Revenue over time (`?months=6`)                       |
| GET    | `/analytics/trends`         | Monthly trends (`?months=12&invoice_type=payable`)    |
| GET    | `/analytics/payment-timing` | Payment timing distribution                           |
| GET    | `/analytics/overdue`        | Overdue invoice stats                                 |
| GET    | `/analytics/system-stats`   | System-wide stats                                     |
| GET    | `/analytics/page-metrics`   | Metric cards for list pages (`?invoice_type=payable`) |

### Vendors & Clients

| Method | Endpoint                       | Description          |
| ------ | ------------------------------ | -------------------- |
| POST   | `/vendors/`                    | Create vendor        |
| GET    | `/vendors/`                    | List vendors         |
| GET    | `/vendors/{id}`                | Get vendor           |
| GET    | `/vendors/{id}/latest-address` | Latest known address |
| PATCH  | `/vendors/{id}`                | Update               |
| DELETE | `/vendors/{id}`                | Soft delete          |

Same pattern applies to `/clients/`.

### Documents

| Method | Endpoint            | Description                       |
| ------ | ------------------- | --------------------------------- |
| POST   | `/documents/upload` | Upload regulatory/compliance PDF  |
| GET    | `/documents`        | List documents                    |
| DELETE | `/documents/{id}`   | Delete document + embedded chunks |
| PATCH  | `/documents/{id}`   | Update metadata (type, country)   |

### Settings & Branding (settings is deprecated)

| Method    | Endpoint                  | Description                 |
| --------- | ------------------------- | --------------------------- |
| GET/PATCH | `/settings`               | Company profile settings    |
| POST      | `/settings/set-password`  | Set/clear settings password |
| GET/PATCH | `/settings/branding`      | Brand colors, footer text   |
| POST      | `/settings/branding/logo` | Upload company logo         |

### Admin & Notifications (deprecated)

| Method | Endpoint                      | Description                           |
| ------ | ----------------------------- | ------------------------------------- |
| POST   | `/admin/run-overdue-check`    | Manually trigger overdue detection    |
| POST   | `/admin/run-compliance-check` | Re-run compliance across all invoices |
| GET    | `/notifications`              | List notifications                    |
| POST   | `/notifications/{id}/read`    | Mark as read                          |
| POST   | `/notifications/read-all`     | Mark all as read                      |

### Health

| Method | Endpoint  | Description                 |
| ------ | --------- | --------------------------- |
| GET    | `/health` | Database connectivity check |

---

## Compliance Engine

The compliance service runs automatically after every invoice create, update, and status transition. It can also be triggered manually via the admin endpoint or from the invoice detail page.

The engine uses **upsert logic**: if a check finds a violation and a flag of that type already exists, it leaves it unchanged (no duplicates). If a check finds no violation but a flag exists, it auto-resolves the flag by deleting it. This means correcting an invoice field automatically clears the corresponding compliance flag with no manual intervention.

---

## RAG Query Pipeline

The query service (`POST /api/v1/query`) runs a 9-step pipeline:

1. **Intent classification** — keyword pre-filter (microseconds, no LLM call for obvious queries) → LLM classifier fallback for ambiguous queries
2. **Route decision** — SQL template engine or RAG path (invoice / compliance / hybrid)
3. **Multi-query rewriting** — 2 alternative phrasings generated to improve retrieval recall
4. **Embedding** — all 3 query variants embedded in parallel
5. **Nearest-neighbor retrieval** — search `invoice_embeddings` and `company_documents` tables, similarity threshold 0.40
6. **Document type boost** — compliance document chunks with matching type receive ×1.15 similarity boost
7. **Reranking** — Cohere or BGE cross-encoder rescores and re-orders candidate chunks (top 6 retained)
8. **Context compression** — LLM extracts only sentences relevant to the question from each chunk
9. **Answer generation** — grounded answer with citation metadata returned to the frontend

For **SQL path** queries (totals, counts, trends), the LLM selects one of 18 pre-written parameterized templates. No raw SQL is ever generated by the model — eliminating both hallucination risk and injection risk.

---

## Known Limitations

- **multi-tenant MVP:** All data is scoped to one hardcoded `MVP_COMPANY_ID`. Multi-tenancy requires adding JWT-based auth and enabling Supabase row-level security.
- **No live payment processing:** Payments are recorded in the database only. Integration with Stripe, PayPal, or an Open Banking API is required for real transactions.
- **English/Latin scripts only:** The embedding model and OCR pipeline are not validated for Arabic, Chinese, or other non-Latin scripts.
- **OpenAI API dependency for embeddings:** If you switch to Ollama. Mixing embedding models across invoices in the same database will produce inconsistent retrieval — run `reset_and_backfill_embeddings.py` when switching.
- **Ollama local model quality:** `llama3:8b` works for intent classification and query answering but produces lower extraction quality than GPT-4o or Gemini on complex or low-quality scanned invoices.
- **Grok:** Provider implementation exists but has not been tested end-to-end by the team.
- **Scheduler + `--reload`:** Do not run `uvicorn` with `--reload` when the APScheduler nightly job needs to work correctly.
- **Scanned/image invoices:** Very low resolution scans, heavy watermarks, or handwritten content will degrade OCR and extraction quality regardless of LLM provider.

---

## Troubleshooting

**Backend 500 on upload:**

- Check that `TESSERACT_CMD` points to a valid Tesseract binary.
- Verify `LLM_PROVIDER` is set correctly and the corresponding API key is present.
- Check `backend/logs/` for the full traceback.

**Embeddings returning no results:**

- Confirm pgvector is enabled in Supabase.
- Run `python scripts/backfill_embeddings.py` to ensure all invoices have embeddings.
- If you recently switched `LLM_PROVIDER`, run `reset_and_backfill_embeddings.py` to regenerate all embeddings with the current provider.

**Compliance flags not clearing:**

- Trigger manual re-validation: `POST /api/v1/invoices/{id}/validate` or use the Validate button on the invoice detail page.

**Scheduler duplicate jobs:**

- Do not run with `--reload`. Restart the backend process manually during development.

---

## License

Academic capstone project — Cyprus International University, Faculty of Engineering, 2026.
