import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { FileText, DollarSign, AlertTriangle, CheckCircle, ArrowRight } from 'lucide-react'
import { analyticsApi, invoicesApi } from '../lib/api'
import { formatCurrency, formatDate, statusConfig } from '../lib/utils'
import { MetricCard, StatusBadge, PageLoader, ErrorState, SectionHeader } from '../components/ui'
import Topbar from '../components/layout/Topbar'

// Fallback mock data until analytics endpoints are built
const MOCK_MONTHLY = [
  { month: 'Jun', revenue: 42000 }, { month: 'Jul', revenue: 58000 },
  { month: 'Aug', revenue: 51000 }, { month: 'Sep', revenue: 67000 },
  { month: 'Oct', revenue: 74000 }, { month: 'Nov', revenue: 89000 },
]

const MOCK_STATUS = [
  { name: 'Paid', value: 28, color: '#22C55E' },
  { name: 'Sent', value: 12, color: '#3B82F6' },
  { name: 'Overdue', value: 6, color: '#EF4444' },
  { name: 'Draft', value: 4, color: '#A8A89F' },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="card px-3 py-2 text-sm">
        <p style={{ color: 'var(--text-secondary)' }}>{label}</p>
        <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          {formatCurrency(payload[0].value)}
        </p>
      </div>
    )
  }
  return null
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null)
  const [recentInvoices, setRecentInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        // Try analytics endpoint first; fall back to raw invoice list
        const [invoicesRes] = await Promise.allSettled([
          invoicesApi.list({ limit: 10, page: 1 }),
        ])
        if (invoicesRes.status === 'fulfilled') {
          const data = invoicesRes.value
          const list = Array.isArray(data) ? data : (data?.invoices || data?.data || [])
          setRecentInvoices(list.slice(0, 10))

          // Derive metrics from list if analytics endpoint not ready
          const total = list.length
          const outstanding = list.filter(i => i.status === 'sent' || i.status === 'overdue')
            .reduce((s, i) => s + (i.grand_total || 0), 0)
          const overdue = list.filter(i => i.status === 'overdue').length
          const paid = list.filter(i => i.status === 'paid')
            .reduce((s, i) => s + (i.grand_total || 0), 0)

          setMetrics({ total, outstanding, overdue, paid })
        }
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return (
    <div className="p-6"><Topbar title="Dashboard" subtitle="Overview of your financial activity" /><PageLoader /></div>
  )
  if (error) return (
    <div className="p-6"><ErrorState message={error} onRetry={() => window.location.reload()} /></div>
  )

  return (
    <div className="p-6 space-y-6 animate-fade-up">
      <Topbar title="Dashboard" subtitle="Overview of your financial activity" />

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Invoices"
          value={metrics?.total ?? '—'}
          sub="All time"
          icon={FileText}
          accentColor="#3B82F6"
        />
        <MetricCard
          label="Outstanding"
          value={formatCurrency(metrics?.outstanding ?? 0)}
          sub="Sent + overdue"
          icon={DollarSign}
          accentColor="#D4A847"
        />
        <MetricCard
          label="Overdue"
          value={metrics?.overdue ?? '—'}
          sub="Needs attention"
          icon={AlertTriangle}
          accentColor="#EF4444"
        />
        <MetricCard
          label="Paid This Month"
          value={formatCurrency(metrics?.paid ?? 0)}
          sub="Collected revenue"
          icon={CheckCircle}
          accentColor="#22C55E"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Monthly revenue bar chart */}
        <div className="card p-5 col-span-2">
          <SectionHeader title="Monthly Revenue" />
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={MOCK_MONTHLY} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false} tickLine={false}
                tick={{ fontSize: 12, fill: 'var(--text-muted)', fontFamily: 'DM Sans' }}
              />
              <YAxis
                axisLine={false} tickLine={false}
                tick={{ fontSize: 11, fill: 'var(--text-muted)', fontFamily: 'DM Sans' }}
                tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--bg-secondary)', radius: 4 }} />
              <Bar dataKey="revenue" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Status breakdown */}
        <div className="card p-5">
          <SectionHeader title="Invoice Status" />
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={MOCK_STATUS}
                cx="50%" cy="50%"
                innerRadius={55} outerRadius={80}
                paddingAngle={3}
                dataKey="value"
              >
                {MOCK_STATUS.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Legend
                formatter={(value) => (
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'DM Sans' }}>
                    {value}
                  </span>
                )}
              />
              <Tooltip
                formatter={(value, name) => [value, name]}
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 12,
                  fontSize: 12,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent invoices table */}
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
                      style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentInvoices.map((inv) => (
                  <tr key={inv.id}
                    className="table-row-hover transition-colors cursor-pointer"
                    style={{ borderBottom: '1px solid var(--border-subtle)' }}
                    onClick={() => window.location.href = `/invoices/${inv.id}`}
                  >
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-xs font-medium"
                        style={{ color: 'var(--text-primary)' }}>
                        {inv.invoice_number || '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {inv.vendor?.name || inv.vendor_id || '—'}
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {inv.client?.name || inv.client_id || '—'}
                    </td>
                    <td className="px-5 py-3.5 text-sm" style={{ color: 'var(--text-muted)' }}>
                      {formatDate(inv.issue_date)}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-sm font-medium"
                        style={{ color: 'var(--text-primary)' }}>
                        {formatCurrency(inv.grand_total, inv.currency)}
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