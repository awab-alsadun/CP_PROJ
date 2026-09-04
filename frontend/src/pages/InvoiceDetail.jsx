import { useState, useEffect, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, DollarSign, Send,
  CheckCircle, AlertTriangle, X, FileText,
  ExternalLink, ChevronDown, ChevronUp, ShieldCheck
} from 'lucide-react'
import { invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, daysOverdue } from '../lib/utils'
import {
  StatusBadge, InvoiceTypeBadge, ConfidenceBar, ProgressBar,
  ComplianceFlagBadge, ConfirmDialog, PageLoader, ErrorState
} from '../components/ui'

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ toasts, remove }) {
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-4 end-4 z-50 flex flex-col gap-2 pointer-events-none">
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

// ── Transition config ──────────────────────────────────────────────────────────
function buildTransitionsPayable(t) {
  return {
    unpaid:         [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' },
                     { to: 'overdue', label: t('invoiceDetail.markOverdue'), icon: AlertTriangle, color: '#EF4444' }],
    partially_paid: [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' },
                     { to: 'overdue', label: t('invoiceDetail.markOverdue'), icon: AlertTriangle, color: '#EF4444' }],
    overdue:        [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' }],
    paid:           [],
  }
}

function buildTransitionsReceivable(t) {
  return {
    draft:          [{ to: 'sent',    label: t('invoiceDetail.markAsSent'), icon: Send,          color: '#3B82F6' }],
    sent:           [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' },
                     { to: 'overdue', label: t('invoiceDetail.markOverdue'), icon: AlertTriangle, color: '#EF4444' }],
    unpaid:         [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' },
                     { to: 'overdue', label: t('invoiceDetail.markOverdue'), icon: AlertTriangle, color: '#EF4444' }],
    partially_paid: [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' }],
    overdue:        [{ to: 'paid',    label: t('invoiceDetail.markAsPaid'), icon: CheckCircle,   color: '#22C55E' }],
    paid:           [],
  }
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function InvoiceDetail() {
  const { t, i18n } = useTranslation()
  const dir = i18n.language === 'ar' ? 'rtl' : 'ltr'
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { toasts, add: toast, remove: removeToast } = useToast()

  const isReceivable = location.pathname.startsWith('/receivables')
  const backPath = isReceivable ? '/receivables' : '/payables'

  const [invoice,       setInvoice]       = useState(null)
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState(null)
  const [transitioning, setTransitioning] = useState(false)

  const [flags,         setFlags]         = useState([])
  const [flagsOpen,     setFlagsOpen]     = useState(false)
  const [loadingFlags,  setLoadingFlags]  = useState(false)

  // Single payment modal
  const [showPayModal,  setShowPayModal]  = useState(false)
  const [savingPayment, setSavingPayment] = useState(false)
  const [paymentData,   setPaymentData]   = useState({
    amount: '', method: 'bank_transfer', reference: '',
    payment_date: new Date().toISOString().split('T')[0],
  })

  const [showCN,        setShowCN]        = useState(false)
  const [cnData,        setCnData]        = useState({ amount: '', reason: '' })
  const [cnLoading,     setCnLoading]     = useState(false)

  const [refundTarget,  setRefundTarget]  = useState(null)
  const [refundAmt,     setRefundAmt]     = useState('')
  const [refundLoading, setRefundLoading] = useState(false)

  const [confirmSend,   setConfirmSend]   = useState(false)

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

  const handleViewPdf = async () => {
    try {
      const blob = await invoicesApi.getPdf(id)
      window.open(URL.createObjectURL(blob), '_blank')
    } catch { toast(t('invoiceDetail.pdfNotAvailable'), 'error') }
  }

  const handleTransition = async (toStatus) => {
    setTransitioning(true)
    try {
      await invoicesApi.transition(id, toStatus)
      await loadInvoice()
      toast(t('invoiceDetail.markedAs', { status: t(`common.status.${toStatus}`) }))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setTransitioning(false)
    }
  }

  const handleRecordPayment = async () => {
    setSavingPayment(true)
    try {
      await invoicesApi.recordPayment(id, {
        amount:       parseFloat(paymentData.amount),
        method:       paymentData.method || null,
        reference:    paymentData.reference || null,
        payment_date: paymentData.payment_date,
      })
      setShowPayModal(false)
      setPaymentData({
        amount: '', method: 'bank_transfer', reference: '',
        payment_date: new Date().toISOString().split('T')[0],
      })
      await loadInvoice()
      toast(t('invoiceDetail.paymentRecorded'))
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
      toast(t('invoiceDetail.creditNoteApplied'))
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
      toast(t('invoiceDetail.refundProcessed'))
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
    ? (buildTransitionsReceivable(t)[invoice.status] || [])
    : (buildTransitionsPayable(t)[invoice.status]    || [])
  const canPay    = !['paid'].includes(invoice.status)
  const canCN     = invoice.status === 'paid'
  const paid      = invoice.amount_paid_so_far || 0
  const remaining = Math.max(0, (invoice.grand_total || 0) - paid)
  const od        = daysOverdue(invoice.due_date)

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
                  {invoice.invoice_number || t('invoiceDetail.invoice')}
                </h1>
                <StatusBadge invoice={invoice} />
                <InvoiceTypeBadge type={invType} />
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                {t('invoiceDetail.issued', { date: formatDate(invoice.issue_date) })}
                {invoice.due_date && (
                  <span style={{ color: od > 0 ? '#EF4444' : 'inherit' }}>
                    {' · '}{t('invoiceDetail.due', { date: formatDate(invoice.due_date) })}
                    {od > 0 && ` ${t('invoiceDetail.daysOverdueSuffix', { days: od })}`}
                  </span>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap justify-end">
            <button onClick={handleViewPdf} className="btn-secondary text-xs h-8">
              <FileText size={13} /> {t('invoiceDetail.pdf')} <ExternalLink size={11} />
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
              <button
                onClick={() => {
                  setPaymentData(p => ({ ...p, amount: remaining.toFixed(2) }))
                  setShowPayModal(true)
                }}
                className="btn-primary text-xs h-8"
              >
                <DollarSign size={13} /> {t('invoiceDetail.recordPayment')}
              </button>
            )}

            {canCN && (
              <button onClick={() => setShowCN(true)} className="btn-secondary text-xs h-8">
                {t('invoiceDetail.applyCreditNote')}
              </button>
            )}
          </div>
        </div>

        {/* Payment progress */}
        {(invoice.amount_paid_so_far != null || paid > 0) && (
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('invoiceDetail.paymentProgress')}</h2>
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
              <span style={{ color: '#22C55E' }}>{t('invoiceDetail.paidLabel', { amount: formatCurrency(paid, invoice.currency) })}</span>
              {remaining > 0 && <span style={{ color: '#EF4444' }}>{t('invoiceDetail.remainingLabel', { amount: formatCurrency(remaining, invoice.currency) })}</span>}
            </div>
          </div>
        )}

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Section title={t('invoiceDetail.invoiceDetails')}>
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label={t('invoiceDetail.invoiceNumberField')} value={invoice.invoice_number} mono />
              <InfoRow label={t('invoiceDetail.currency')}       value={invoice.currency} />
              <InfoRow label={t('invoiceDetail.issueDate')}     value={formatDate(invoice.issue_date)} />
              <InfoRow label={t('invoiceDetail.dueDate')}       value={formatDate(invoice.due_date)} />
              <InfoRow label={t('invoiceDetail.paymentMethod')} value={invoice.payment_method} />
              <InfoRow label={t('invoiceDetail.taxRate')}       value={invoice.tax_percent != null ? `${invoice.tax_percent}%` : null} />
            </div>
            {invoice.description && (
              <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
                <InfoRow label={t('invoiceDetail.description')} value={invoice.description} />
              </div>
            )}
          </Section>

          <Section title={t('invoiceDetail.financials')}>
            <div className="space-y-3">
              {[
                { label: t('invoiceDetail.subtotal'), value: formatCurrency(invoice.subtotal,  invoice.currency) },
                { label: t('invoiceDetail.discount'), value: invoice.discount > 0 ? `- ${formatCurrency(invoice.discount, invoice.currency)}` : '—' },
                { label: t('invoiceDetail.tax'),      value: formatCurrency(invoice.total_tax, invoice.currency) },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between text-sm">
                  <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                  <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{value}</span>
                </div>
              ))}
              <div className="flex justify-between items-center pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('invoiceDetail.grandTotal')}</span>
                <span className="font-mono text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {formatCurrency(invoice.grand_total, invoice.currency)}
                </span>
              </div>
              {invoice.confidence_score != null && (
                <div className="flex justify-between items-center pt-2">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('invoiceDetail.extractionConfidence')}</span>
                  <ConfidenceBar score={invoice.confidence_score} />
                </div>
              )}
            </div>
          </Section>

          <Section title={invType === 'receivable' ? t('invoiceDetail.client') : t('invoiceDetail.vendor')}>
            <div className="grid grid-cols-2 gap-4">
              {invType === 'receivable' ? (
                <>
                  <InfoRow label={t('invoiceDetail.name')}   value={invoice.client?.name} />
                  <InfoRow label={t('invoiceDetail.taxId')} value={invoice.client?.tax_id} mono />
                  <InfoRow label={t('invoiceDetail.email')}  value={invoice.client?.email} />
                  <InfoRow label={t('invoiceDetail.phone')}  value={invoice.client?.phone} />
                </>
              ) : (
                <>
                  <InfoRow label={t('invoiceDetail.name')}   value={invoice.vendor?.name} />
                  <InfoRow label={t('invoiceDetail.taxId')} value={invoice.vendor?.tax_id} mono />
                  <InfoRow label={t('invoiceDetail.email')}  value={invoice.vendor?.email} />
                  <InfoRow label={t('invoiceDetail.phone')}  value={invoice.vendor?.phone} />
                </>
              )}
            </div>
          </Section>

          {invType === 'receivable' && invoice.vendor && (
            <Section title={t('invoiceDetail.vendor')}>
              <div className="grid grid-cols-2 gap-4">
                <InfoRow label={t('invoiceDetail.name')}   value={invoice.vendor?.name} />
                <InfoRow label={t('invoiceDetail.taxId')} value={invoice.vendor?.tax_id} mono />
              </div>
            </Section>
          )}
          {invType === 'payable' && invoice.client && (
            <Section title={t('invoiceDetail.client')}>
              <div className="grid grid-cols-2 gap-4">
                <InfoRow label={t('invoiceDetail.name')}   value={invoice.client?.name} />
                <InfoRow label={t('invoiceDetail.taxId')} value={invoice.client?.tax_id} mono />
              </div>
            </Section>
          )}
        </div>

        {/* Line items */}
        {invoice.line_items?.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('invoiceDetail.lineItems')}</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {[t('common.table.description'), t('common.table.qty'), t('common.table.unitPrice'), t('common.table.discount'), t('common.table.subtotal')].map(h => (
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
          <Section title={t('invoiceDetail.paymentHistory')}>
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
                      {formatDate(p.payment_date)} · {p.method || t('confidence.na')}
                      {p.reference && ` · ${t('invoiceDetail.refPrefix', { ref: p.reference })}`}
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
                        {t('invoiceDetail.refund')}
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
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{t('invoiceDetail.complianceStatus')}</h2>
              {flags.length > 0 && (
                <span className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                  style={{ background: '#FEF2F2', color: '#EF4444' }}>
                  {t('invoiceDetail.flagCount', { count: flags.length })}
                </span>
              )}
            </div>
            {loadingFlags
              ? <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('invoiceDetail.loadingShort')}</span>
              : flagsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />
            }
          </button>

          {flagsOpen && (
            <div className="border-t px-5 py-4" style={{ borderColor: 'var(--border)' }}>
              {flags.length === 0 ? (
                <div className="flex items-center gap-2 text-sm" style={{ color: '#22C55E' }}>
                  <CheckCircle size={14} /> {t('invoiceDetail.noComplianceIssues')}
                </div>
              ) : (
                <div className="space-y-2">
                  {flags.map((f, i) => (
                    <div key={f.id || i}
                      className="flex items-start gap-3 p-3 rounded-xl border-s-4"
                      style={{
                        background: 'var(--bg-secondary)',
                        [dir === 'rtl' ? 'borderRightColor' : 'borderLeftColor']: f.severity === 'high' ? '#EF4444' : f.severity === 'medium' ? '#F59E0B' : 'var(--border)',
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

      {/* ── Record Payment Modal ───────────────────────────────── */}
      {showPayModal && (
        <Modal title={t('invoiceDetail.recordPaymentTitle')} onClose={() => setShowPayModal(false)}>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <FieldRow label={t('invoiceDetail.amountRequired')}>
                <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                  value={paymentData.amount}
                  onChange={e => setPaymentData(p => ({ ...p, amount: e.target.value }))}
                  placeholder={remaining.toFixed(2)} />
              </FieldRow>
              <FieldRow label={t('invoiceDetail.dateRequired')}>
                <input className="input h-9 text-sm" type="date"
                  value={paymentData.payment_date}
                  onChange={e => setPaymentData(p => ({ ...p, payment_date: e.target.value }))} />
              </FieldRow>
              <FieldRow label={t('invoiceDetail.method')}>
                <select className="input h-9 text-sm" value={paymentData.method}
                  onChange={e => setPaymentData(p => ({ ...p, method: e.target.value }))}>
                  <option value="bank_transfer">{t('common.paymentMethods.bank_transfer')}</option>
                  <option value="credit_card">{t('common.paymentMethods.credit_card')}</option>
                  <option value="cash">{t('common.paymentMethods.cash')}</option>
                  <option value="cheque">{t('common.paymentMethods.cheque')}</option>
                  <option value="wire">{t('common.paymentMethods.wire')}</option>
                  <option value="other">{t('common.paymentMethods.other')}</option>
                </select>
              </FieldRow>
              <FieldRow label={t('invoiceDetail.reference')}>
                <input className="input h-9 text-sm" value={paymentData.reference}
                  onChange={e => setPaymentData(p => ({ ...p, reference: e.target.value }))}
                  placeholder="TXN-001" />
              </FieldRow>
            </div>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('invoiceDetail.remainingBalanceLabel')} <span className="font-mono font-medium">{formatCurrency(remaining, invoice.currency)}</span>
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowPayModal(false)} className="btn-secondary text-xs h-8">{t('common.cancel')}</button>
              <button
                onClick={handleRecordPayment}
                disabled={savingPayment || !paymentData.amount}
                className="btn-primary text-xs h-8 disabled:opacity-50"
              >
                {savingPayment ? t('invoiceDetail.saving') : t('invoiceDetail.confirmPayment')}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Credit Note Modal ─────────────────────────────────── */}
      {showCN && (
        <Modal title={t('invoiceDetail.applyCreditNoteTitle')} onClose={() => setShowCN(false)}>
          <div className="space-y-3">
            <FieldRow label={t('invoiceDetail.amountRequired')}>
              <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                value={cnData.amount}
                onChange={e => setCnData(p => ({ ...p, amount: e.target.value }))} />
            </FieldRow>
            <FieldRow label={t('invoiceDetail.reason')}>
              <textarea className="input text-sm resize-none" rows={2}
                value={cnData.reason}
                onChange={e => setCnData(p => ({ ...p, reason: e.target.value }))}
                placeholder={t('invoiceDetail.reasonPlaceholder')} />
            </FieldRow>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCN(false)} className="btn-secondary text-xs h-8">{t('common.cancel')}</button>
              <button onClick={handleCreditNote} disabled={cnLoading || !cnData.amount}
                className="btn-primary text-xs h-8 disabled:opacity-50">
                {cnLoading ? t('invoiceDetail.applying') : t('invoiceDetail.applyCreditNote')}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Refund Modal ──────────────────────────────────────── */}
      {refundTarget && (
        <Modal title={t('invoiceDetail.processRefundTitle')} onClose={() => setRefundTarget(null)}>
          <div className="space-y-3">
            <FieldRow label={t('invoiceDetail.refundAmountRequired')}>
              <input className="input h-9 text-sm font-mono" type="number" step="0.01"
                value={refundAmt}
                onChange={e => setRefundAmt(e.target.value)} />
            </FieldRow>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setRefundTarget(null)} className="btn-secondary text-xs h-8">{t('common.cancel')}</button>
              <button onClick={handleRefund} disabled={refundLoading || !refundAmt}
                className="text-xs h-8 px-3 rounded-xl font-medium disabled:opacity-50"
                style={{ background: '#EF4444', color: '#fff' }}>
                {refundLoading ? t('invoiceDetail.processing') : t('invoiceDetail.confirmRefund')}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Send confirm ──────────────────────────────────────── */}
      <ConfirmDialog
        open={confirmSend}
        title={t('invoiceDetail.sendInvoiceTitle')}
        message={t('invoiceDetail.sendInvoiceMessage', { email: invoice.client?.email || t('invoiceDetail.theClient') })}
        onConfirm={() => { setConfirmSend(false); handleTransition('sent') }}
        onCancel={() => setConfirmSend(false)}
        confirmLabel={t('invoiceDetail.sendInvoiceConfirm')}
      />
    </>
  )
}