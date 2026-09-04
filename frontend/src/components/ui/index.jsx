import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { statusConfig, confidenceColor, confidenceLabel } from '../../lib/utils'

// ── Existing components ───────────────────────────────────────────────────────

export function StatusBadge({ status, invoice }) {
  const { t } = useTranslation()
  // Composite: overdue invoice that has received a partial payment.
  // Does NOT introduce a new DB status — purely a display-layer derivation.
  if (invoice?.status === 'overdue' && Number(invoice?.amount_paid_so_far) > 0) {
    return (
      <span
        className="badge"
        style={{ background: '#FEF2F2', color: '#F87171', border: '1px solid #FECACA' }}
      >
        <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ background: '#F87171' }} />
        {t('ui.partialOverdue')}
      </span>
    )
  }

  // Backward-compatible: accepts either an invoice object or a plain status string.
  // Allocation result rows (which only have a status string) continue to work unchanged.
  const resolvedStatus = invoice ? invoice.status : status
  const cfg = statusConfig(resolvedStatus)
  return (
    <span className={cfg.class}>
      <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ background: cfg.dot }} />
      {cfg.label}
    </span>
  )
}

export function ConfidenceBar({ score }) {
  if (score === null || score === undefined) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: score >= 0.85 ? '#22C55E' : score >= 0.6 ? '#F59E0B' : '#EF4444'
          }}
        />
      </div>
      <span className={`text-xs font-mono font-medium ${confidenceColor(score)}`}>
        {pct}%
      </span>
    </div>
  )
}

export function Spinner({ size = 16, className = '' }) {
  return (
    <Loader2
      size={size}
      className={`animate-spin ${className}`}
      style={{ color: 'var(--text-muted)' }}
    />
  )
}

export function PageLoader() {
  return (
    <div className="flex-1 flex items-center justify-center h-64">
      <Spinner size={24} />
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, description = '' }) {
  const { t } = useTranslation()
  const resolvedTitle = title ?? t('ui.nothingHere')
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'var(--bg-secondary)' }}>
        <Icon size={22} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
      </div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{resolvedTitle}</p>
      {description && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{description}</p>
      )}
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: '#FEF2F2' }}>
        <AlertTriangle size={22} color="#EF4444" strokeWidth={1.5} />
      </div>
      <p className="text-sm font-medium text-red-600">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary mt-4 text-xs">
          {t('ui.tryAgain')}
        </button>
      )}
    </div>
  )
}

export function MetricCard({ label, value, sub, icon: Icon, trend, accentColor }) {
  const { t } = useTranslation()
  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium tracking-wide uppercase"
          style={{ color: 'var(--text-muted)' }}>
          {label}
        </span>
        {Icon && (
          <div className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: accentColor ? `${accentColor}18` : 'var(--bg-secondary)' }}>
            <Icon size={16} style={{ color: accentColor || 'var(--text-secondary)' }} strokeWidth={1.8} />
          </div>
        )}
      </div>
      <div>
        <p className="text-2xl font-display font-semibold leading-none"
          style={{ color: 'var(--text-primary)' }}>
          {value}
        </p>
        {sub && (
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>{sub}</p>
        )}
      </div>
      {trend !== undefined && (
        <div className="flex items-center gap-1">
          <span className={`text-xs font-medium ${trend >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
            {trend >= 0 ? '+' : ''}{trend}%
          </span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('ui.vsLastMonth')}</span>
        </div>
      )}
    </div>
  )
}

export function SectionHeader({ title, action }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
      {action}
    </div>
  )
}

// ── New components ────────────────────────────────────────────────────────────

export function InvoiceTypeBadge({ type }) {
  const { t } = useTranslation()
  const isPayable = type === 'payable'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold tracking-wide"
      style={{
        background: isPayable ? '#EFF6FF' : '#F0FDF4',
        color: isPayable ? '#3B82F6' : '#16A34A',
        border: `1px solid ${isPayable ? '#BFDBFE' : '#BBF7D0'}`,
      }}
    >
      {isPayable ? t('ui.apAbbrev') : t('ui.arAbbrev')}
    </span>
  )
}

export function ProgressBar({ value, max, color = '#22C55E', height = 6 }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="w-full rounded-full overflow-hidden" style={{ height, background: 'var(--border)' }}>
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  )
}

export function ComplianceFlagBadge({ severity }) {
  const { t } = useTranslation()
  const cfg = {
    high:   { label: t('ui.severityHigh'),   bg: '#FEF2F2', color: '#EF4444', border: '#FECACA' },
    medium: { label: t('ui.severityMedium'), bg: '#FFFBEB', color: '#F59E0B', border: '#FDE68A' },
    low:    { label: t('ui.severityLow'),    bg: 'var(--bg-secondary)', color: 'var(--text-muted)', border: 'var(--border)' },
  }[severity] || { label: severity, bg: 'var(--bg-secondary)', color: 'var(--text-muted)', border: 'var(--border)' }

  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
      style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}
    >
      {cfg.label}
    </span>
  )
}

export function ConfirmDialog({ open, title, message, onConfirm, onCancel, confirmLabel, danger = false }) {
  const { t } = useTranslation()
  const resolvedConfirmLabel = confirmLabel ?? t('ui.confirm')
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.45)' }}
        onClick={onCancel}
      />
      <div
        className="relative w-full max-w-sm rounded-2xl border p-6 shadow-xl animate-fade-up"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
      >
        <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{title}</h3>
        <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>{message}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="btn-secondary text-sm">{t('ui.cancel')}</button>
          <button
            onClick={onConfirm}
            className="text-sm px-4 py-2 rounded-xl font-medium transition-all"
            style={{
              background: danger ? '#EF4444' : 'var(--accent)',
              color: danger ? '#fff' : '#131310',
            }}
          >
            {resolvedConfirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let _addToast = null

export function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([])

  React.useEffect(() => {
    _addToast = (message, type = 'success') => {
      const id = Date.now()
      setToasts(p => [...p, { id, message, type }])
      setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
    }
    return () => { _addToast = null }
  }, [])

  return (
    <>
      {children}
      <div className="fixed bottom-4 end-4 z-[200] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <div
            key={t.id}
            className="flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium animate-fade-up pointer-events-auto"
            style={{
              background: 'var(--bg-card)',
              border: `1px solid ${t.type === 'error' ? '#FECACA' : t.type === 'warning' ? '#FDE68A' : '#BBF7D0'}`,
              color: t.type === 'error' ? '#EF4444' : t.type === 'warning' ? '#F59E0B' : '#16A34A',
              minWidth: 260,
            }}
          >
            {t.message}
          </div>
        ))}
      </div>
    </>
  )
}

export function toast(message, type = 'success') {
  if (_addToast) _addToast(message, type)
}

import React from 'react'