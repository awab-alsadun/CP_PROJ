import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import {
  FileText, DollarSign, AlertTriangle, CheckCircle, ArrowRight,
  Layers, BookOpen, Building2, Users
} from 'lucide-react'
import { analyticsApi } from '../lib/api'
import { formatCurrency, formatDate } from '../lib/utils'
import { MetricCard, StatusBadge, PageLoader, ErrorState, SectionHeader } from '../components/ui'

const STATUS_COLORS = {
  paid: '#22C55E', sent: '#3B82F6', overdue: '#EF4444', draft: '#A8A89F'
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2 text-sm">
      <p style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
        {formatCurrency(payload[0].value)}
      </p>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [dash, setDash]       = useState(null)
  const [stats, setStats]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [dashRes, statsRes] = await Promise.allSettled([
        analyticsApi.dashboard(),
        analyticsApi.systemStats(),
      ])
      if (dashRes.status === 'fulfilled') {
        setDash(dashRes.value)
      } else {
        setError(dashRes.reason?.message || 'Failed to load dashboard')
      }
      if (statsRes.status === 'fulfilled') setStats(statsRes.value)
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className="p-6"><PageLoader /></div>
  if (error)   return <div className="p-6"><ErrorState message={error} onRetry={() => window.location.reload()} /></div>

  // Build chart data from response
  const monthlyData = (dash?.monthly_revenue || []).map(m => ({
    month: m.month?.slice(0, 7) || m.month,
    revenue: m.amount,
  }))

  const statusData = dash?.status_breakdown
    ? Object.entries(dash.status_breakdown)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: k.charAt(0).toUpperCase() + k.slice(1), value: v, color: STATUS_COLORS[k] }))
    : []

  const recentInvoices = dash?.recent_invoices || []

  return (
    <div className="p-6 space-y-6 animate-fade-up">

      {/* Primary metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Invoices"
          value={dash?.total_invoices ?? '—'}
          sub="All time"
          icon={FileText}
          accentColor="#3B82F6"
        />
        <MetricCard
          label="Outstanding"
          value={formatCurrency(dash?.total_outstanding ?? 0)}
          sub="Sent + overdue"
          icon={DollarSign}
          accentColor="#D4A847"
        />
        <MetricCard
          label="Overdue"
          value={dash?.overdue_count ?? '—'}
          sub="Needs attention"
          icon={AlertTriangle}
          accentColor="#EF4444"
        />
        <MetricCard
          label="Paid This Month"
          value={formatCurrency(dash?.paid_this_month ?? 0)}
          sub="Collected revenue"
          icon={CheckCircle}
          accentColor="#22C55E"
        />
      </div>

      {/* System stats — secondary row */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Vendors',    value: stats.total_vendors,         icon: Building2, color: '#8B5CF6' },
            { label: 'Clients',    value: stats.total_clients,         icon: Users,     color: '#06B6D4' },
            { label: 'Embeddings', value: stats.total_embeddings,      icon: Layers,    color: '#10B981' },
            { label: 'Reg. Docs',  value: stats.total_documents,       icon: BookOpen,  color: '#F59E0B' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="card px-4 py-3 flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: `${color}18` }}>
                <Icon size={15} style={{ color }} strokeWidth={1.8} />
              </div>
              <div>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
                <p className="text-base font-semibold font-mono leading-tight"
                  style={{ color: 'var(--text-primary)' }}>
                  {(value ?? 0).toLocaleString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Monthly revenue */}
        <div className="card p-5 col-span-2">
          <SectionHeader title="Monthly Revenue" />
          {monthlyData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-sm"
              style={{ color: 'var(--text-muted)' }}>No revenue data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={monthlyData} barSize={28}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="month" axisLine={false} tickLine={false}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)', fontFamily: 'DM Sans' }} />
                <YAxis axisLine={false} tickLine={false}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)', fontFamily: 'DM Sans' }}
                  tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--bg-secondary)', radius: 4 }} />
                <Bar dataKey="revenue" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Status breakdown */}
        <div className="card p-5">
          <SectionHeader title="Invoice Status" />
          {statusData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-sm"
              style={{ color: 'var(--text-muted)' }}>No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={statusData} cx="50%" cy="50%"
                  innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                  {statusData.map(entry => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Legend formatter={v => (
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'DM Sans' }}>{v}</span>
                )} />
                <Tooltip contentStyle={{
                  background: 'var(--bg-card)', border: '1px solid var(--border)',
                  borderRadius: 12, fontSize: 12,
                }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Recent invoices */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Recent Invoices
          </h2>
          <Link to="/invoices" className="flex items-center gap-1 text-xs font-medium"
            style={{ color: 'var(--accent)' }}>
            View all <ArrowRight size={12} />
          </Link>
        </div>

        {recentInvoices.length === 0 ? (
          <div className="py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            No invoices yet
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Invoice #', 'Vendor', 'Client', 'Date', 'Amount', 'Status'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
                      style={{ color: 'var(--text-muted)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentInvoices.map(inv => (
                  <tr key={inv.id}
                    className="table-row-hover transition-colors cursor-pointer"
                    style={{ borderBottom: '1px solid var(--border-subtle)' }}
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                  >
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                        {inv.invoice_number || '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {inv.vendor_name || '—'}
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {inv.client_name || '—'}
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-muted)' }}>
                      {formatDate(inv.issue_date)}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {formatCurrency(inv.grand_total)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={inv.status} />
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