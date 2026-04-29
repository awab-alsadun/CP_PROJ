import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ChevronRight, Eye, EyeOff, DollarSign, Send, CheckCircle, AlertTriangle } from 'lucide-react'
import { invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, statusConfig } from '../lib/utils'
import { StatusBadge, ConfidenceBar, PageLoader, ErrorState } from '../components/ui'

const TRANSITIONS = {
  draft:   [{ to: 'sent',    label: 'Mark as Sent',    icon: Send,         color: '#3B82F6' }],
  sent:    [{ to: 'paid',    label: 'Record as Paid',  icon: CheckCircle,  color: '#22C55E' },
            { to: 'overdue', label: 'Mark Overdue',    icon: AlertTriangle, color: '#EF4444' }],
  paid:    [],
  overdue: [{ to: 'paid',   label: 'Record as Paid',   icon: CheckCircle,  color: '#22C55E' }],
}

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

export default function InvoiceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [invoice, setInvoice] = useState(null)
  const [raw, setRaw] = useState(null)
  const [showRaw, setShowRaw] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [transitioning, setTransitioning] = useState(false)
  const [showPaymentForm, setShowPaymentForm] = useState(false)
  const [paymentData, setPaymentData] = useState({ amount: '', method: 'bank_transfer', reference: '' })

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [invoiceRes, lineItemsRes, paymentsRes] = await Promise.allSettled([
          invoicesApi.get(id),
          invoicesApi.getLineItems(id),
          invoicesApi.getPayments(id),
        ])
        if (invoiceRes.status === 'rejected') throw new Error(invoiceRes.reason?.message)
        const invoice = invoiceRes.value
        invoice.line_items = lineItemsRes.status === 'fulfilled' ? lineItemsRes.value : []
        invoice.payments   = paymentsRes.status  === 'fulfilled' ? paymentsRes.value  : []
        setInvoice(invoice)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  const loadRaw = async () => {
    if (raw) { setShowRaw(v => !v); return }
    try {
      const data = await invoicesApi.getRaw(id)
      setRaw(data)
      setShowRaw(true)
    } catch {
      setRaw({ error: 'Raw extraction data not available yet.' })
      setShowRaw(true)
    }
  }

  const handleTransition = async (toStatus) => {
    setTransitioning(true)
    try {
      const updated = await invoicesApi.transition(id, toStatus)
      setInvoice(prev => ({ ...prev, status: updated?.status || toStatus }))
    } catch (e) {
      alert(`Transition failed: ${e.message}`)
    } finally {
      setTransitioning(false)
    }
  }

  const handleRecordPayment = async (e) => {
    e.preventDefault()
    try {
      await invoicesApi.recordPayment(id, {
        payment_date: new Date().toISOString().split('T')[0],
        amount: parseFloat(paymentData.amount),
        method: paymentData.method,
        reference: paymentData.reference,
      })
      setShowPaymentForm(false)
      const updated = await invoicesApi.get(id)
      setInvoice(updated)
    } catch (e) {
      alert(`Payment failed: ${e.message}`)
    }
  }

  if (loading) return <div className="p-6"><PageLoader /></div>
  if (error) return <div className="p-6"><ErrorState message={error} onRetry={() => navigate(-1)} /></div>
  if (!invoice) return null

  const transitions = TRANSITIONS[invoice.status] || []

  return (
    <div className="p-6 space-y-5 animate-fade-up max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
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

        {/* Action buttons */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <button onClick={loadRaw} className="btn-secondary text-xs h-8">
            {showRaw ? <EyeOff size={13} /> : <Eye size={13} />}
            {showRaw ? 'Hide Raw' : 'Raw Extraction'}
          </button>
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
          <button
            onClick={() => setShowPaymentForm(v => !v)}
            className="btn-primary text-xs h-8"
          >
            <DollarSign size={13} />
            Record Payment
          </button>
        </div>
      </div>

      {/* Payment form */}
      {showPaymentForm && (
        <div className="card p-5 border-2 animate-fade-up" style={{ borderColor: 'var(--accent)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>Record Payment</h3>
          <form onSubmit={handleRecordPayment} className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>Amount</label>
              <input className="input h-9 text-sm"
                type="number" step="0.01" required
                value={paymentData.amount}
                onChange={e => setPaymentData(p => ({ ...p, amount: e.target.value }))}
                placeholder={String(invoice.grand_total || '')}
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
            <div className="col-span-3 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowPaymentForm(false)} className="btn-secondary text-xs h-8">Cancel</button>
              <button type="submit" className="btn-primary text-xs h-8">Save Payment</button>
            </div>
          </form>
        </div>
      )}

      {/* Raw extraction view */}
      {showRaw && raw && (
        <div className="card overflow-hidden animate-fade-up">
          <div className="px-5 py-3.5 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Raw Extraction</h2>
            {raw.confidence_score !== undefined && (
              <div className="flex items-center gap-2">
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Confidence</span>
                <ConfidenceBar score={raw.confidence_score || invoice.confidence_score} />
              </div>
            )}
          </div>
          <pre className="p-5 text-xs font-mono overflow-x-auto leading-relaxed"
            style={{ color: 'var(--text-secondary)', background: 'var(--bg-secondary)', maxHeight: 320 }}>
            {raw.error
              ? raw.error
              : JSON.stringify(raw.extraction_json || raw, null, 2)
            }
          </pre>
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Invoice info */}
        <Section title="Invoice Details">
          <div className="grid grid-cols-2 gap-4">
            <InfoRow label="Invoice #" value={invoice.invoice_number} mono />
            <InfoRow label="Currency" value={invoice.currency} />
            <InfoRow label="Issue Date" value={formatDate(invoice.issue_date)} />
            <InfoRow label="Due Date" value={formatDate(invoice.due_date)} />
            <InfoRow label="Payment Method" value={invoice.payment_method} />
            <InfoRow label="Tax Rate" value={invoice.tax_percent != null ? `${invoice.tax_percent}%` : null} />
          </div>
          {invoice.description && (
            <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
              <InfoRow label="Description" value={invoice.description} />
            </div>
          )}
        </Section>

        {/* Financials */}
        <Section title="Financials">
          <div className="space-y-3">
            {[
              { label: 'Subtotal', value: formatCurrency(invoice.subtotal, invoice.currency) },
              { label: 'Discount', value: invoice.discount > 0 ? `- ${formatCurrency(invoice.discount, invoice.currency)}` : '—' },
              { label: 'Tax', value: formatCurrency(invoice.total_tax, invoice.currency) },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between text-sm">
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{value}</span>
              </div>
            ))}
            <div className="flex justify-between items-center pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
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

        {/* Vendor */}
        <Section title="Vendor">
          <div className="grid grid-cols-2 gap-4">
            <InfoRow label="Name" value={invoice.vendor?.name} />
            <InfoRow label="Tax ID" value={invoice.vendor?.tax_id} mono />
            <InfoRow label="Email" value={invoice.vendor?.email} />
            <InfoRow label="Phone" value={invoice.vendor?.phone} />
          </div>
        </Section>

        {/* Client */}
        <Section title="Client">
          <div className="grid grid-cols-2 gap-4">
            <InfoRow label="Name" value={invoice.client?.name} />
            <InfoRow label="Tax ID" value={invoice.client?.tax_id} mono />
            <InfoRow label="Email" value={invoice.client?.email} />
            <InfoRow label="Phone" value={invoice.client?.phone} />
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
                      style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
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
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
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
  )
}