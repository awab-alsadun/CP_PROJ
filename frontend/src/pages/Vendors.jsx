import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Building2, ChevronLeft, ChevronRight } from 'lucide-react'
import { vendorsApi } from '../lib/api'
import { formatCurrency, truncate } from '../lib/utils'
import { PageLoader, ErrorState, EmptyState } from '../components/ui'

const PAGE_SIZE = 50

export default function Vendors() {
  const navigate = useNavigate()
  const [vendors,  setVendors]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [search,   setSearch]   = useState('')
  const [page,     setPage]     = useState(1)
  const [total,    setTotal]    = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await vendorsApi.list({ page, limit: PAGE_SIZE })
      const list = Array.isArray(res) ? res : (res?.vendors || res?.data || [])
      setVendors(list)
      // res.total will exist when backend adds count; until then use array length as lower bound
      setTotal(res?.total ?? null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { load() }, [load])

  // Client-side search filter on the current page
  const filtered = vendors.filter(v =>
    !search.trim() ||
    v.name?.toLowerCase().includes(search.toLowerCase()) ||
    v.tax_id?.includes(search) ||
    v.email?.toLowerCase().includes(search.toLowerCase())
  )

  const totalPages = total != null ? Math.ceil(total / PAGE_SIZE) : null

  return (
    <div className="p-6 space-y-4 animate-fade-up">
      <div className="flex items-center justify-between">
        <div className="relative w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-muted)' }} />
          <input className="input pl-9 h-9 text-sm" placeholder="Search vendors…"
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
          {total != null ? `${total} total` : ''}
        </span>
      </div>

      <div className="card overflow-hidden">
        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={load} />
          : filtered.length === 0 ? (
            <EmptyState icon={Building2} title="No vendors found"
              description="Vendors are created automatically when invoices are ingested." />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {['Vendor', 'Tax ID', 'Email', 'Phone', 'Total Invoiced', 'Invoices'].map(h => (
                        <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
                          style={{ color: 'var(--text-muted)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(v => (
                      <tr key={v.id}
                        className="table-row-hover cursor-pointer transition-colors"
                        style={{ borderBottom: '1px solid var(--border-subtle)' }}
                        onClick={() => navigate(`/vendors/${v.id}`)}
                      >
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-semibold flex-shrink-0"
                              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                              {v.name?.[0]?.toUpperCase() || 'V'}
                            </div>
                            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                              {truncate(v.name, 30)}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                            {v.tax_id || '—'}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {v.email || '—'}
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {v.phone || '—'}
                        </td>
                        <td className="px-5 py-3.5">
                          <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                            {v.total_billed != null ? formatCurrency(v.total_billed) : '—'}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          {v.invoice_count ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {totalPages != null && totalPages > 1 && (
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