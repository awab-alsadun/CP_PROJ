import { clsx } from 'clsx'
import i18n from '../i18n'

export function cn(...args) {
  return clsx(...args)
}

export function formatCurrency(amount, currency = 'USD') {
  if (amount === null || amount === undefined) return '—'
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
  }).format(amount)
  // Wrap in Unicode directional isolate marks so the LTR currency string
  // (symbol + digits) renders as one atomic unit inside RTL (Arabic) contexts,
  // preventing the bidi algorithm from visually reordering the currency symbol.
  return `⁦${formatted}⁩`
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
  if (diff < 60) return i18n.t('topbar.justNow')
  if (diff < 3600) return i18n.t('topbar.minutesAgo', { count: Math.floor(diff / 60) })
  if (diff < 86400) return i18n.t('topbar.hoursAgo', { count: Math.floor(diff / 3600) })
  if (diff < 2592000) return i18n.t('topbar.daysAgo', { count: Math.floor(diff / 86400) })
  return formatDate(dateStr)
}

export function daysOverdue(dueDateStr) {
  if (!dueDateStr) return 0
  const diff = Math.floor((Date.now() - new Date(dueDateStr)) / 86400000)
  return diff > 0 ? diff : 0
}

export function confidenceColor(score) {
  if (score === null || score === undefined) return 'text-[var(--text-muted)]'
  if (score >= 0.85) return 'confidence-high'
  if (score >= 0.6) return 'confidence-mid'
  return 'confidence-low'
}

export function confidenceLabel(score) {
  if (score === null || score === undefined) return i18n.t('confidence.na')
  if (score >= 0.85) return i18n.t('confidence.high')
  if (score >= 0.6) return i18n.t('confidence.medium')
  return i18n.t('confidence.low')
}

export function statusConfig(status) {
  const configs = {
    draft:          { label: i18n.t('common.status.draft'),   class: 'badge-draft',          dot: '#A8A89F' },
    sent:           { label: i18n.t('common.status.sent'),    class: 'badge-sent',           dot: '#3B82F6' },
    paid:           { label: i18n.t('common.status.paid'),    class: 'badge-paid',           dot: '#22C55E' },
    overdue:        { label: i18n.t('common.status.overdue'), class: 'badge-overdue',        dot: '#EF4444' },
    unpaid:         { label: i18n.t('common.status.unpaid'),  class: 'badge-unpaid',         dot: '#6B7280' },
    partially_paid: { label: i18n.t('common.status.partially_paid'), class: 'badge-partially-paid', dot: '#F59E0B' },
  }
  return configs[status] || { label: status, class: 'badge-draft', dot: '#A8A89F' }
}

export function truncate(str, n = 40) {
  if (!str) return ''
  return str.length > n ? str.slice(0, n) + '…' : str
}
