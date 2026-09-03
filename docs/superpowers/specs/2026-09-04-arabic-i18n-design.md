# Arabic (i18n) Support — Design Spec

## Overview

Add full Arabic language support to the InVox frontend, selectable at runtime
from Settings, with full RTL (right-to-left) layout mirroring — not just
translated text. English remains the default. Numbers (currency, counts,
IDs) stay in Western Arabic numerals (0-9) in both languages. Frontend-only;
no backend changes.

## Goals

- Every page/component has an Arabic translation, switchable without a page
  reload.
- Full RTL layout mirroring: sidebar, nav, alignment, icon flow, drawer
  slide direction all mirror when Arabic is active.
- Numbers stay Western-digit regardless of language.
- Single codebase — no duplicated pages or routes per language.
- Language preference persists per-browser via `localStorage`, consistent
  with the existing `company_id` / `invox_llm_provider` pattern.

## Non-goals

- Backend/API translation. All API responses and error messages stay in
  English — this is a display-layer language switch only.
- Date localization (Arabic month names, calendar systems). Dates keep their
  current `en-US` `Intl` formatting.
- Automatic browser-language detection. The user explicitly picks a language
  in Settings; first load always defaults to English.
- A generic multi-language framework for languages beyond Arabic (though the
  key-based structure makes adding one later straightforward).

## Architecture

### Library: react-i18next + i18next

Rationale, grounded in this specific codebase (not a generic library
preference):

- Arabic has 6 grammatical plural forms (zero/one/two/few/many/other)
  vs. English's 2. This app says things like "3 invoices" / "1 overdue
  invoice" constantly. i18next's ICU-style plural resolution handles this
  correctly out of the box; hand-rolling it means writing that logic
  ourselves.
- `frontend/src/lib/utils.js` has plain (non-component, non-hook) functions
  — `statusConfig()`, `confidenceLabel()` — with hardcoded English strings
  that need translation but can't call a React hook. i18next exposes an
  importable singleton (`import i18n from '../i18n'; i18n.t(key)`) usable
  from plain JS, not just inside components with `useTranslation()`.
- Industry-standard, well-documented — low risk for a project on a deadline.

### New file structure

```
frontend/src/i18n/
  index.js              # i18next init + config
  locales/
    en.json             # English strings, nested by feature namespace
    ar.json             # Arabic strings, identical key shape
```

No new page files, no `/en` or `/ar` route trees. All 16 existing pages plus
`Sidebar.jsx`, `Topbar.jsx`, `AppShell.jsx`, `ChatPanel.jsx` get their
hardcoded strings replaced with `t('namespace.key')` calls, in place, in the
same files they live in today.

### Key namespace shape (illustrative)

```json
{
  "common": { "save": "Save", "cancel": "Cancel", "delete": "Delete" },
  "nav": { "dashboard": "Dashboard", "payables": "Payables" },
  "status": { "draft": "Draft", "sent": "Sent", "paid": "Paid",
              "overdue": "Overdue", "unpaid": "Unpaid",
              "partially_paid": "Partial" },
  "dashboard": { "...": "..." },
  "settings": { "...": "..." },
  "chat": { "...": "..." }
}
```

One namespace per page/feature area, plus shared `common`, `nav`, and
`status` namespaces to avoid duplicating strings like "Save" or "Overdue"
across every page's translation file.

### Language state and persistence

- `localStorage.invox_language` — `"en"` (default) or `"ar"`.
- i18next initializes with `lng` read from `localStorage` at startup,
  falling back to `"en"`.
- Settings → Company Profile tab gets a new "Language" field: a two-option
  control (English / العربية) that calls `i18n.changeLanguage(...)` and
  writes the choice to `localStorage`.
- A small effect at the top of `App.jsx` subscribes to language changes and
  sets:
  - `document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'`
  - `document.documentElement.lang = lang`

  This single attribute is what activates Tailwind's logical-class flipping
  app-wide — components using logical classes need no per-component
  direction logic at all.

### RTL layout strategy

1. **Tailwind physical → logical class migration**, done per-file during
   string extraction (one pass per file, not a separate sweep):
   `ml-*→ms-*`, `mr-*→me-*`, `pl-*→ps-*`, `pr-*→pe-*`, `left-*→start-*`,
   `right-*→end-*`, `border-l→border-s`, `border-r→border-e`,
   `rounded-l-*→rounded-s-*`, `rounded-r-*→rounded-e-*`,
   `text-left→text-start`, `text-right→text-end`.
   Confirmed this project runs Tailwind 3.4.15, which supports these logical
   utilities natively — once `dir="rtl"` is set on `<html>`, they flip with
   zero extra code.
2. **Inline styles with hardcoded physical values** — e.g. `ChatPanel.jsx`'s
   `right: open ? 0 : -400` and `borderLeft` — converted case-by-case, either
   to Tailwind logical classes (preferred) or an explicit
   `document.dir === 'rtl'` conditional where a utility class can't express
   it (e.g. transform-based slide animations).
3. **Directionally-meaningful icons** — Sidebar's collapse
   `ChevronLeft`/`ChevronRight` — swapped conditionally based on current
   direction.
4. **Arabic web font** — add "Cairo" via Google Fonts, applied when
   `dir="rtl"` (`[dir="rtl"] { font-family: 'Cairo', sans-serif; }` in
   `index.css`, alongside the existing Latin stack). The current fonts (DM
   Sans, Syne, JetBrains Mono) contain no Arabic glyphs — without this,
   Arabic text renders as fallback/tofu boxes regardless of translation
   correctness.

### Numbers stay Western — explicit no-op

`formatCurrency`, `formatDate`, and `formatDateShort` in `lib/utils.js`
already hardcode `Intl.NumberFormat('en-US', ...)` / `toLocaleDateString(
'en-US', ...)`. These are **left unchanged** by this work. Calling this out
explicitly so a future edit doesn't "helpfully" change them to `'ar-SA'` —
that would introduce Eastern Arabic-Indic digits (٠١٢٣), which is the
opposite of what's wanted here. Plain `{count}` interpolation elsewhere
needs no special handling; JS numbers are Western-digit by default.

## Scope: what gets converted

**Layout shell:** `App.jsx` (the `PAGE_META` title/subtitle map),
`AppShell.jsx`, `Sidebar.jsx`, `Topbar.jsx`.

**Pages (all 16):** `Login`, `Dashboard`, `Invoices`, `InvoiceDetail`,
`CreateInvoice`, `CreateClient`, `CreateVendor`, `Vendors`, `Clients`,
`UploadExtract`, `CompanyDocuments`, `Analytics`, `AiChat`, `Payables`,
`Receivables`, `Settings`.

**Components:** `ChatPanel.jsx`, `PaymentSimulator.jsx`, `components/ui/index.jsx` (shared
primitives — `StatusBadge`, `EmptyState`, `ErrorState`, `MetricCard`, `InvoiceTypeBadge`,
`ComplianceFlagBadge`, `ConfirmDialog`, `ToastProvider` — used across nearly every page;
found during implementation scanning, not in the original page-by-page read, but in scope
for the same reason `lib/utils.js` is: it's shared infrastructure other pages depend on).

**Shared:** `lib/utils.js` (`statusConfig`, `confidenceLabel` label strings),
routed through the i18next singleton import rather than the component hook.

`CompanyDocuments.jsx` is currently a placeholder stub and `PaymentSimulator.jsx`
is orphaned (unused, no backend route) — both are translated anyway per
explicit instruction, even though they may be deleted or rebuilt later.

## Phased build plan

1. **Infra + shell** — install `react-i18next`/`i18next`, create the locale
   file skeleton (`common`/`nav`/`status` namespaces), wire the language
   toggle into Settings, add the dir/lang-sync effect, add the Arabic font.
   Convert `App.jsx`, `AppShell.jsx`, `Sidebar.jsx`, `Topbar.jsx` fully
   (strings + RTL classes) — this wraps every page, so it's the natural
   smoke-test surface. Also convert `lib/utils.js`'s `statusConfig`/
   `confidenceLabel` labels here (via the i18next singleton import, not the
   hook) since the `status` namespace is defined in this phase and several
   later phases depend on these functions already being translation-aware.
2. **Auth + most-used pages** — `Login`, `Dashboard`, `ChatPanel`, `AiChat`.
3. **Invoice list/detail pages** — `Payables`, `Receivables`, `Invoices`,
   `InvoiceDetail` (share status-badge and table patterns — efficient to do
   together).
4. **Form pages** — `CreateInvoice`, `CreateVendor`, `CreateClient`.
5. **Remaining pages** — `Vendors`, `Clients`, `Analytics`, `UploadExtract`,
   `Settings`, `CompanyDocuments`, `PaymentSimulator`.
6. **Bilingual QA pass** — click through both languages in the browser,
   verify RTL mirroring visually on every page, fix anything only visible by
   looking (not everything shows up from reading code).

## Testing approach

Per phase: start the frontend dev server, toggle to Arabic in Settings, and
visually verify via the browser — RTL mirroring, Arabic text actually
rendering (no fallback boxes), and numbers staying Western-digit. This is a
visual feature; a code-compiles check is not sufficient verification on its
own.

## Risks / call-outs

- **Translation quality**: translations are written directly (per user
  choice) rather than sourced from a professional translator. A
  native-speaker review pass is recommended before this is judge-facing,
  especially for financial/compliance terminology where precision matters.
- **Dead-code scope**: `CompanyDocuments.jsx` and `PaymentSimulator.jsx` are
  translated despite being a stub/orphan respectively, per explicit
  instruction to defer cleanup — low cost, just noted so it's a deliberate
  choice, not an oversight.
- **Effort shape**: 16 pages plus shared layout, each needing both string
  extraction and RTL class conversion in the same pass — mechanical rather
  than logically hard, but there is a lot of it.
