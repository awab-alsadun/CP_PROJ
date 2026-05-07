import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Eye, EyeOff, DollarSign, Send,
  CheckCircle, AlertTriangle, X, FileCode
} from 'lucide-react'
import { invoicesApi, vendorsApi, clientsApi } from '../lib/api'
import { formatCurrency, formatDate } from '../lib/utils'
import { StatusBadge, ConfidenceBar, PageLoader, ErrorState } from '../components/ui'

// ── Simple toast ───────────────────────────────────────────
function Toast({ toasts, remove }) {
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id}
          className="flex items-center gap-3 px-4 py-3 rounded-xl shadow-panel text-sm font-medium animate-fade-up pointer-events-auto"
          style={{
            background: t.type === 'error' ? '#FEF2F2' : 'var(--bg-card)',
            color: t.type === 'error' ? '#EF4444' : 'var(--text-primary)',
            border: `1px solid ${t.type === 'error' ? '#FECACA' : 'var(--border)'}`,
            minWidth: 260,
          }}>
          {t.type === 'error'
            ? <AlertTriangle size={14} color="#EF4444" />
            : <CheckCircle size={14} color="#22C55E" />
          }
          <span className="flex-1">{t.message}</span>
          <button onClick={() => remove(t.id)} className="opacity-50 hover:opacity-100">
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}

function useToast() {
  const [toasts, setToasts] = useState([])
  const add = useCallback((message, type = 'success') => {
    const id = Date.now()
    setToasts(p => [...p, { id, message, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
  }, [])
  const remove = useCallback(id => setToasts(p => p.filter(t => t.id !== id)), [])
  return { toasts, add, remove }
}

// ── Transition config ──────────────────────────────────────
const TRANSITIONS = {
  draft:   [{ to: 'sent',    label: 'Mark as Sent',   icon: Send,          color: '#3B82F6' }],
  sent:    [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' },
            { to: 'overdue', label: 'Mark Overdue',   icon: AlertTriangle, color: '#EF4444' }],
  paid:    [],
  overdue: [{ to: 'paid',   label: 'Mark as Paid',    icon: CheckCircle,   color: '#22C55E' }],
}

// ── Sub-components ─────────────────────────────────────────
function InfoRow({ label, value, mono }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className={`text-sm ${mono ? 'font-mono' : ''}`} style={{ color: 'var(--text-primary)' }}>
        {value || '—'}
      </span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────
export default function InvoiceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toasts, add: toast, remove: removeToast } = useToast()

  const [invoice,         setInvoice]         = useState(null)
  const [raw,             setRaw]             = useState(null)
  const [showRaw,         setShowRaw]         = useState(false)
  const [loading,         setLoading]         = useState(true)
  const [error,           setError]           = useState(null)
  const [transitioning,   setTransitioning]   = useState(false)
  const [showPaymentForm, setShowPaymentForm] = useState(false)
  const [savingPayment,   setSavingPayment]   = useState(false)
  const [loadingRaw,      setLoadingRaw]      = useState(false)
  const [paymentData,     setPaymentData]     = useState({
    amount: '', method: 'bank_transfer', reference: '',
    payment_date: new Date().toISOString().split('T')[0],
  })

  const loadInvoice = useCallback(async () => {
    try {
      const [invoiceRes, lineItemsRes, paymentsRes] = await Promise.allSettled([
        invoicesApi.get(id),
        invoicesApi.getLineItems(id),
        invoicesApi.getPayments(id),
      ])
      if (invoiceRes.status === 'rejected') throw new Error(invoiceRes.reason?.message)
      const inv = invoiceRes.value
      inv.line_items = lineItemsRes.status === 'fulfilled' ? lineItemsRes.value : []
      inv.payments   = paymentsRes.status  === 'fulfilled' ? paymentsRes.value  : []

      // If backend returns only vendor_id/client_id (not nested objects),
      // fetch vendor and client details separately so the cards populate.
      const needsVendor = inv.vendor_id && (!inv.vendor?.name)
      const needsClient = inv.client_id && (!inv.client?.name)
      if (needsVendor || needsClient) {
        const [vRes, cRes] = await Promise.allSettled([
          needsVendor ? vendorsApi.get(inv.vendor_id) : Promise.resolve(null),
          needsClient ? clientsApi.get(inv.client_id) : Promise.resolve(null),
        ])
        if (needsVendor && vRes.status === 'fulfilled' && vRes.value) inv.vendor = vRes.value
        if (needsClient && cRes.status === 'fulfilled' && cRes.value) inv.client = cRes.value
      }

      setInvoice(inv)
    } catch (e) {
      setError(e.message)
    }
  }, [id])

  useEffect(() => {
    setLoading(true)
    loadInvoice().finally(() => setLoading(false))
  }, [loadInvoice])

  const handleLoadRaw = async () => {
    if (raw) { setShowRaw(v => !v); return }
    setLoadingRaw(true)
    try {
      const data = await invoicesApi.getRaw(id)
      setRaw(data)
      setShowRaw(true)
    } catch (e) {
      toast(`Raw extraction: ${e.message}`, 'error')
    } finally {
      setLoadingRaw(false)
    }
  }

  const handleTransition = async (toStatus) => {
    setTransitioning(true)
    try {
      await invoicesApi.transition(id, toStatus)
      await loadInvoice()
      toast(`Invoice marked as ${toStatus}`)
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setTransitioning(false)
    }
  }

  const handleRecordPayment = async (e) => {
    e.preventDefault()
    setSavingPayment(true)
    try {
      await invoicesApi.recordPayment(id, {
        amount: parseFloat(paymentData.amount),
        method: paymentData.method || null,
        reference: paymentData.reference || null,
        payment_date: paymentData.payment_date,
      })
      setShowPaymentForm(false)
      setPaymentData({ amount: '', method: 'bank_transfer', reference: '', payment_date: new Date().toISOString().split('T')[0] })
      await loadInvoice()
      toast('Payment recorded successfully')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setSavingPayment(false)
    }
  }

  if (loading) return <div className="p-6"><PageLoader /></div>
  if (error)   return <div className="p-6"><ErrorState message={error} onRetry={() => navigate(-1)} /></div>
  if (!invoice) return null

  const transitions = TRANSITIONS[invoice.status] || []
  const canPay = invoice.status !== 'paid'

  return (
    <>
      <Toast toasts={toasts} remove={removeToast} />

      <div className="p-6 space-y-5 animate-fade-up max-w-5xl">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="btn-ghost p-2 rounded-xl">
              <ArrowLeft size={16} />
            </button>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {invoice.invoice_number || 'Invoice'}
                </h1>
                <StatusBadge status={invoice.status} />
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                Issued {formatDate(invoice.issue_date)}
                {invoice.due_date && ` · Due ${formatDate(invoice.due_date)}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap justify-end">
            {/* Raw extraction toggle */}
            <button
              onClick={handleLoadRaw}
              disabled={loadingRaw}
              className="btn-secondary text-xs h-8 disabled:opacity-50"
            >
              <FileCode size={13} />
              {loadingRaw ? 'Loading…' : showRaw ? 'Hide Raw' : 'View Raw Extraction'}
            </button>

            {/* State machine transitions */}
            {transitions.map(t => {
              const Icon = t.icon
              return (
                <button
                  key={t.to}
                  onClick={() => handleTransition(t.to)}
                  disabled={transitioning}
                  className="btn-secondary text-xs h-8 disabled:opacity-50"
                  style={{ borderColor: t.color, color: t.color }}
                >
                  <Icon size={13} />
                  {t.label}
                </button>
              )
            })}

            {/* Record payment — hidden when already paid */}
            {canPay && (
              <button
                onClick={() => setShowPaymentForm(v => !v)}
                className="btn-primary text-xs h-8"
              >
                <DollarSign size={13} />
                Record Payment
              </button>
            )}
          </div>
        </div>

        {/* Payment form */}
        {showPaymentForm && (
          <div className="card p-5 border-2 animate-fade-up" style={{ borderColor: 'var(--accent)' }}>
            <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
              Record Payment
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>Amount *</label>
                <input className="input h-9 text-sm font-mono"
                  type="number" step="0.01" min="0" required
                  value={paymentData.amount}
                  onChange={e => setPaymentData(p => ({ ...p, amount: e.target.value }))}
                  placeholder={String(invoice.grand_total || '')}
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>Date *</label>
                <input className="input h-9 text-sm" type="date"
                  value={paymentData.payment_date}
                  onChange={e => setPaymentData(p => ({ ...p, payment_date: e.target.value }))}
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>Method</label>
                <select className="input h-9 text-sm"
                  value={paymentData.method}
                  onChange={e => setPaymentData(p => ({ ...p, method: e.target.value }))}>
                  <option value="bank_transfer">Bank Transfer</option>
                  <option value="credit_card">Credit Card</option>
                  <option value="cash">Cash</option>
                  <option value="check">Check</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>Reference</label>
                <input className="input h-9 text-sm"
                  value={paymentData.reference}
                  onChange={e => setPaymentData(p => ({ ...p, reference: e.target.value }))}
                  placeholder="TXN-001"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-3">
              <button onClick={() => setShowPaymentForm(false)} className="btn-secondary text-xs h-8">
                Cancel
              </button>
              <button
                onClick={handleRecordPayment}
                disabled={savingPayment || !paymentData.amount}
                className="btn-primary text-xs h-8 disabled:opacity-50"
              >
                {savingPayment ? 'Saving…' : 'Save Payment'}
              </button>
            </div>
          </div>
        )}

        {/* Raw extraction panel */}
        {showRaw && raw && (
          <div className="card overflow-hidden animate-fade-up">
            <div className="px-5 py-3.5 border-b flex items-center justify-between"
              style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Raw Extraction
              </h2>
              <div className="flex items-center gap-3">
                {invoice.confidence_score != null && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Confidence</span>
                    <ConfidenceBar score={invoice.confidence_score} />
                  </div>
                )}
                <span className="text-xs font-mono px-2 py-0.5 rounded"
                  style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                  v{raw.schema_version || '1.0'}
                </span>
              </div>
            </div>

            {/* Tabs: raw text vs JSON */}
            <RawTabs raw={raw} />
          </div>
        )}

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Section title="Invoice Details">
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label="Invoice #"      value={invoice.invoice_number} mono />
              <InfoRow label="Currency"       value={invoice.currency} />
              <InfoRow label="Issue Date"     value={formatDate(invoice.issue_date)} />
              <InfoRow label="Due Date"       value={formatDate(invoice.due_date)} />
              <InfoRow label="Payment Method" value={invoice.payment_method} />
              <InfoRow label="Tax Rate"
                value={invoice.tax_percent != null ? `${invoice.tax_percent}%` : null} />
            </div>
            {invoice.description && (
              <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
                <InfoRow label="Description" value={invoice.description} />
              </div>
            )}
          </Section>

          <Section title="Financials">
            <div className="space-y-3">
              {[
                { label: 'Subtotal',  value: formatCurrency(invoice.subtotal, invoice.currency) },
                { label: 'Discount',  value: invoice.discount > 0 ? `- ${formatCurrency(invoice.discount, invoice.currency)}` : '—' },
                { label: 'Tax',       value: formatCurrency(invoice.total_tax, invoice.currency) },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between text-sm">
                  <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                  <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{value}</span>
                </div>
              ))}
              <div className="flex justify-between items-center pt-3 border-t"
                style={{ borderColor: 'var(--border)' }}>
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Grand Total</span>
                <span className="font-mono text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {formatCurrency(invoice.grand_total, invoice.currency)}
                </span>
              </div>
              {invoice.confidence_score != null && (
                <div className="flex justify-between items-center pt-2">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Extraction Confidence</span>
                  <ConfidenceBar score={invoice.confidence_score} />
                </div>
              )}
            </div>
          </Section>

          <Section title="Vendor">
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label="Name"   value={invoice.vendor?.name} />
              <InfoRow label="Tax ID" value={invoice.vendor?.tax_id} mono />
              <InfoRow label="Email"  value={invoice.vendor?.email} />
              <InfoRow label="Phone"  value={invoice.vendor?.phone} />
            </div>
          </Section>

          <Section title="Client">
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label="Name"   value={invoice.client?.name} />
              <InfoRow label="Tax ID" value={invoice.client?.tax_id} mono />
              <InfoRow label="Email"  value={invoice.client?.email} />
              <InfoRow label="Phone"  value={invoice.client?.phone} />
            </div>
          </Section>
        </div>

        {/* Line items */}
        {invoice.line_items?.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Line Items</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Description', 'Qty', 'Unit Price', 'Discount', 'Subtotal'].map(h => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
                        style={{ color: 'var(--text-muted)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoice.line_items.map((item, i) => (
                    <tr key={item.id || i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td className="px-5 py-3 text-sm" style={{ color: 'var(--text-primary)' }}>{item.description}</td>
                      <td className="px-5 py-3 text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>{item.quantity}</td>
                      <td className="px-5 py-3 text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>
                        {formatCurrency(item.unit_price, invoice.currency)}
                      </td>
                      <td className="px-5 py-3 text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
                        {item.discount > 0 ? formatCurrency(item.discount, invoice.currency) : '—'}
                      </td>
                      <td className="px-5 py-3 text-sm font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                        {formatCurrency(item.line_subtotal, invoice.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Payment history */}
        {invoice.payments?.length > 0 && (
          <Section title="Payment History">
            <div className="space-y-2">
              {invoice.payments.map((p, i) => (
                <div key={p.id || i}
                  className="flex items-center justify-between py-2.5 px-3 rounded-xl"
                  style={{ background: 'var(--bg-secondary)' }}>
                  <div>
                    <p className="text-sm font-medium font-mono" style={{ color: 'var(--text-primary)' }}>
                      {formatCurrency(p.amount, invoice.currency)}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {formatDate(p.payment_date)} · {p.method || 'N/A'}
                      {p.reference && ` · Ref: ${p.reference}`}
                    </p>
                  </div>
                  <CheckCircle size={16} color="#22C55E" />
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </>
  )
}

// ── Raw tabs sub-component ─────────────────────────────────
function RawTabs({ raw }) {
  const [tab, setTab] = useState('json')
  return (
    <div>
      <div className="flex gap-1 px-5 pt-3 border-b" style={{ borderColor: 'var(--border)' }}>
        {[['json', 'Extraction JSON'], ['text', 'Raw Text']].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className="px-3 py-1.5 text-xs font-medium rounded-t-lg transition-all"
            style={tab === key
              ? { color: 'var(--accent)', borderBottom: '2px solid var(--accent)' }
              : { color: 'var(--text-muted)' }
            }>
            {label}
          </button>
        ))}
      </div>
      <pre className="p-5 text-xs font-mono overflow-auto leading-relaxed"
        style={{
          color: 'var(--text-secondary)',
          background: 'var(--bg-secondary)',
          maxHeight: 360,
          whiteSpace: tab === 'text' ? 'pre-wrap' : 'pre',
        }}>
        {tab === 'json'
          ? JSON.stringify(raw.extraction_json || {}, null, 2)
          : (raw.raw_text || 'No raw text available.')
        }
      </pre>
    </div>
  )
}