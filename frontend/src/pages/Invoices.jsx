import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, truncate } from '../lib/utils'
import { StatusBadge, PageLoader, ErrorState, EmptyState, ConfidenceBar } from '../components/ui'

const STATUSES = ['all', 'draft', 'sent', 'paid', 'overdue']
const PAGE_SIZE = 20

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function Invoices() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [invoices,  setInvoices]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [search,    setSearch]    = useState('')
  const [status,    setStatus]    = useState('all')
  const [page,      setPage]      = useState(1)
  const [total,     setTotal]     = useState(0)
  const [sortField, setSortField] = useState('issue_date')
  const [sortDir,   setSortDir]   = useState('desc')

  const debouncedSearch = useDebounce(search)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await invoicesApi.list({ page, limit: PAGE_SIZE, status, search: debouncedSearch })
      setInvoices(res?.data || [])
      setTotal(res?.total ?? 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, status, debouncedSearch])

  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [status, debouncedSearch])

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('desc') }
  }

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ChevronUp size={12} style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
    return sortDir === 'asc'
      ? <ChevronUp size={12} style={{ color: 'var(--accent)' }} />
      : <ChevronDown size={12} style={{ color: 'var(--accent)' }} />
  }

  const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 0

  return (
    <div className="p-6 space-y-4 animate-fade-up">
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute start-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input className="input ps-9 h-9 text-sm" placeholder={t('invoicesLegacy.searchPlaceholder')}
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
              {s === 'all' ? t('common.status.all') : t(`common.status.${s}`)}
            </button>
          ))}
        </div>
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{total ? t('common.total', { count: total }) : ''}</span>
      </div>

      <div className="card overflow-hidden">
        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={load} />
          : invoices.length === 0 ? (
            <EmptyState
              title={status !== 'all' ? t('invoicesLegacy.noStatusInvoices', { status: t(`common.status.${status}`) }) : t('invoicesLegacy.noInvoices')}
              description={status !== 'all' ? t('invoicesLegacy.noStatusDescription', { status }) : t('invoicesLegacy.uploadHint')}
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {[
                        { labelKey: 'common.table.invoiceNumber',  field: 'invoice_number' },
                        { labelKey: 'common.table.vendor',     field: null },
                        { labelKey: 'common.table.client',     field: null },
                        { labelKey: 'common.table.issueDate', field: 'issue_date' },
                        { labelKey: 'common.table.dueDate',   field: 'due_date' },
                        { labelKey: 'common.table.amount',     field: 'grand_total' },
                        { labelKey: 'common.table.status',     field: 'status' },
                        { labelKey: 'invoicesLegacy.confidence', field: 'confidence_score' },
                      ].map(({ labelKey, field }) => (
                        <th key={labelKey}
                          className={`text-start px-5 py-3 text-xs font-medium uppercase tracking-wide ${field ? 'cursor-pointer select-none' : ''}`}
                          style={{ color: 'var(--text-muted)' }}
                          onClick={() => field && toggleSort(field)}>
                          <span className="flex items-center gap-1">
                            {t(labelKey)}
                            {field && <SortIcon field={field} />}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map(inv => (
                      <tr key={inv.id}
                        className="table-row-hover cursor-pointer transition-colors"
                        style={{ borderBottom: '1px solid var(--border-subtle)' }}
                        onClick={() => navigate(`/${inv.invoice_type === 'receivable' ? 'receivables' : 'payables'}/${inv.id}`)}>
                        <td className="px-5 py-3.5">
                          <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                            {inv.invoice_number || '—'}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {truncate(inv.vendor?.name || inv.vendor_name || '—', 24)}
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {truncate(inv.client?.name || inv.client_name || '—', 24)}
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-muted)' }}>{formatDate(inv.issue_date)}</td>
                        <td className="px-5 py-3.5 text-sm"
                          style={{ color: inv.status === 'overdue' ? '#EF4444' : 'var(--text-muted)' }}>
                          {formatDate(inv.due_date)}
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                            {formatCurrency(inv.grand_total, inv.currency)}
                          </span>
                        </td>
                        <td className="px-5 py-3.5"><StatusBadge status={inv.status} /></td>
                        <td className="px-5 py-3.5"><ConfidenceBar score={inv.confidence_score} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{t('common.pageOf', { page, total: totalPages })}</span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                      className="btn-ghost p-1.5 disabled:opacity-40"><ChevronLeft size={14} /></button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                      .filter(p => p >= page - 2 && p <= page + 2)
                      .map(p => (
                        <button key={p} onClick={() => setPage(p)}
                          className="w-7 h-7 rounded-lg text-xs font-semibold flex items-center justify-center"
                          style={p === page
                            ? { background: 'var(--accent)', color: '#131310' }
                            : { background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                          {p}
                        </button>
                      ))}
                    <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                      className="btn-ghost p-1.5 disabled:opacity-40"><ChevronRight size={14} /></button>
                  </div>
                </div>
              )}
            </>
          )}
      </div>
    </div>
  )
}
