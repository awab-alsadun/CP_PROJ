import { clsx } from 'clsx'

export function cn(...args) {
  return clsx(...args)
}

export function formatCurrency(amount, currency = 'USD') {
  if (amount === null || amount === undefined) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
  }).format(amount)
}

export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatDateShort(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function formatRelative(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const now = new Date()
  const diff = Math.floor((now - d) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`
  return formatDate(dateStr)
}

export function confidenceColor(score) {
  if (score === null || score === undefined) return 'text-[var(--text-muted)]'
  if (score >= 0.85) return 'confidence-high'
  if (score >= 0.6) return 'confidence-mid'
  return 'confidence-low'
}

export function confidenceLabel(score) {
  if (score === null || score === undefined) return 'N/A'
  if (score >= 0.85) return 'High'
  if (score >= 0.6) return 'Medium'
  return 'Low'
}

export function statusConfig(status) {
  const configs = {
    draft:   { label: 'Draft',   class: 'badge-draft',   dot: '#A8A89F' },
    sent:    { label: 'Sent',    class: 'badge-sent',    dot: '#3B82F6' },
    paid:    { label: 'Paid',    class: 'badge-paid',    dot: '#22C55E' },
    overdue: { label: 'Overdue', class: 'badge-overdue', dot: '#EF4444' },
  }
  return configs[status] || configs.draft
}

export function truncate(str, n = 40) {
  if (!str) return ''
  return str.length > n ? str.slice(0, n) + '…' : str
}