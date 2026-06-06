import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Save, Send } from 'lucide-react'
import { invoicesApi, clientsApi, settingsApi, getCompanyId } from '../lib/api'
import { cn, formatCurrency } from '../lib/utils'
import {
  Spinner,
  EmptyState,
  SectionHeader,
  toast,
} from '../components/ui'

// ---------------------------------------------------------------------------
// Payload builder — camelCase state → snake_case API payload at the boundary
// All numeric fields go out as strings. Empty discount becomes "0".
// invoice_type is hardcoded receivable. vendor fields are always null.
// ---------------------------------------------------------------------------
function buildInvoicePayload(s, status) {
  const num = (v) => {
    if (v === '' || v === null || v === undefined) return '0'
    return String(v)
  }
  return {
    company_id: getCompanyId(),
    client_id: s.clientId,
    client_address_id: s.clientAddressId || null,
    invoice_number: s.invoiceNumber.trim(),
    issue_date: s.issueDate,
    due_date: s.dueDate || null,
    currency: s.currency,
    tax_percent: num(s.taxPercent),
    subtotal: num(s.subtotal),
    total_tax: num(s.totalTax),
    grand_total: num(s.grandTotal),
    discount: num(s.discount),
    payment_method: s.paymentMethod || null,
    description: s.description || null,
    status,
    invoice_type: 'receivable',
    vendor_id: null,
    vendor_address_id: null,
    line_items: s.lineItems.map((li) => ({
      description: li.description.trim(),
      quantity: num(li.quantity),
      unit_price: num(li.unitPrice),
      line_subtotal: num(li.lineSubtotal),
      discount: num(li.discount),
    })),
  }
}

// ---------------------------------------------------------------------------
// Computed totals — derive subtotal, tax, grand total from line items
// ---------------------------------------------------------------------------
function computeTotals(lineItems, taxPercent, invoiceDiscount) {
  const toN = (v) => {
    const n = parseFloat(v)
    return Number.isFinite(n) ? n : 0
  }
  const items = lineItems.map((li) => {
    const qty = toN(li.quantity)
    const price = toN(li.unitPrice)
    const disc = toN(li.discount)
    const lineSubtotal = Math.max(0, qty * price - disc)
    return { ...li, lineSubtotal: lineSubtotal.toFixed(2) }
  })
  const subtotal = items.reduce((a, b) => a + toN(b.lineSubtotal), 0)
  const tax = subtotal * (toN(taxPercent) / 100)
  const grand = Math.max(0, subtotal + tax - toN(invoiceDiscount))
  return {
    items,
    subtotal: subtotal.toFixed(2),
    totalTax: tax.toFixed(2),
    grandTotal: grand.toFixed(2),
  }
}

const EMPTY_LINE = {
  description: '',
  quantity: '1',
  unitPrice: '0',
  discount: '0',
  lineSubtotal: '0.00',
}

const today = () => new Date().toISOString().slice(0, 10)

export default function CreateInvoice() {
  const navigate = useNavigate()

  // -------- form state (camelCase) --------
  const [form, setForm] = useState({
    invoiceNumber: '',
    issueDate: today(),
    dueDate: '',
    currency: 'USD',
    taxPercent: '0',
    discount: '0',
    paymentMethod: '',
    description: '',
    clientId: '',
    clientAddressId: null,
    lineItems: [{ ...EMPTY_LINE }],
  })

  // -------- clients & addresses --------
  const [clients, setClients] = useState([])
  const [clientsLoading, setClientsLoading] = useState(true)
  const [clientsError, setClientsError] = useState(null)
  const [clientAddress, setClientAddress] = useState(null) // single normalized address object
  const [addressLoading, setAddressLoading] = useState(false)

  // -------- submit state --------
  const [submitting, setSubmitting] = useState(null) // 'draft' | 'sent' | null
  const [fieldErrors, setFieldErrors] = useState({}) // { 'invoice_number': 'msg', 'line_items.0.description': 'msg' }

  // -------- seed tax % from company default on mount --------
  useEffect(() => {
    settingsApi.get()
      .then((s) => {
        const rate = s?.default_tax_rate
        if (rate != null && Number(rate) > 0) {
          setForm((f) => ({ ...f, taxPercent: String(rate) }))
        }
      })
      .catch(() => {}) // leave taxPercent as '0' on failure
  }, [])

  // -------- load clients on mount --------
  useEffect(() => {
    let cancelled = false
    setClientsLoading(true)
    clientsApi
      .list({ page: 1, limit: 200 })
      .then((res) => {
        if (cancelled) return
        setClients(res?.data || [])
        setClientsError(null)
      })
      .catch((err) => {
        if (cancelled) return
        setClientsError(err?.message || 'Failed to load clients')
        setClients([])
      })
      .finally(() => !cancelled && setClientsLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  // -------- when client changes, fetch latest address from dedicated endpoint --------
  useEffect(() => {
    if (!form.clientId) {
      setClientAddress(null)
      setForm((f) => ({ ...f, clientAddressId: null }))
      return
    }
    let cancelled = false
    setAddressLoading(true)
    clientsApi
      .getLatestAddress(form.clientId)
      .then((addr) => {
        if (cancelled) return
        setClientAddress(addr || null)
        setForm((f) => ({ ...f, clientAddressId: addr?.id || null }))
      })
      .catch((err) => {
        if (cancelled) return
        const status = err?.status ?? err?.response?.status
        const is404 =
          status === 404 || /\b404\b/.test(err?.message || '')
        if (!is404) {
          // eslint-disable-next-line no-console
          console.error('[CreateInvoice] latest-address failed:', err)
        }
        setClientAddress(null)
        setForm((f) => ({ ...f, clientAddressId: null }))
      })
      .finally(() => !cancelled && setAddressLoading(false))
    return () => {
      cancelled = true
    }
  }, [form.clientId])

  // -------- recompute totals whenever line items / tax / discount change --------
  const totals = useMemo(
    () => computeTotals(form.lineItems, form.taxPercent, form.discount),
    [form.lineItems, form.taxPercent, form.discount]
  )

  // sync computed line_subtotal back into form lineItems (for payload build)
  useEffect(() => {
    setForm((f) => {
      const same =
        f.lineItems.length === totals.items.length &&
        f.lineItems.every((li, i) => li.lineSubtotal === totals.items[i].lineSubtotal)
      if (same) return f
      return { ...f, lineItems: totals.items }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totals.items])

  // -------- field helpers --------
  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const updateLine = (idx, key, val) => {
    setForm((f) => {
      const next = f.lineItems.slice()
      next[idx] = { ...next[idx], [key]: val }
      return { ...f, lineItems: next }
    })
  }

  const addLine = () =>
    setForm((f) => ({ ...f, lineItems: [...f.lineItems, { ...EMPTY_LINE }] }))

  const removeLine = (idx) => {
    setForm((f) => {
      if (f.lineItems.length === 1) return f
      const next = f.lineItems.slice()
      next.splice(idx, 1)
      return { ...f, lineItems: next }
    })
  }

  // -------- client-side validation --------
  const validate = () => {
    const errs = {}
    if (!form.invoiceNumber.trim()) errs.invoice_number = 'Required'
    if (!form.issueDate) errs.issue_date = 'Required'
    if (!form.clientId) errs.client_id = 'Select a client'
    if (!form.currency) errs.currency = 'Required'
    form.lineItems.forEach((li, i) => {
      if (!li.description.trim()) errs[`line_items.${i}.description`] = 'Required'
      const q = parseFloat(li.quantity)
      if (!Number.isFinite(q) || q <= 0) errs[`line_items.${i}.quantity`] = '> 0'
      const p = parseFloat(li.unitPrice)
      if (!Number.isFinite(p) || p < 0) errs[`line_items.${i}.unit_price`] = '>= 0'
    })
    return errs
  }

  // -------- submit --------
  const submit = async (status) => {
    setFieldErrors({})
    const clientErrs = validate()
    if (Object.keys(clientErrs).length) {
      setFieldErrors(clientErrs)
      toast('Fix the highlighted fields', 'error')
      return
    }
    setSubmitting(status)
    try {
      const payload = buildInvoicePayload(
        {
          ...form,
          subtotal: totals.subtotal,
          totalTax: totals.totalTax,
          grandTotal: totals.grandTotal,
        },
        status
      )
      const res = await invoicesApi.create(payload)
      toast(
        status === 'sent' ? 'Invoice created and marked sent' : 'Invoice saved as draft',
        'success'
      )
      navigate(`/receivables/${res.id}`)
    } catch (err) {
      handleSubmitError(err)
    } finally {
      setSubmitting(null)
    }
  }

  // 422 → map err.detail[] into fieldErrors. 400 → toast.
  const handleSubmitError = (err) => {
    const status = err?.status || err?.response?.status
    const detail = err?.detail || err?.response?.data?.detail

    if (Array.isArray(detail)) {
      const next = {}
      detail.forEach((d) => {
        const path = (d.loc || []).slice(1).join('.') // strip 'body'
        if (path) next[path] = d.msg || 'Invalid'
      })
      setFieldErrors(next)
      toast('Validation failed — see fields below', 'error')
      return
    }
    if (status === 400) {
      toast(err?.message || 'Request rejected', 'error')
      return
    }
    toast(err?.message || 'Failed to create invoice', 'error')
  }

  // -------- render helpers --------
  const errFor = (key) => fieldErrors[key]
  const inputCls = (key) =>
    cn('input', errFor(key) && 'border-red-500 focus:border-red-500')

  // -------- render --------
  return (
    <div className="max-w-6xl mx-auto px-6 py-8 animate-fade-up">
      {/* header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="btn-ghost p-2"
            aria-label="Back"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-display text-3xl text-[var(--text-primary)]">
              Create Invoice
            </h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Receivable · billed to a client
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => submit('draft')}
            disabled={!!submitting}
            className="btn-secondary flex items-center gap-2"
          >
            {submitting === 'draft' ? <Spinner size={16} /> : <Save className="w-4 h-4" />}
            Save Draft
          </button>
          <button
            onClick={() => submit('sent')}
            disabled={!!submitting}
            className="btn-primary flex items-center gap-2"
          >
            {submitting === 'sent' ? <Spinner size={16} /> : <Send className="w-4 h-4" />}
            Save & Send
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT: meta + client + line items */}
        <div className="lg:col-span-2 space-y-6">
          {/* meta */}
          <section className="card p-6">
            <SectionHeader title="Invoice details" />
            <div className="grid grid-cols-2 gap-4 mt-4">
              <Field label="Invoice number" error={errFor('invoice_number')}>
                <input
                  className={inputCls('invoice_number')}
                  value={form.invoiceNumber}
                  onChange={(e) => set('invoiceNumber', e.target.value)}
                  placeholder="INV-2026-001"
                />
              </Field>
              <Field label="Currency" error={errFor('currency')}>
                <select
                  className={inputCls('currency')}
                  value={form.currency}
                  onChange={(e) => set('currency', e.target.value)}
                >
                  {['USD', 'EUR', 'GBP', 'TRY', 'SAR', 'AED', 'EGP'].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Issue date" error={errFor('issue_date')}>
                <input
                  type="date"
                  className={inputCls('issue_date')}
                  value={form.issueDate}
                  onChange={(e) => set('issueDate', e.target.value)}
                />
              </Field>
              <Field label="Due date" error={errFor('due_date')}>
                <input
                  type="date"
                  className={inputCls('due_date')}
                  value={form.dueDate}
                  onChange={(e) => set('dueDate', e.target.value)}
                />
              </Field>
              <Field label="Payment method" error={errFor('payment_method')}>
                <select
                  className={inputCls('payment_method')}
                  value={form.paymentMethod}
                  onChange={(e) => set('paymentMethod', e.target.value)}
                >
                  <option value="">—</option>
                  <option value="bank_transfer">Bank transfer</option>
                  <option value="credit_card">Credit card</option>
                  <option value="cash">Cash</option>
                  <option value="cheque">Cheque</option>
                  <option value="wire">Wire</option>
                </select>
              </Field>
              <Field label="Description" error={errFor('description')}>
                <input
                  className={inputCls('description')}
                  value={form.description}
                  onChange={(e) => set('description', e.target.value)}
                  placeholder="Optional note"
                />
              </Field>
            </div>
          </section>

          {/* client */}
          <section className="card p-6">
            <SectionHeader title="Bill to" />
            <div className="grid grid-cols-2 gap-4 mt-4">
              <Field label="Client" error={errFor('client_id')}>
                {clientsLoading ? (
                  <div className="input flex items-center gap-2">
                    <Spinner size={14} /> <span className="text-[var(--text-muted)]">Loading…</span>
                  </div>
                ) : clientsError ? (
                  <div className="text-sm text-red-500">{clientsError}</div>
                ) : clients.length === 0 ? (
                  <EmptyState
                    title="No clients"
                    description="Create a client first."
                  />
                ) : (
                  <select
                    className={inputCls('client_id')}
                    value={form.clientId}
                    onChange={(e) => set('clientId', e.target.value)}
                  >
                    <option value="">Select a client…</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label="Client address" error={errFor('client_address_id')}>
                {addressLoading ? (
                  <div className="input flex items-center gap-2">
                    <Spinner size={14} />{' '}
                    <span className="text-[var(--text-muted)]">Loading…</span>
                  </div>
                ) : !form.clientId ? (
                  <div className="input text-[var(--text-muted)]">
                    Select client first
                  </div>
                ) : !clientAddress ? (
                  <div className="input text-[var(--text-muted)]">
                    No address on file
                  </div>
                ) : (
                  <div
                    className="input cursor-default"
                    aria-readonly="true"
                  >
                    {formatAddress(clientAddress)}
                  </div>
                )}
              </Field>
            </div>
          </section>

          {/* line items */}
          <section className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <SectionHeader title="Line items" />
              <button onClick={addLine} className="btn-ghost flex items-center gap-2 text-sm">
                <Plus className="w-4 h-4" />
                Add line
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid grid-cols-12 gap-2 text-xs font-mono uppercase tracking-wider text-[var(--text-muted)] px-2">
                <div className="col-span-5">Description</div>
                <div className="col-span-2">Qty</div>
                <div className="col-span-2">Unit price</div>
                <div className="col-span-2">Discount</div>
                <div className="col-span-1 text-right">Subtotal</div>
              </div>

              {form.lineItems.map((li, i) => (
                <div
                  key={i}
                  className="grid grid-cols-12 gap-2 items-start group"
                >
                  <div className="col-span-5">
                    <input
                      className={inputCls(`line_items.${i}.description`)}
                      value={li.description}
                      onChange={(e) => updateLine(i, 'description', e.target.value)}
                      placeholder="Item or service"
                    />
                    {errFor(`line_items.${i}.description`) && (
                      <p className="text-xs text-red-500 mt-1">
                        {errFor(`line_items.${i}.description`)}
                      </p>
                    )}
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      className={inputCls(`line_items.${i}.quantity`)}
                      value={li.quantity}
                      onChange={(e) => updateLine(i, 'quantity', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      className={inputCls(`line_items.${i}.unit_price`)}
                      value={li.unitPrice}
                      onChange={(e) => updateLine(i, 'unitPrice', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      className="input"
                      value={li.discount}
                      onChange={(e) => updateLine(i, 'discount', e.target.value)}
                    />
                  </div>
                  <div className="col-span-1 flex items-center justify-end gap-1 text-sm font-mono">
                    <span>{formatCurrency(li.lineSubtotal, form.currency)}</span>
                    {form.lineItems.length > 1 && (
                      <button
                        onClick={() => removeLine(i)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-[var(--text-muted)] hover:text-red-500"
                        aria-label="Remove line"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* RIGHT: totals */}
        <aside className="lg:col-span-1">
          <section className="card p-6 sticky top-6">
            <SectionHeader title="Totals" />
            <div className="space-y-4 mt-4">
              <Field label="Tax %" error={errFor('tax_percent')}>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className={inputCls('tax_percent')}
                  value={form.taxPercent}
                  onChange={(e) => set('taxPercent', e.target.value)}
                />
              </Field>
              <Field label="Invoice discount" error={errFor('discount')}>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className={inputCls('discount')}
                  value={form.discount}
                  onChange={(e) => set('discount', e.target.value)}
                />
              </Field>

              <div className="border-t border-[var(--border-subtle)] pt-4 space-y-2 font-mono text-sm">
                <Row label="Subtotal" value={formatCurrency(totals.subtotal, form.currency)} />
                <Row label="Tax" value={formatCurrency(totals.totalTax, form.currency)} />
                <Row
                  label="Discount"
                  value={`- ${formatCurrency(form.discount || '0', form.currency)}`}
                />
                <div className="border-t border-[var(--border)] pt-3 flex items-center justify-between">
                  <span className="font-display text-base text-[var(--text-primary)]">
                    Grand total
                  </span>
                  <span className="font-display text-xl text-[var(--accent)]">
                    {formatCurrency(totals.grandTotal, form.currency)}
                  </span>
                </div>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small presentational helpers (kept in-file per single-file-component rule)
// ---------------------------------------------------------------------------
function Field({ label, error, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-[var(--text-muted)] mb-1.5">
        {label}
      </span>
      {children}
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </label>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  )
}

function formatAddress(a) {
  if (!a) return ''
  return [a.street, a.city].filter(Boolean).join(', ')
}