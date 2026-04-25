import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Filter, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, truncate } from '../lib/utils'
import { StatusBadge, PageLoader, ErrorState, EmptyState, ConfidenceBar } from '../components/ui'

const STATUSES = ['all', 'draft', 'sent', 'paid', 'overdue']
const PAGE_SIZE = 20

export default function Invoices() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [sortField, setSortField] = useState('issue_date')
  const [sortDir, setSortDir] = useState('desc')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { page, limit: PAGE_SIZE }
      if (status !== 'all') params.status = status
      if (search.trim()) params.search = search.trim()
      params.sort = sortField
      params.order = sortDir
      const res = await invoicesApi.list(params)
      const list = Array.isArray(res) ? res : (res?.invoices || res?.data || [])
      setInvoices(list)
      setTotal(res?.total || list.length)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, status, search, sortField, sortDir])

  useEffect(() => { load() }, [load])

  // Reset page on filter change
  useEffect(() => { setPage(1) }, [status, search])

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

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="p-6 space-y-4 animate-fade-up">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-muted)' }} />
          <input
            className="input pl-9 h-9 text-sm"
            placeholder="Search invoice #, vendor, client…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Status tabs */}
        <div className="flex gap-1 p-1 rounded-xl border" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          {STATUSES.map(s => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all duration-150 ${
                status === s
                  ? 'shadow-sm'
                  : ''
              }`}
              style={status === s
                ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                : { color: 'var(--text-muted)' }
              }
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Table card */}
      <div className="card overflow-hidden">
        {loading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : invoices.length === 0 ? (
          <EmptyState title="No invoices found" description="Try adjusting your filters or upload an invoice." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {[
                      { label: 'Invoice #', field: 'invoice_number' },
                      { label: 'Vendor', field: null },
                      { label: 'Client', field: null },
                      { label: 'Issue Date', field: 'issue_date' },
                      { label: 'Due Date', field: 'due_date' },
                      { label: 'Amount', field: 'grand_total' },
                      { label: 'Status', field: 'status' },
                      { label: 'Confidence', field: 'confidence_score' },
                    ].map(({ label, field }) => (
                      <th
                        key={label}
                        className={`text-left px-5 py-3 text-xs font-medium uppercase tracking-wide ${field ? 'cursor-pointer select-none' : ''}`}
                        style={{ color: 'var(--text-muted)' }}
                        onClick={() => field && toggleSort(field)}
                      >
                        <span className="flex items-center gap-1">
                          {label}
                          {field && <SortIcon field={field} />}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoices.map(inv => (
                    <tr
                      key={inv.id}
                      className="table-row-hover cursor-pointer transition-colors"
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      onClick={() => navigate(`/invoices/${inv.id}`)}
                    >
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                          {inv.invoice_number || '—'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        {truncate(inv.vendor?.name || '—', 24)}
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        {truncate(inv.client?.name || '—', 24)}
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-muted)' }}>
                        {formatDate(inv.issue_date)}
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: inv.status === 'overdue' ? '#EF4444' : 'var(--text-muted)' }}>
                        {formatDate(inv.due_date)}
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                          {formatCurrency(inv.grand_total, inv.currency)}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusBadge status={inv.status} />
                      </td>
                      <td className="px-5 py-3.5">
                        <ConfidenceBar score={inv.confidence_score} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="btn-ghost p-1.5 disabled:opacity-40"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const pg = page <= 3 ? i + 1 : page - 2 + i
                    if (pg > totalPages) return null
                    return (
                      <button
                        key={pg}
                        onClick={() => setPage(pg)}
                        className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${pg === page ? 'font-semibold' : ''}`}
                        style={pg === page
                          ? { background: 'var(--accent)', color: '#131310' }
                          : { color: 'var(--text-secondary)' }
                        }
                      >
                        {pg}
                      </button>
                    )
                  })}
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="btn-ghost p-1.5 disabled:opacity-40"
                  >
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