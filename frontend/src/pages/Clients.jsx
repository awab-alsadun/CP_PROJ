import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Users } from 'lucide-react'
import { clientsApi } from '../lib/api'
import { formatCurrency, truncate } from '../lib/utils'
import { PageLoader, ErrorState, EmptyState } from '../components/ui'

export default function Clients() {
  const navigate = useNavigate()
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    clientsApi.list()
      .then(res => {
        const list = Array.isArray(res) ? res : (res?.clients || res?.data || [])
        setClients(list)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = clients.filter(c =>
    !search || c.name?.toLowerCase().includes(search.toLowerCase()) || c.tax_id?.includes(search)
  )

  return (
    <div className="p-6 space-y-4 animate-fade-up">
      <div className="flex items-center justify-between">
        <div className="relative w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input className="input pl-9 h-9 text-sm" placeholder="Search clients…"
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
          {filtered.length} client{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="card overflow-hidden">
        {loading ? <PageLoader />
          : error ? <ErrorState message={error} onRetry={() => window.location.reload()} />
          : filtered.length === 0 ? (
            <EmptyState icon={Users} title="No clients found" description="Clients are created when invoices are ingested or created manually." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Client', 'Tax ID', 'Email', 'Phone', 'Total Billed', 'Invoices'].map(h => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
                        style={{ color: 'var(--text-muted)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(c => (
                    <tr key={c.id}
                      className="table-row-hover cursor-pointer transition-colors"
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      onClick={() => navigate(`/clients/${c.id}`)}
                    >
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-semibold flex-shrink-0"
                            style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>
                            {c.name?.[0]?.toUpperCase() || 'C'}
                          </div>
                          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                            {truncate(c.name, 30)}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{c.tax_id || '—'}</span>
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>{c.email || '—'}</td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>{c.phone || '—'}</td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                          {c.total_billed != null ? formatCurrency(c.total_billed) : '—'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        {c.invoice_count ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>
    </div>
  )
}