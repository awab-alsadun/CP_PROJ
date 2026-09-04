import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, ChevronLeft, ChevronRight, FileUp, AlertCircle, DollarSign, Send, Files } from 'lucide-react'
import { invoicesApi, analyticsApi } from '../lib/api'
import { formatCurrency, formatDate, daysOverdue, truncate } from '../lib/utils'
import { StatusBadge, MetricCard, PageLoader, ErrorState, EmptyState } from '../components/ui'

const STATUSES = ['all', 'draft', 'sent', 'partially_paid', 'paid', 'overdue']
const PAGE_SIZE = 20

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function Receivables() {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const STATUS_LABELS = {
    all: t('common.status.all'), draft: t('common.status.draft'), sent: t('common.status.sent'),
    partially_paid: t('common.status.partially_paid'), paid: t('common.status.paid'),
    overdue: t('common.status.overdue'),
  }

  // Table state
  const [invoices, setInvoices] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [search,   setSearch]   = useState('')
  const [status,   setStatus]   = useState('all')
  const [page,     setPage]     = useState(1)
  const [total,    setTotal]    = useState(0)

  // Metric card state — fetched once, never touched by table filters
  const [metrics, setMetrics] = useState(null)

  const debouncedSearch = useDebounce(search)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await invoicesApi.list({
        page, limit: PAGE_SIZE, status, search: debouncedSearch,
        invoice_type: 'receivable',
      })
      setInvoices(res?.data || [])
      setTotal(res?.total ?? 0)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [page, status, debouncedSearch])

  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [status, debouncedSearch])

  // Metrics: one call on mount, isolated from all table state
  useEffect(() => {
    analyticsApi.pageMetrics('receivable')
      .then(m => setMetrics(m))
      .catch(() => {})
  }, [])

  const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 0

  return (
    <div className="p-6 space-y-4 animate-fade-up">

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <MetricCard label={t('receivables.totalReceivables')} value={metrics ? String(metrics.total_count)          : '—'} icon={Files}       accentColor="#3B82F6" />
        <MetricCard label={t('receivables.outstanding')}      value={metrics ? formatCurrency(metrics.outstanding)   : '—'} icon={DollarSign}  accentColor="#22C55E" />
        <MetricCard label={t('receivables.overdue')}          value={metrics ? String(metrics.overdue_count)         : '—'} icon={AlertCircle} accentColor="#EF4444" />
        <MetricCard label={t('receivables.drafts')}           value={metrics ? String(metrics.draft_count)           : '—'} icon={FileUp}      accentColor="#A8A89F" />
        <MetricCard label={t('receivables.sentAwaiting')}     value={metrics ? formatCurrency(metrics.sent_amt)      : '—'} icon={Send}        accentColor="#3B82F6" />
      </div>

      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute start-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input className="input ps-9 h-9 text-sm" placeholder={t('receivables.searchPlaceholder')}
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="flex gap-1 p-1 rounded-xl border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          {STATUSES.map(s => (
            <button key={s} onClick={() => setStatus(s)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all duration-150"
              style={status === s
                ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                : { color: 'var(--text-muted)' }}>
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={load} />
          : invoices.length === 0 ? (
            <EmptyState icon={FileUp}
              title={status !== 'all' ? t('receivables.noStatusReceivables', { status: STATUS_LABELS[status] }) : t('receivables.noReceivables')}
              description={t('receivables.createHint')} />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {[t('common.table.invoiceNumber'), t('common.table.client'), t('common.table.total'), t('common.table.paid'), t('common.table.remaining'), t('common.table.status'), t('common.table.dueDate')].map(h => (
                        <th key={h} className="text-start px-5 py-3 text-xs font-medium uppercase tracking-wide"
                          style={{ color: 'var(--text-muted)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map(inv => {
                      const paid      = inv.amount_paid_so_far || 0
                      const remaining = (inv.grand_total || 0) - paid
                      const od        = daysOverdue(inv.due_date)
                      return (
                        <tr key={inv.id}
                          className="table-row-hover cursor-pointer transition-colors"
                          style={{ borderBottom: '1px solid var(--border-subtle)' }}
                          onClick={() => navigate(`/receivables/${inv.id}`)}>
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                              {inv.invoice_number || '—'}
                            </span>
                          </td>
                          <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                            {truncate(inv.client?.name || inv.client_name || '—', 24)}
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                              {formatCurrency(inv.grand_total, inv.currency)}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-sm" style={{ color: '#22C55E' }}>
                              {formatCurrency(paid, inv.currency)}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-sm font-medium"
                              style={{ color: remaining > 0 ? '#EF4444' : 'var(--text-muted)' }}>
                              {remaining > 0 ? formatCurrency(remaining, inv.currency) : '—'}
                            </span>
                          </td>
                          <td className="px-5 py-3.5"><StatusBadge invoice={inv} /></td>
                          <td className="px-5 py-3.5 text-sm"
                            style={{ color: od > 0 ? '#EF4444' : 'var(--text-muted)' }}>
                            {formatDate(inv.due_date)}
                            {od > 0 && <span className="ms-1 text-xs">{t('receivables.daysOverdue', { days: od })}</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('common.pageOf', { page, total: totalPages })}</span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="btn-ghost p-1.5 disabled:opacity-40"><ChevronLeft size={14} /></button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1).filter(p => p >= page - 2 && p <= page + 2).map(p => (
                      <button key={p} onClick={() => setPage(p)}
                        className="w-7 h-7 rounded-lg text-xs font-semibold flex items-center justify-center"
                        style={p === page ? { background: 'var(--accent)', color: '#131310' } : { background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                        {p}
                      </button>
                    ))}
                    <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="btn-ghost p-1.5 disabled:opacity-40"><ChevronRight size={14} /></button>
                  </div>
                </div>
              )}
            </>
          )}
      </div>
    </div>
  )
}