import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Save, Send, FileDown } from 'lucide-react'
import { invoicesApi, clientsApi, vendorsApi, settingsApi, getCompanyId } from '../lib/api'
import { cn, formatCurrency } from '../lib/utils'
import {
  Spinner,
  EmptyState,
  SectionHeader,
  toast,
} from '../components/ui'

// ---------------------------------------------------------------------------
// Payload builder
// ---------------------------------------------------------------------------
function buildInvoicePayload(s, status, invoiceType) {
  const num = (v) => {
    if (v === '' || v === null || v === undefined) return '0'
    return String(v)
  }
  const isReceivable = invoiceType === 'receivable'
  return {
    company_id:        getCompanyId(),
    client_id:         isReceivable ? s.clientId || null : null,
    client_address_id: isReceivable ? s.clientAddressId || null : null,
    vendor_id:         !isReceivable ? s.vendorId || null : null,
    vendor_address_id: !isReceivable ? s.vendorAddressId || null : null,
    invoice_number:    !isReceivable && s.invoiceNumber?.trim() ? s.invoiceNumber.trim() : undefined,
    issue_date:        isReceivable ? new Date().toISOString().split('T')[0] : (s.issueDate || new Date().toISOString().split('T')[0]),
    due_date:          s.dueDate || null,
    currency:          s.currency,
    tax_percent:       num(s.taxPercent),
    subtotal:          num(s.subtotal),
    total_tax:         num(s.totalTax),
    grand_total:       num(s.grandTotal),
    discount:          num(s.discount),
    payment_method:    s.paymentMethod || null,
    description:       s.description || null,
    status,
    invoice_type:      invoiceType,
    line_items: s.lineItems.map((li) => ({
      description:   li.description.trim(),
      quantity:      num(li.quantity),
      unit_price:    num(li.unitPrice),
      line_subtotal: num(li.lineSubtotal),
      discount:      num(li.discount),
    })),
  }
}

// ---------------------------------------------------------------------------
// Computed totals
// ---------------------------------------------------------------------------
function computeTotals(lineItems, taxPercent, invoiceDiscount) {
  const toN = (v) => {
    const n = parseFloat(v)
    return Number.isFinite(n) ? n : 0
  }
  const items = lineItems.map((li) => {
    const qty   = toN(li.quantity)
    const price = toN(li.unitPrice)
    const disc  = toN(li.discount)
    const lineSubtotal = Math.max(0, qty * price - disc)
    return { ...li, lineSubtotal: lineSubtotal.toFixed(2) }
  })
  const subtotal = items.reduce((a, b) => a + toN(b.lineSubtotal), 0)
  const tax      = subtotal * (toN(taxPercent) / 100)
  const grand    = Math.max(0, subtotal + tax - toN(invoiceDiscount))
  return {
    items,
    subtotal:   subtotal.toFixed(2),
    totalTax:   tax.toFixed(2),
    grandTotal: grand.toFixed(2),
  }
}

const EMPTY_LINE = {
  description: '',
  quantity:    '1',
  unitPrice:   '0',
  discount:    '0',
  lineSubtotal: '0.00',
}

export default function CreateInvoice() {
  const navigate = useNavigate()

  // -------- invoice type toggle --------
  const [invoiceType, setInvoiceType] = useState('receivable')

  // -------- form state --------
  const [form, setForm] = useState({
    invoiceNumber: '',
    issueDate:     new Date().toISOString().split('T')[0],
    dueDate:       '',
    currency:      'USD',
    taxPercent:    '0',
    discount:      '0',
    paymentMethod: '',
    description:   '',
    // receivable
    clientId:        '',
    clientAddressId: null,
    // payable
    vendorId:        '',
    vendorAddressId: null,
    lineItems: [{ ...EMPTY_LINE }],
  })

  // -------- entity lists --------
  const [clients,        setClients]        = useState([])
  const [vendors,        setVendors]        = useState([])
  const [clientsLoading, setClientsLoading] = useState(true)
  const [vendorsLoading, setVendorsLoading] = useState(true)
  const [clientsError,   setClientsError]   = useState(null)
  const [vendorsError,   setVendorsError]   = useState(null)

  // -------- address state --------
  const [entityAddress,  setEntityAddress]  = useState(null)
  const [addressLoading, setAddressLoading] = useState(false)

  // -------- submit state --------
  const [submitting,   setSubmitting]   = useState(null)
  const [fieldErrors,  setFieldErrors]  = useState({})

  // -------- seed tax % from company default --------
  useEffect(() => {
    settingsApi.get()
      .then((s) => {
        const rate = s?.default_tax_rate
        if (rate != null && Number(rate) > 0) {
          setForm((f) => ({ ...f, taxPercent: String(rate) }))
        }
      })
      .catch(() => {})
  }, [])

  // -------- load clients --------
  useEffect(() => {
    let cancelled = false
    setClientsLoading(true)
    clientsApi.list({ page: 1, limit: 200 })
      .then((res) => { if (!cancelled) { setClients(res?.data || []); setClientsError(null) } })
      .catch((err) => { if (!cancelled) setClientsError(err?.message || 'Failed to load clients') })
      .finally(() => !cancelled && setClientsLoading(false))
    return () => { cancelled = true }
  }, [])

  // -------- load vendors --------
  useEffect(() => {
    let cancelled = false
    setVendorsLoading(true)
    vendorsApi.list({ page: 1, limit: 200 })
      .then((res) => { if (!cancelled) { setVendors(res?.data || []); setVendorsError(null) } })
      .catch((err) => { if (!cancelled) setVendorsError(err?.message || 'Failed to load vendors') })
      .finally(() => !cancelled && setVendorsLoading(false))
    return () => { cancelled = true }
  }, [])

  // -------- reset entity selection on type toggle --------
  useEffect(() => {
    setEntityAddress(null)
    setForm((f) => ({
      ...f,
      clientId: '', clientAddressId: null,
      vendorId: '', vendorAddressId: null,
    }))
    setFieldErrors({})
  }, [invoiceType])

  // -------- fetch address when client changes --------
  useEffect(() => {
    if (invoiceType !== 'receivable' || !form.clientId) {
      if (invoiceType === 'receivable') setEntityAddress(null)
      return
    }
    let cancelled = false
    setAddressLoading(true)
    clientsApi.getLatestAddress(form.clientId)
      .then((addr) => {
        if (cancelled) return
        setEntityAddress(addr || null)
        setForm((f) => ({ ...f, clientAddressId: addr?.id || null }))
      })
      .catch((err) => {
        if (cancelled) return
        const is404 = /\b404\b/.test(err?.message || '')
        if (!is404) console.error('[CreateInvoice] client address failed:', err)
        setEntityAddress(null)
        setForm((f) => ({ ...f, clientAddressId: null }))
      })
      .finally(() => !cancelled && setAddressLoading(false))
    return () => { cancelled = true }
  }, [form.clientId, invoiceType])

  // -------- fetch address when vendor changes --------
  useEffect(() => {
    if (invoiceType !== 'payable' || !form.vendorId) {
      if (invoiceType === 'payable') setEntityAddress(null)
      return
    }
    let cancelled = false
    setAddressLoading(true)
    vendorsApi.getLatestAddress(form.vendorId)
      .then((addr) => {
        if (cancelled) return
        setEntityAddress(addr || null)
        setForm((f) => ({ ...f, vendorAddressId: addr?.id || null }))
      })
      .catch((err) => {
        if (cancelled) return
        const is404 = /\b404\b/.test(err?.message || '')
        if (!is404) console.error('[CreateInvoice] vendor address failed:', err)
        setEntityAddress(null)
        setForm((f) => ({ ...f, vendorAddressId: null }))
      })
      .finally(() => !cancelled && setAddressLoading(false))
    return () => { cancelled = true }
  }, [form.vendorId, invoiceType])

  // -------- recompute totals --------
  const totals = useMemo(
    () => computeTotals(form.lineItems, form.taxPercent, form.discount),
    [form.lineItems, form.taxPercent, form.discount]
  )

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

  // -------- helpers --------
  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const updateLine = (idx, key, val) => {
    setForm((f) => {
      const next = f.lineItems.slice()
      next[idx] = { ...next[idx], [key]: val }
      return { ...f, lineItems: next }
    })
  }

  const addLine    = () => setForm((f) => ({ ...f, lineItems: [...f.lineItems, { ...EMPTY_LINE }] }))
  const removeLine = (idx) => {
    setForm((f) => {
      if (f.lineItems.length === 1) return f
      const next = f.lineItems.slice()
      next.splice(idx, 1)
      return { ...f, lineItems: next }
    })
  }

  // -------- validation --------
  const validate = () => {
    const errs = {}
    if (invoiceType === 'receivable' && !form.clientId) errs.entity_id = 'Select a client'
    if (invoiceType === 'payable'    && !form.vendorId) errs.entity_id = 'Select a vendor'
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
    const errs = validate()
    if (Object.keys(errs).length) {
      setFieldErrors(errs)
      toast('Fix the highlighted fields', 'error')
      return
    }
    setSubmitting(status)
    try {
      const payload = buildInvoicePayload(
        { ...form, subtotal: totals.subtotal, totalTax: totals.totalTax, grandTotal: totals.grandTotal },
        status,
        invoiceType,
      )
      const res = await invoicesApi.create(payload)
      const successMsg = invoiceType === 'receivable'
        ? (status === 'sent' ? 'Invoice created and marked sent' : 'Invoice saved as draft')
        : 'Payable invoice created'
      toast(successMsg, 'success')
      navigate(invoiceType === 'receivable' ? `/receivables/${res.id}` : `/payables/${res.id}`)
    } catch (err) {
      handleSubmitError(err)
    } finally {
      setSubmitting(null)
    }
  }

  const handleSubmitError = (err) => {
    const status = err?.status || err?.response?.status
    const detail = err?.detail || err?.response?.data?.detail
    if (Array.isArray(detail)) {
      const next = {}
      detail.forEach((d) => {
        const path = (d.loc || []).slice(1).join('.')
        if (path) next[path] = d.msg || 'Invalid'
      })
      setFieldErrors(next)
      toast('Validation failed — see fields below', 'error')
      return
    }
    if (status === 400) { toast(err?.message || 'Request rejected', 'error'); return }
    toast(err?.message || 'Failed to create invoice', 'error')
  }

  const errFor   = (key) => fieldErrors[key]
  const inputCls = (key) => cn('input', errFor(key) && 'border-red-500 focus:border-red-500')
  const todayLabel = new Date().toLocaleDateString('en-US')
  const isReceivable = invoiceType === 'receivable'

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 animate-fade-up">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="btn-ghost p-2" aria-label="Back">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-display text-3xl text-[var(--text-primary)]">Create Invoice</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              {isReceivable ? 'Receivable · billed to a client' : 'Payable · from a vendor'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* type toggle */}
          <div
            className="flex gap-1 p-1 rounded-xl border mr-2"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}
          >
            {[
              { value: 'receivable', label: 'Receivable' },
              { value: 'payable',    label: 'Payable' },
            ].map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setInvoiceType(value)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150"
                style={invoiceType === value
                  ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                  : { color: 'var(--text-muted)' }}
              >
                {label}
              </button>
            ))}
          </div>

          {isReceivable ? (
            <>
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
            </>
          ) : (
            <button
              onClick={() => submit('unpaid')}
              disabled={!!submitting}
              className="btn-primary flex items-center gap-2"
            >
              {submitting === 'unpaid' ? <Spinner size={16} /> : <FileDown className="w-4 h-4" />}
              Save Payable
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">

          {/* ── Invoice details ── */}
          <section className="card p-6">
            <SectionHeader title="Invoice details" />
            <div className="grid grid-cols-2 gap-4 mt-4">
              <Field
                label="Invoice number"
                hint={isReceivable ? 'Auto-generated by the system' : 'Optional — leave blank to auto-generate'}
              >
                {isReceivable ? (
                  <div
                    className="input h-9 text-sm flex items-center italic"
                    style={{ color: 'var(--text-muted)' }}
                    aria-readonly="true"
                  >
                    Auto-generated on save
                  </div>
                ) : (
                  <input
                    className="input"
                    value={form.invoiceNumber}
                    onChange={(e) => set('invoiceNumber', e.target.value)}
                    placeholder="e.g. INV-2026-001 (optional)"
                  />
                )}
              </Field>
              <Field label="Currency" error={errFor('currency')}>
                <select
                  className={inputCls('currency')}
                  value={form.currency}
                  onChange={(e) => set('currency', e.target.value)}
                >
                  {['USD', 'EUR', 'GBP', 'TRY', 'SAR', 'AED', 'EGP'].map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Issue date" hint={isReceivable ? 'Today' : undefined} error={errFor('issue_date')}>
                {isReceivable ? (
                  <div
                    className="input h-9 text-sm flex items-center"
                    style={{ color: 'var(--text-muted)' }}
                    aria-readonly="true"
                  >
                    {todayLabel}
                  </div>
                ) : (
                  <input
                    type="date"
                    className={inputCls('issue_date')}
                    value={form.issueDate}
                    onChange={(e) => set('issueDate', e.target.value)}
                  />
                )}
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

          {/* ── Bill to / Bill from ── */}
          <section className="card p-6">
            <SectionHeader title={isReceivable ? 'Bill to' : 'Bill from'} />
            <div className="grid grid-cols-2 gap-4 mt-4">

              {isReceivable ? (
                /* CLIENT selector */
                <Field label="Client" error={errFor('entity_id')}>
                  {clientsLoading ? (
                    <div className="input flex items-center gap-2">
                      <Spinner size={14} /><span className="text-[var(--text-muted)]">Loading…</span>
                    </div>
                  ) : clientsError ? (
                    <div className="text-sm text-red-500">{clientsError}</div>
                  ) : clients.length === 0 ? (
                    <EmptyState title="No clients" description="Create a client first." />
                  ) : (
                    <select
                      className={inputCls('entity_id')}
                      value={form.clientId}
                      onChange={(e) => set('clientId', e.target.value)}
                    >
                      <option value="">Select a client…</option>
                      {clients.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  )}
                </Field>
              ) : (
                /* VENDOR selector */
                <Field label="Vendor" error={errFor('entity_id')}>
                  {vendorsLoading ? (
                    <div className="input flex items-center gap-2">
                      <Spinner size={14} /><span className="text-[var(--text-muted)]">Loading…</span>
                    </div>
                  ) : vendorsError ? (
                    <div className="text-sm text-red-500">{vendorsError}</div>
                  ) : vendors.length === 0 ? (
                    <EmptyState title="No vendors" description="Create a vendor first." />
                  ) : (
                    <select
                      className={inputCls('entity_id')}
                      value={form.vendorId}
                      onChange={(e) => set('vendorId', e.target.value)}
                    >
                      <option value="">Select a vendor…</option>
                      {vendors.map((v) => (
                        <option key={v.id} value={v.id}>{v.name}</option>
                      ))}
                    </select>
                  )}
                </Field>
              )}

              {/* ADDRESS display */}
              <Field label={isReceivable ? 'Client address' : 'Vendor address'}>
                {addressLoading ? (
                  <div className="input flex items-center gap-2">
                    <Spinner size={14} /><span className="text-[var(--text-muted)]">Loading…</span>
                  </div>
                ) : !(isReceivable ? form.clientId : form.vendorId) ? (
                  <div className="input text-[var(--text-muted)]">
                    Select {isReceivable ? 'client' : 'vendor'} first
                  </div>
                ) : !entityAddress ? (
                  <div className="input text-[var(--text-muted)]">No address on file</div>
                ) : (
                  <div className="input cursor-default" aria-readonly="true">
                    {formatAddress(entityAddress)}
                  </div>
                )}
              </Field>
            </div>
          </section>

          {/* ── Line items ── */}
          <section className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <SectionHeader title="Line items" />
              <button onClick={addLine} className="btn-ghost flex items-center gap-2 text-sm">
                <Plus className="w-4 h-4" />Add line
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
                <div key={i} className="grid grid-cols-12 gap-2 items-start group">
                  <div className="col-span-5">
                    <input
                      className={inputCls(`line_items.${i}.description`)}
                      value={li.description}
                      onChange={(e) => updateLine(i, 'description', e.target.value)}
                      placeholder="Item or service"
                    />
                    {errFor(`line_items.${i}.description`) && (
                      <p className="text-xs text-red-500 mt-1">{errFor(`line_items.${i}.description`)}</p>
                    )}
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number" min="0" step="any"
                      className={inputCls(`line_items.${i}.quantity`)}
                      value={li.quantity}
                      onChange={(e) => updateLine(i, 'quantity', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number" min="0" step="0.01"
                      className={inputCls(`line_items.${i}.unit_price`)}
                      value={li.unitPrice}
                      onChange={(e) => updateLine(i, 'unitPrice', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number" min="0" step="0.01"
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

        {/* ── Totals sidebar ── */}
        <aside className="lg:col-span-1">
          <section className="card p-6 sticky top-6">
            <SectionHeader title="Totals" />
            <div className="space-y-4 mt-4">
              <Field label="Tax %" error={errFor('tax_percent')}>
                <input
                  type="number" min="0" step="0.01"
                  className={inputCls('tax_percent')}
                  value={form.taxPercent}
                  onChange={(e) => set('taxPercent', e.target.value)}
                />
              </Field>
              <Field label="Invoice discount" error={errFor('discount')}>
                <input
                  type="number" min="0" step="0.01"
                  className={inputCls('discount')}
                  value={form.discount}
                  onChange={(e) => set('discount', e.target.value)}
                />
              </Field>

              <div className="border-t border-[var(--border-subtle)] pt-4 space-y-2 font-mono text-sm">
                <Row label="Subtotal" value={formatCurrency(totals.subtotal, form.currency)} />
                <Row label="Tax"      value={formatCurrency(totals.totalTax, form.currency)} />
                <Row label="Discount" value={`- ${formatCurrency(form.discount || '0', form.currency)}`} />
                <div className="border-t border-[var(--border)] pt-3 flex items-center justify-between">
                  <span className="font-display text-base text-[var(--text-primary)]">Grand total</span>
                  <span className="font-display text-xl text-[var(--accent)]">
                    {formatCurrency(totals.grandTotal, form.currency)}
                  </span>
                </div>
              </div>

              {/* Type indicator */}
              <div
                className="mt-2 px-3 py-2 rounded-lg text-xs font-mono text-center"
                style={{
                  background: isReceivable ? 'rgba(34,197,94,0.08)' : 'rgba(59,130,246,0.08)',
                  color:      isReceivable ? '#22C55E' : '#3B82F6',
                  border:     `1px solid ${isReceivable ? 'rgba(34,197,94,0.2)' : 'rgba(59,130,246,0.2)'}`,
                }}
              >
                {isReceivable ? '↑ RECEIVABLE — money in' : '↓ PAYABLE — money out'}
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

function Field({ label, hint, error, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-[var(--text-muted)] mb-1.5">
        {label}
      </span>
      {children}
      {hint && !error && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{hint}</p>
      )}
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