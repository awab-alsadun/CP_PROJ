import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Building2, Plus } from 'lucide-react'
import { vendorsApi } from '../lib/api'
import { EmptyState, ErrorState, PageLoader } from '../components/ui'

const PAGE_SIZE = 50

export default function Vendors() {
  const navigate = useNavigate()
  const [page,    setPage]    = useState(1)
  const [search,  setSearch]  = useState('')
  const [data,    setData]    = useState([])
  const [total,   setTotal]   = useState(0)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await vendorsApi.list({ page, limit: PAGE_SIZE })
      setData(res.data || res || [])
      setTotal(res.total ?? 0)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [page])

  useEffect(() => { load() }, [load])

  const filtered = search
    ? data.filter(v =>
        v.name?.toLowerCase().includes(search.toLowerCase()) ||
        v.email?.toLowerCase().includes(search.toLowerCase())
      )
    : data

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1

  return (
    <div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          gap: 12,
          alignItems: 'center',
        }}>
          <input
            className="input"
            placeholder="Search vendors…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1, fontSize: 13, padding: '6px 12px' }}
          />
          {total > 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {total} total
            </span>
          )}
          <button
            onClick={() => navigate('/vendors/create')}
            className="btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, padding: '6px 14px', whiteSpace: 'nowrap' }}
          >
            <Plus size={14} />
            Create Vendor
          </button>
        </div>

        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={load} />
          : filtered.length === 0 ? (
            <EmptyState icon={Building2} title="No vendors found" />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Name', 'Email', 'Phone', 'Tax ID', 'Credit Balance', 'Invoice Count'].map(h => (
                      <th key={h} style={{
                        padding: '10px 16px', textAlign: 'left', fontSize: 11,
                        fontWeight: 600, textTransform: 'uppercase',
                        letterSpacing: '0.06em', color: 'var(--text-muted)',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(v => (
                    <tr key={v.id} className="table-row-hover" style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 600, fontSize: 13 }}>{v.name}</td>
                      <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>{v.email || '—'}</td>
                      <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>{v.phone || '—'}</td>
                      <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{v.tax_id}</td>
                      <td style={{ padding: '12px 16px' }}>
                        {v.credit_balance && v.credit_balance > 0
                          ? <span className="font-mono text-xs" style={{ color: '#22C55E' }}>{v.credit_balance.toFixed(2)}</span>
                          : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                      <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{v.invoice_count ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        {!loading && !error && total > PAGE_SIZE && (
          <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Page {page} of {totalPages}</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn-secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)} style={{ padding: '5px 12px', fontSize: 12 }}>Previous</button>
              <button className="btn-secondary" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} style={{ padding: '5px 12px', fontSize: 12 }}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}