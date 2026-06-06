import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, FileDown, AlertCircle, DollarSign, Files } from 'lucide-react'
import { invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, daysOverdue, truncate } from '../lib/utils'
import { StatusBadge, MetricCard, PageLoader, ErrorState, EmptyState } from '../components/ui'

const STATUSES = ['all', 'unpaid', 'partially_paid', 'paid', 'overdue']
const STATUS_LABELS = { all: 'All', unpaid: 'Unpaid', partially_paid: 'Partial', paid: 'Paid', overdue: 'Overdue' }
const PAGE_SIZE = 20

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function Payables() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [search,   setSearch]   = useState('')
  const [status,   setStatus]   = useState('all')
  const [page,     setPage]     = useState(1)
  const [total,    setTotal]    = useState(0)

  // Mount-cached DB-wide totals (unaffected by filter/search/page)
  const [totalAll,     setTotalAll]     = useState(null)
  const [totalOverdue, setTotalOverdue] = useState(null)

  const debouncedSearch = useDebounce(search)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await invoicesApi.list({
        page, limit: PAGE_SIZE, status, search: debouncedSearch,
        invoice_type: 'payable',
      })
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

  // One-shot DB counts on mount. Partial failures tolerated.
  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      invoicesApi.list({ invoice_type: 'payable', limit: 1 }),
      invoicesApi.list({ invoice_type: 'payable', status: 'overdue', limit: 1 }),
    ]).then(results => {
      if (cancelled) return
      const [allR, overdueR] = results
      setTotalAll(allR.status === 'fulfilled' ? (allR.value?.total ?? 0) : null)
      setTotalOverdue(overdueR.status === 'fulfilled' ? (overdueR.value?.total ?? 0) : null)
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const totalPages = total ? Math.ceil(total / PAGE_SIZE) : 0

  // Visible-on-this-page metrics
  const unpaidAmt    = invoices.filter(i => ['unpaid','partially_paid','overdue'].includes(i.status))
                               .reduce((s, i) => s + ((i.grand_total || 0) - (i.amount_paid_so_far || 0)), 0)
  const overdueCount = invoices.filter(i => i.status === 'overdue').length

  // X / Y display strings. Y is null while loading or on error — degrade to plain X.
  const overdueDisplay = totalOverdue != null ? `${overdueCount} / ${totalOverdue}` : `${overdueCount}`
  const totalDisplay   = totalAll != null ? String(totalAll) : '—'

  return (
    <div className="p-6 space-y-4 animate-fade-up">

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricCard label="Total Payables" value={totalDisplay}              icon={Files}       accentColor="#3B82F6" />
        <MetricCard label="Total Unpaid"   value={formatCurrency(unpaidAmt)} icon={DollarSign}  accentColor="#D4A847" />
        <MetricCard label="Overdue"        value={overdueDisplay}            icon={AlertCircle} accentColor="#EF4444" />
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-muted)' }} />
          <input
            className="input pl-9 h-9 text-sm"
            placeholder="Search invoice #, vendor…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div className="flex gap-1 p-1 rounded-xl border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          {STATUSES.map(s => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all duration-150"
              style={status === s
                ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                : { color: 'var(--text-muted)' }
              }
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={load} />
          : invoices.length === 0 ? (
            <EmptyState
              icon={FileDown}
              title={status !== 'all' ? `No ${STATUS_LABELS[status].toLowerCase()} payables` : 'No payables found'}
              description="Upload vendor invoices to get started."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {['Invoice #', 'Vendor', 'Total', 'Paid', 'Remaining', 'Status', 'Due Date'].map(h => (
                        <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
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
                        <tr
                          key={inv.id}
                          className="table-row-hover cursor-pointer transition-colors"
                          style={{ borderBottom: '1px solid var(--border-subtle)' }}
                          onClick={() => navigate(`/payables/${inv.id}`)}
                        >
                          <td className="px-5 py-3.5">
                            <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                              {inv.invoice_number || '—'}
                            </span>
                          </td>
                          <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                            {truncate(inv.vendor?.name || inv.vendor_name || '—', 24)}
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
                          <td className="px-5 py-3.5">
                            <StatusBadge invoice={inv} />
                          </td>
                          <td className="px-5 py-3.5 text-sm"
                            style={{ color: od > 0 ? '#EF4444' : 'var(--text-muted)' }}>
                            {formatDate(inv.due_date)}
                            {od > 0 && <span className="ml-1 text-xs">({od}d)</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {totalPages > 1 && (
                <div className="flex items-center justify-between px-5 py-3 border-t"
                  style={{ borderColor: 'var(--border)' }}>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1} className="btn-ghost p-1.5 disabled:opacity-40">
                      <ChevronLeft size={14} />
                    </button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                      .filter(p => p >= page - 2 && p <= page + 2)
                      .map(p => (
                        <button key={p} onClick={() => setPage(p)}
                          className="w-7 h-7 rounded-lg text-xs font-semibold flex items-center justify-center"
                          style={p === page
                            ? { background: 'var(--accent)', color: '#131310' }
                            : { background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }
                          }>
                          {p}
                        </button>
                      ))}
                    <button onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages} className="btn-ghost p-1.5 disabled:opacity-40">
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
      </div>
    </div>
  )
}