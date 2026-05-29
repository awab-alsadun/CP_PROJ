import { useState, useEffect, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Eye, EyeOff, DollarSign, Send,
  CheckCircle, AlertTriangle, X, FileCode, FileText,
  ExternalLink, ChevronDown, ChevronUp, ShieldCheck
} from 'lucide-react'
import { invoicesApi, paymentsApi } from '../lib/api'
import { formatCurrency, formatDate, daysOverdue } from '../lib/utils'
import {
  StatusBadge, InvoiceTypeBadge, ConfidenceBar, ProgressBar,
  ComplianceFlagBadge, ConfirmDialog, PageLoader, ErrorState
} from '../components/ui'

// ── Toast ─────────────────────────────────────────────────────────────────────
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

// ── Sub-components ─────────────────────────────────────────────────────────────
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

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl border p-6 shadow-xl animate-fade-up"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          <button onClick={onClose} className="btn-ghost p-1.5 rounded-lg"><X size={13} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function FieldRow({ label, children }) {
  return (
    <div>
      <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>{label}</label>
      {children}
    </div>
  )
}

// ── Transition config (legacy + new statuses) ──────────────────────────────────
const TRANSITIONS_PAYABLE = {
  unpaid:         [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' },
                   { to: 'overdue', label: 'Mark Overdue',   icon: AlertTriangle, color: '#EF4444' }],
  partially_paid: [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' },
                   { to: 'overdue', label: 'Mark Overdue',   icon: AlertTriangle, color: '#EF4444' }],
  overdue:        [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' }],
  paid:           [],
}

const TRANSITIONS_RECEIVABLE = {
  draft:          [{ to: 'sent',    label: 'Mark as Sent',   icon: Send,          color: '#3B82F6' }],
  sent:           [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' },
                   { to: 'overdue', label: 'Mark Overdue',   icon: AlertTriangle, color: '#EF4444' }],
  unpaid:         [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' },
                   { to: 'overdue', label: 'Mark Overdue',   icon: AlertTriangle, color: '#EF4444' }],
  partially_paid: [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' }],
  overdue:        [{ to: 'paid',    label: 'Mark as Paid',   icon: CheckCircle,   color: '#22C55E' }],
  paid:           [],
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function InvoiceDetail() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { toasts, add: toast, remove: removeToast } = useToast()

  // Determine type from URL path
  const isReceivable = location.pathname.startsWith('/receivables')
  const backPath = isReceivable ? '/receivables' : '/payables'

  const [invoice,         setInvoice]         = useState(null)
  const [raw,             setRaw]             = useState(null)
  const [showRaw,         setShowRaw]         = useState(false)
  const [loading,         setLoading]         = useState(true)
  const [error,           setError]           = useState(null)
  const [transitioning,   setTransitioning]   = useState(false)
  const [loadingRaw,      setLoadingRaw]      = useState(false)

  // Compliance flags
  const [flags,           setFlags]           = useState([])
  const [flagsOpen,       setFlagsOpen]       = useState(false)
  const [loadingFlags,    setLoadingFlags]    = useState(false)

  // FIFO payment modal
  const [showPayModal,    setShowPayModal]    = useState(false)
  const [payLoading,      setPayLoading]      = useState(false)
  const [allocResult,     setAllocResult]     = useState(null)
  const [payData,         setPayData]         = useState({
    amount: '', method: 'bank_transfer', reference: '',
    payment_date: new Date().toISOString().split('T')[0],
  })

  // Legacy payment form (direct to invoice)
  const [showDirectPay,   setShowDirectPay]   = useState(false)
  const [savingPayment,   setSavingPayment]   = useState(false)
  const [paymentData,     setPaymentData]     = useState({
    amount: '', method: 'bank_transfer', reference: '',
    payment_date: new Date().toISOString().split('T')[0],
  })

  // Credit note
  const [showCN,          setShowCN]          = useState(false)
  const [cnData,          setCnData]          = useState({ amount: '', reason: '' })
  const [cnLoading,       setCnLoading]       = useState(false)

  // Refund
  const [refundTarget,    setRefundTarget]    = useState(null) // { payment_id, amount }
  const [refundAmt,       setRefundAmt]       = useState('')
  const [refundLoading,   setRefundLoading]   = useState(false)

  // Send confirm
  const [confirmSend,     setConfirmSend]     = useState(false)

  const loadInvoice = useCallback(async () => {
    try {
      const [invoiceRes, lineItemsRes, paymentsRes] = await Promise.allSettled([
        invoicesApi.get(id),
        invoicesApi.getLineItems(id),
        invoicesApi.getPayments(id),
      ])
      if (invoiceRes.status === 'rejected') throw new Error(invoiceRes.reason?.message)
      const inv = invoiceRes.value
      inv.line_items = lineItemsRes.status === 'fulfilled' ? (lineItemsRes.value?.data || lineItemsRes.value || []) : []
      inv.payments   = paymentsRes.status  === 'fulfilled' ? (paymentsRes.value?.data  || paymentsRes.value  || []) : []
      setInvoice(inv)
    } catch (e) {
      setError(e.message)
    }
  }, [id])

  useEffect(() => {
    setLoading(true)
    loadInvoice().finally(() => setLoading(false))
  }, [loadInvoice])

  const loadFlags = async () => {
    setLoadingFlags(true)
    try {
      const res = await invoicesApi.getComplianceFlags(id)
      setFlags(res?.data || res || [])
    } catch { setFlags([]) }
    finally { setLoadingFlags(false) }
  }

  const toggleFlags = () => {
    if (!flagsOpen && flags.length === 0) loadFlags()
    setFlagsOpen(v => !v)
  }

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

  const handleViewPdf = async () => {
    try {
      const blob = await invoicesApi.getPdf(id)
      window.open(URL.createObjectURL(blob), '_blank')
    } catch { toast('PDF not available for this invoice', 'error') }
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

  // FIFO allocation payment
  const handleAllocate = async () => {
    if (!payData.amount) return
    setPayLoading(true)
    try {
      const inv = invoice
      const entityId   = isReceivable ? inv.client_id  : inv.vendor_id
      const entityType = isReceivable ? 'client'       : 'vendor'
      const res = await paymentsApi.allocate({
        entity_id:    entityId,
        entity_type:  entityType,
        amount:       parseFloat(payData.amount),
        currency:     inv.currency,
        method:       payData.method || null,
        reference:    payData.reference || null,
        payment_date: payData.payment_date,
      })
      setAllocResult(res)
      await loadInvoice()
      toast(`Payment of ${formatCurrency(parseFloat(payData.amount), inv.currency)} allocated`)
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setPayLoading(false)
    }
  }

  // Direct invoice payment (legacy)
  const handleRecordPayment = async () => {
    setSavingPayment(true)
    try {
      await invoicesApi.recordPayment(id, {
        amount: parseFloat(paymentData.amount),
        method: paymentData.method || null,
        reference: paymentData.reference || null,
        payment_date: paymentData.payment_date,
      })
      setShowDirectPay(false)
      setPaymentData({ amount: '', method: 'bank_transfer', reference: '', payment_date: new Date().toISOString().split('T')[0] })
      await loadInvoice()
      toast('Payment recorded successfully')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setSavingPayment(false)
    }
  }

  const handleCreditNote = async () => {
    setCnLoading(true)
    try {
      await invoicesApi.creditNote(id, { amount: parseFloat(cnData.amount), reason: cnData.reason })
      setShowCN(false)
      setCnData({ amount: '', reason: '' })
      await loadInvoice()
      toast('Credit note applied')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setCnLoading(false)
    }
  }

  const handleRefund = async () => {
    setRefundLoading(true)
    try {
      await invoicesApi.refund(id, { payment_id: refundTarget.payment_id, amount: parseFloat(refundAmt) })
      setRefundTarget(null)
      setRefundAmt('')
      await loadInvoice()
      toast('Refund processed')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setRefundLoading(false)
    }
  }

  if (loading) return <div className="p-6"><PageLoader /></div>
  if (error)   return <div className="p-6"><ErrorState message={error} onRetry={() => navigate(-1)} /></div>
  if (!invoice) return null

  const invType    = invoice.invoice_type || (isReceivable ? 'receivable' : 'payable')
  const transitions = isReceivable
    ? (TRANSITIONS_RECEIVABLE[invoice.status] || [])
    : (TRANSITIONS_PAYABLE[invoice.status]    || [])
  const canPay   = !['paid'].includes(invoice.status)
  const canCN    = invoice.status === 'paid'
  const paid     = invoice.amount_paid_so_far || 0
  const remaining = Math.max(0, (invoice.grand_total || 0) - paid)
  const od       = daysOverdue(invoice.due_date)

  return (
    <>
      <Toast toasts={toasts} remove={removeToast} />

      <div className="p-6 space-y-5 animate-fade-up max-w-5xl">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(backPath)} className="btn-ghost p-2 rounded-xl">
              <ArrowLeft size={16} />
            </button>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {invoice.invoice_number || 'Invoice'}
                </h1>
                <StatusBadge status={invoice.status} />
                <InvoiceTypeBadge type={invType} />
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                Issued {formatDate(invoice.issue_date)}
                {invoice.due_date && (
                  <span style={{ color: od > 0 ? '#EF4444' : 'inherit' }}>
                    {' · Due '}{formatDate(invoice.due_date)}
                    {od > 0 && ` (${od}d overdue)`}
                  </span>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap justify-end">
            <button onClick={handleViewPdf} className="btn-secondary text-xs h-8">
              <FileText size={13} /> PDF <ExternalLink size={11} />
            </button>
            <button onClick={handleLoadRaw} disabled={loadingRaw} className="btn-secondary text-xs h-8 disabled:opacity-50">
              <FileCode size={13} />
              {loadingRaw ? 'Loading…' : showRaw ? 'Hide Raw' : 'View Raw'}
            </button>

            {transitions.map(t => {
              const Icon = t.icon
              return (
                <button
                  key={t.to}
                  onClick={() => t.to === 'sent' ? setConfirmSend(true) : handleTransition(t.to)}
                  disabled={transitioning}
                  className="btn-secondary text-xs h-8 disabled:opacity-50"
                  style={{ borderColor: t.color, color: t.color }}
                >
                  <Icon size={13} />
                  {t.label}
                </button>
              )
            })}

            {canPay && (
              <button onClick={() => { setPayData(p => ({ ...p, amount: remaining.toFixed(2) })); setShowPayModal(true) }}
                className="btn-primary text-xs h-8">
                <DollarSign size={13} /> Record Payment
              </button>
            )}

            {canCN && (
              <button onClick={() => setShowCN(true)} className="btn-secondary text-xs h-8">
                Apply Credit Note
              </button>
            )}
          </div>
        </div>

        {/* Financial summary with progress */}
        {(invoice.amount_paid_so_far != null || paid > 0) && (
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Payment Progress</h2>
              <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                {formatCurrency(paid, invoice.currency)} / {formatCurrency(invoice.grand_total, invoice.currency)}
              </span>
            </div>
            <ProgressBar
              value={paid}
              max={invoice.grand_total || 1}
              color={remaining === 0 ? '#22C55E' : '#D4A847'}
              height={8}
            />
            <div className="flex justify-between text-xs mt-2">
              <span style={{ color: '#22C55E' }}>Paid: {formatCurrency(paid, invoice.currency)}</span>
              {remaining > 0 && <span style={{ color: '#EF4444' }}>Remaining: {formatCurrency(remaining, invoice.currency)}</span>}
            </div>
          </div>
        )}

        {/* Raw extraction panel */}
        {showRaw && raw && (
          <div className="card overflow-hidden animate-fade-up">
            <div className="px-5 py-3.5 border-b flex items-center justify-between"
              style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Raw Extraction</h2>
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
              <InfoRow label="Tax Rate"       value={invoice.tax_percent != null ? `${invoice.tax_percent}%` : null} />
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
                { label: 'Subtotal', value: formatCurrency(invoice.subtotal,   invoice.currency) },
                { label: 'Discount', value: invoice.discount > 0 ? `- ${formatCurrency(invoice.discount, invoice.currency)}` : '—' },
                { label: 'Tax',      value: formatCurrency(invoice.total_tax,  invoice.currency) },
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

          <Section title={invType === 'receivable' ? 'Client' : 'Vendor'}>
            <div className="grid grid-cols-2 gap-4">
              {invType === 'receivable' ? (
                <>
                  <InfoRow label="Name"   value={invoice.client?.name} />
                  <InfoRow label="Tax ID" value={invoice.client?.tax_id} mono />
                  <InfoRow label="Email"  value={invoice.client?.email} />
                  <InfoRow label="Phone"  value={invoice.client?.phone} />
                </>
              ) : (
                <>
                  <InfoRow label="Name"   value={invoice.vendor?.name} />
                  <InfoRow label="Tax ID" value={invoice.vendor?.tax_id} mono />
                  <InfoRow label="Email"  value={invoice.vendor?.email} />
                  <InfoRow label="Phone"  value={invoice.vendor?.phone} />
                </>
              )}
            </div>
          </Section>

          {/* Show the other party too if present */}
          {invType === 'receivable' && invoice.vendor && (
            <Section title="Vendor">
              <div className="grid grid-cols-2 gap-4">
                <InfoRow label="Name"   value={invoice.vendor?.name} />
                <InfoRow label="Tax ID" value={invoice.vendor?.tax_id} mono />
              </div>
            </Section>
          )}
          {invType === 'payable' && invoice.client && (
            <Section title="Client">
              <div className="grid grid-cols-2 gap-4">
                <InfoRow label="Name"   value={invoice.client?.name} />
                <InfoRow label="Tax ID" value={invoice.client?.tax_id} mono />
              </div>
            </Section>
          )}
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
                  <div className="flex items-center gap-2">
                    <CheckCircle size={16} color="#22C55E" />
                    {p.id && (
                      <button
                        onClick={() => { setRefundTarget({ payment_id: p.id, amount: p.amount }); setRefundAmt(String(p.amount)) }}
                        className="btn-ghost text-xs h-6 px-2"
                        style={{ color: '#EF4444', fontSize: 11 }}
                      >
                        Refund
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Compliance flags accordion */}
        <div className="card overflow-hidden">
          <button
            onClick={toggleFlags}
            className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-[var(--bg-secondary)] transition-colors"
          >
            <div className="flex items-center gap-2">
              <ShieldCheck size={15} style={{ color: 'var(--text-muted)' }} />
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Compliance Status</h2>
              {flags.length > 0 && (
                <span className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                  style={{ background: '#FEF2F2', color: '#EF4444' }}>
                  {flags.length} flag{flags.length > 1 ? 's' : ''}
                </span>
              )}
            </div>
            {loadingFlags
              ? <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Loading…</span>
              : flagsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />
            }
          </button>

          {flagsOpen && (
            <div className="border-t px-5 py-4" style={{ borderColor: 'var(--border)' }}>
              {flags.length === 0 ? (
                <div className="flex items-center gap-2 text-sm" style={{ color: '#22C55E' }}>
                  <CheckCircle size={14} /> No compliance issues detected
                </div>
              ) : (
                <div className="space-y-2">
                  {flags.map((f, i) => (
                    <div key={f.id || i}
                      className="flex items-start gap-3 p-3 rounded-xl border-l-4"
                      style={{
                        background: 'var(--bg-secondary)',
                        borderLeftColor: f.severity === 'high' ? '#EF4444' : f.severity === 'medium' ? '#F59E0B' : 'var(--border)',
                      }}>
                      <ComplianceFlagBadge severity={f.severity} />
                      <div className="flex-1">
                        <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{f.flag_type}</p>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{f.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── FIFO Payment Modal ─────────────────────────────────── */}
      {showPayModal && (
        <Modal title="Record Payment (FIFO Allocation)" onClose={() => { setShowPayModal(false); setAllocResult(null) }}>
          {allocResult ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold" style={{ color: '#22C55E' }}>Payment allocated</p>
              {allocResult.allocations?.map((a, i) => (
                <div key={i} className="flex justify-between text-sm px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-secondary)' }}>
                  <span className="font-mono text-xs">{a.invoice_number}</span>
                  <span>{formatCurrency(a.amount_applied, invoice.currency)}</span>
                  <StatusBadge status={a.new_status} />
                </div>
              ))}
              {allocResult.overpayment > 0 && (
                <p className="text-xs" style={{ color: '#F59E0B' }}>
                  Overpayment of {formatCurrency(allocResult.overpayment)} credited.
                </p>
              )}
              <button className="btn-primary w-full" onClick={() => { setShowPayModal(false); setAllocResult(null) }}>
                Done
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label="Amount *">
                  <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                    value={payData.amount}
                    onChange={e => setPayData(p => ({ ...p, amount: e.target.value }))}
                    placeholder={remaining.toFixed(2)} />
                </FieldRow>
                <FieldRow label="Date *">
                  <input className="input h-9 text-sm" type="date"
                    value={payData.payment_date}
                    onChange={e => setPayData(p => ({ ...p, payment_date: e.target.value }))} />
                </FieldRow>
                <FieldRow label="Method">
                  <select className="input h-9 text-sm" value={payData.method}
                    onChange={e => setPayData(p => ({ ...p, method: e.target.value }))}>
                    <option value="bank_transfer">Bank Transfer</option>
                    <option value="credit_card">Credit Card</option>
                    <option value="cash">Cash</option>
                    <option value="check">Check</option>
                    <option value="other">Other</option>
                  </select>
                </FieldRow>
                <FieldRow label="Reference">
                  <input className="input h-9 text-sm" value={payData.reference}
                    onChange={e => setPayData(p => ({ ...p, reference: e.target.value }))}
                    placeholder="TXN-001" />
                </FieldRow>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Allocates across {isReceivable ? 'client' : 'vendor'}'s open invoices via FIFO (earliest first).
              </p>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowPayModal(false)} className="btn-secondary text-xs h-8">Cancel</button>
                <button
                  onClick={handleAllocate}
                  disabled={payLoading || !payData.amount}
                  className="btn-primary text-xs h-8 disabled:opacity-50"
                >
                  {payLoading ? 'Allocating…' : 'Confirm Payment'}
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}

      {/* ── Credit Note Modal ─────────────────────────────────── */}
      {showCN && (
        <Modal title="Apply Credit Note" onClose={() => setShowCN(false)}>
          <div className="space-y-3">
            <FieldRow label="Amount *">
              <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                value={cnData.amount}
                onChange={e => setCnData(p => ({ ...p, amount: e.target.value }))} />
            </FieldRow>
            <FieldRow label="Reason">
              <textarea className="input text-sm resize-none" rows={2}
                value={cnData.reason}
                onChange={e => setCnData(p => ({ ...p, reason: e.target.value }))}
                placeholder="Reason for credit note" />
            </FieldRow>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCN(false)} className="btn-secondary text-xs h-8">Cancel</button>
              <button onClick={handleCreditNote} disabled={cnLoading || !cnData.amount}
                className="btn-primary text-xs h-8 disabled:opacity-50">
                {cnLoading ? 'Applying…' : 'Apply Credit Note'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Refund Modal ──────────────────────────────────────── */}
      {refundTarget && (
        <Modal title="Process Refund" onClose={() => setRefundTarget(null)}>
          <div className="space-y-3">
            <FieldRow label="Refund Amount *">
              <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                value={refundAmt}
                onChange={e => setRefundAmt(e.target.value)} />
            </FieldRow>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setRefundTarget(null)} className="btn-secondary text-xs h-8">Cancel</button>
              <button onClick={handleRefund} disabled={refundLoading || !refundAmt}
                className="text-xs h-8 px-3 rounded-xl font-medium disabled:opacity-50"
                style={{ background: '#EF4444', color: '#fff' }}>
                {refundLoading ? 'Processing…' : 'Confirm Refund'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Send confirm ──────────────────────────────────────── */}
      <ConfirmDialog
        open={confirmSend}
        title="Send Invoice"
        message={`This will send the invoice to ${invoice.client?.email || 'the client'} and generate a PDF. Continue?`}
        onConfirm={() => { setConfirmSend(false); handleTransition('sent') }}
        onCancel={() => setConfirmSend(false)}
        confirmLabel="Send Invoice"
      />
    </>
  )
}

// ── Raw tabs ───────────────────────────────────────────────────────────────────
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
