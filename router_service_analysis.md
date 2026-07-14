# Architectural Analysis: FastAPI Routers vs. Services

## Executive Summary

The backend architecture largely attempts to follow a **"Thin Router / Fat Service"** pattern, where routers (`backend/app/routers/*.py`) handle HTTP request validation, status code assignments, and file/body parsing, while delegating core operational and database logic to underlying services (`backend/app/services/*.py`).

However, **this pattern is not strictly enforced and is heavily violated in several key areas**. While most files use the `_handle` pattern to wrap service responses, files like `reports.py` entirely bypass the service layer, constructing raw SQL queries and running deep data transformations directly within the router. Similarly, `clients.py` and `settings.py` leak database querying or core business/auth validations into the routing layer.

---

## File-by-File Analysis: Routers to Services

### 1. `admin.py` (Admin Router)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `POST /run-overdue-check` ➡️ `overdue_service.check_and_mark_overdue`
  - `POST /run-compliance-check` ➡️ `compliance_service.run_compliance_check_all`
- **Analysis**: Adheres perfectly to the pattern. It uses the `_handle` wrapper to intercept standard database/validation exceptions and translates them to HTTP 400/502 errors without exposing database access inside the router itself.

### 2. `analytics.py` (Analytics Router)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `GET /dashboard` ➡️ `analytics_service.get_dashboard`
  - `GET /spending` ➡️ `analytics_service.get_spending`
  - `GET /revenue` ➡️ `analytics_service.get_revenue`
  - `GET /trends` ➡️ `analytics_service.get_trends`
  - `GET /payment-timing` ➡️ `analytics_service.get_payment_timing`
  - `GET /overdue` ➡️ `analytics_service.get_overdue`
  - `GET /system-stats` ➡️ `analytics_service.get_system_stats`
  - `GET /page-metrics` ➡️ `analytics_service.get_page_metrics`
- **Analysis**: Fully adheres to the thin router pattern. Contains zero business logic and relies entirely on `analytics_service.py` to query and calculate visualization metrics.

### 3. `clients.py` (Clients Router)

- **Architectural Pattern**: **Mixed (Leaky Handler)**.
- **Mapping**:
  - `POST /` ➡️ `client_service.create_client`
  - `GET /` ➡️ `client_service.list_clients`
  - `GET /{client_id}` ➡️ `client_service.get_client`
  - `PATCH /{client_id}` ➡️ `client_service.update_client`
  - `DELETE /{client_id}` ➡️ `client_service.soft_delete_client`
  - `GET /{client_id}/latest-address` ➡️ ⚠️ **No service counterpart**. Logic is written inline.
- **Analysis**: Most endpoints delegate appropriately. However, the `get_latest_address` endpoint breaks the architecture. It performs raw `db.table("invoices")` and `db.table("addresses")` lookups, executes fallback condition trees natively in the controller, explicitly manages `except Exception` chains to throw HTTP 502s, and dictates data retrieval formatting inside the route. It should be refactored into a `client_service.get_latest_address` method.

### 4. `documents.py` (Documents Router)

- **Architectural Pattern**: **Thick Handler**.
- **Mapping**:
  - `POST /upload` ➡️ `document_service.upload_and_embed_document`
  - `GET /` ➡️ `document_service.list_documents`
  - `DELETE /{document_id}` ➡️ `document_service.delete_document`
  - `PATCH /{document_id}` ➡️ `document_service.update_document_metadata`
- **Analysis**: While it delegates database queries and embedding logic to the `document_service`, the router holds substantial validation logic natively. `upload_document` and `update_company_document` check arrays of acceptable `document_types` and parse file size constraints (`max_size = 50 * 1024 * 1024`) inline. From an overarching architectural view, it keeps the `document_service.py` independent of FastAPI context, but does arguably harbor too much hard-coded configuration logic.

### 5. `invoices.py` (Invoices Router)

- **Architectural Pattern**: **Thin Handler (Mostly)**.
- **Mapping**:
  - `POST /` ➡️ `invoice_service.create_receivable_invoice`
  - `GET /` ➡️ `invoice_service.list_invoices`
  - `GET /{invoice_id}` ➡️ `invoice_service.get_invoice`
  - `PATCH /{invoice_id}` ➡️ `invoice_service.update_invoice`
  - `DELETE /{invoice_id}` ➡️ `invoice_service.soft_delete_invoice`
  - `GET /{invoice_id}/line-items` ➡️ `invoice_service.get_line_items`
  - `GET /{invoice_id}/payments` ➡️ `invoice_service.get_payments`
  - `GET /{invoice_id}/raw-document` ➡️ `invoice_service.get_raw_document`
  - `GET /{invoice_id}/compliance-flags` ➡️ `compliance_service.get_invoice_flags`
  - `POST /{invoice_id}/validate` ➡️ `compliance_service.validate_invoice_compliance`
- **Analysis**: Highly optimized delegator. The only explicit rule inside the router is preventing payable invoices from being created manually (`HTTPException` on `InvoiceType.payable`). The rest safely proxies through `invoice_service` and `compliance_service`.

### 6. `notifications.py` (Notifications Router)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `GET /` ➡️ `notification_service.list_notifications`
  - `POST /{id}/read` ➡️ `notification_service.mark_read`
  - `POST /read-all` ➡️ `notification_service.mark_all_read`
- **Analysis**: Standard delegation; behaves exactly as intended.

### 7. `payments.py` (Payments Router)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `POST /webhook` ➡️ _Not Implemented (Stubs an HTTP 501)_
  - `POST /invoices/{invoice_id}/credit-note` ➡️ `credit_service.apply_credit_note`
  - `POST /invoices/{invoice_id}/refund` ➡️ `credit_service.process_refund`
- **Analysis**: Adheres properly. Payments handling was previously relocated directly to invoices, leaving this script primarily to manage specialized `credit_service` transactions.

### 8. `query.py` (Query Router for RAG/DB searches)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `POST /` ➡️ `query_service.handle_query`
- **Analysis**: Uses native Pydantic validators on `QueryRequest` inline (prevent empty queries & set 2000 character maximum limit), but the main pipeline logic shifts execution cleanly to the standalone `query_service.py` component handling SQL / RAG routing.

### 9. `reports.py` (Reports Router)

- **Architectural Pattern**: **HUGE ANTI-PATTERN (Heavy Logic)**.
- **Mapping**:
  - `GET /income-statement` ➡️ ⚠️ **No service counterpart**.
  - `GET /cash-flow` ➡️ ⚠️ **No service counterpart**.
- **Analysis**: This is the largest architectural violation in the application. There is no `report_service.py`. The `reports.py` router:
  1. Contains Python helper functions globally (`get_period_sql`, `format_label`).
  2. Constructs large, nested SQL CTE strings (`query = f"""SELECT {trunc} AS period_start... """`).
  3. Executes raw `db.rpc("exec_sql")` and `db.table(...).select(...)` inside the route handlers.
  4. Parses results using loops, complex python `defaultdict` bucket strategies, and mathematical calculations all the way down to rounding limits.
- **Recommendation**: This file desperately needs all database execution and parsing extracted directly to an `app.services.report_service` module.

### 10. `settings.py` (Settings Router)

- **Architectural Pattern**: **Mixed Handler**.
- **Mapping**:
  - `GET /` ➡️ `settings_service.get_company_settings` & `settings_service.is_password_protected`
  - `PATCH /` ➡️ `settings_service.verify_settings_password` & `settings_service.update_company_settings`
  - `GET /branding` ➡️ `settings_service.get_company_settings`
  - `PATCH /branding` ➡️ `settings_service.update_company_settings`
- **Analysis**: Contains slightly heavier pre-processing inline than a standard thin router. Validates hex codes natively with an inline `_validate_hex` parser function and does immediate logical processing on password checks before allowing `PATCH` actions to run sequentially. It manages business intent at the HTTP layer rather than purely deferring.

### 11. `upload.py` (Upload Router)

- **Architectural Pattern**: **Thick Handler**.
- **Mapping**:
  - `_process_single_upload` (Helper) ➡️ `invoice_processor.process_invoice`
  - `POST /` ➡️ Relies on internal helper.
  - `POST /batch` ➡️ Wrapper loop driving the internal helper.
- **Analysis**: Fastapi file semantics (UploadFile constraints and validation logic mapping specifically to PDF/JPG/PNG parsing) are built inherently into a `_process_single_upload` function inside the router. It isolates FastAPI from `invoice_processor.py`, letting the service just handle byte-arrays rather than HTTP file-handles, which technically observes domain isolation requirements, even if it creates a thick router layer.

### 12. `vendors.py` (Vendors Router)

- **Architectural Pattern**: **Thin Handler**.
- **Mapping**:
  - `POST /` ➡️ `vendor_service.create_vendor`
  - `GET /` ➡️ `vendor_service.list_vendors`
  - `GET /{vendor_id}` ➡️ `vendor_service.get_vendor`
  - `PATCH /{vendor_id}` ➡️ `vendor_service.update_vendor`
  - `DELETE /{vendor_id}` ➡️ `vendor_service.soft_delete_vendor`
- **Analysis**: Complies fully with thin routing standards.

---

## Conclusion

The backend intends to decouple HTTP routing from business logic through clearly defined services but experiences significant discipline drift across the application lifecycle. **`admin`, `analytics`, `invoices`, `notifications`, `payments`, `query` and `vendors`** are beautifully factored. In stark contrast, **`reports.py`** and **`clients.py` (via `get_latest_address`)** heavily bury deep dataset operations, database joins, filtering loops, and exception handling inside FastAPI route contexts. Refactoring these specific anomalies will bridge the application integrity seamlessly to full consistency.
