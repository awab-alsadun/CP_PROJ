import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'
import { statusConfig, confidenceColor, confidenceLabel } from '../../lib/utils'

export function StatusBadge({ status }) {
  const cfg = statusConfig(status)
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

export function EmptyState({ icon: Icon = Inbox, title = 'Nothing here', description = '' }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'var(--bg-secondary)' }}>
        <Icon size={22} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
      </div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{title}</p>
      {description && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{description}</p>
      )}
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: '#FEF2F2' }}>
        <AlertTriangle size={22} color="#EF4444" strokeWidth={1.5} />
      </div>
      <p className="text-sm font-medium text-red-600">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary mt-4 text-xs">
          Try again
        </button>
      )}
    </div>
  )
}

export function MetricCard({ label, value, sub, icon: Icon, trend, accentColor }) {
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
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>vs last month</span>
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