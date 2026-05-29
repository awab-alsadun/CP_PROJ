import { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie, Legend
} from 'recharts'
import { analyticsApi } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { PageLoader, SectionHeader } from '../components/ui'

const ChartCard = ({ title, subtitle, children, height = 220 }) => (
  <div className="card p-5">
    <div className="mb-4">
      <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h3>
      {subtitle && <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
    <ResponsiveContainer width="100%" height={height}>
      {children}
    </ResponsiveContainer>
  </div>
)

const tooltipStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  fontSize: 12,
  fontFamily: 'DM Sans',
  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
}

const axisTickStyle = { fontSize: 11, fill: 'var(--text-muted)', fontFamily: 'DM Sans' }

export default function Analytics() {
  const [typeFilter, setTypeFilter] = useState('all')
  const [spending,   setSpending]   = useState(null)
  const [trends,     setTrends]     = useState(null)
  const [timing,     setTiming]     = useState(null)
  const [overdue,    setOverdue]    = useState(null)
  const [loading,    setLoading]    = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [s, t, pt, o] = await Promise.allSettled([
        analyticsApi.spending(),
        analyticsApi.trends(),
        analyticsApi.paymentTiming(),
        analyticsApi.overdue(),
      ])
      if (s.status  === 'fulfilled') setSpending(s.value)
      if (t.status  === 'fulfilled') setTrends(t.value)
      if (pt.status === 'fulfilled') setTiming(pt.value)
      if (o.status  === 'fulfilled') setOverdue(o.value)
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className="p-6"><PageLoader /></div>

  const vendorData  = spending?.vendors || []
  const clientData  = spending?.clients || []
  const trendsData  = trends?.months    || []
  const timingData  = timing?.distribution || []
  const overdueData = overdue?.aging_buckets || []

  const TIMING_COLORS = ['#22C55E', '#86EFAC', '#FDE68A', '#FCA5A5', '#EF4444']

  return (
    <div className="p-6 space-y-4 animate-fade-up">

      {/* Type filter */}
      <div className="flex items-center justify-between">
        <div />
        <div className="flex gap-1 p-1 rounded-xl border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          {[['all', 'All'], ['payable', 'Payables (AP)'], ['receivable', 'Receivables (AR)']].map(([v, l]) => (
            <button key={v} onClick={() => setTypeFilter(v)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150"
              style={typeFilter === v
                ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }
                : { color: 'var(--text-muted)' }
              }>
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {(typeFilter === 'all' || typeFilter === 'payable') && (
          <ChartCard title="Spending by Vendor" subtitle="Top vendors by invoice amount (AP)">
            {vendorData.length === 0
              ? <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>No vendor data</div>
              : <BarChart data={vendorData} layout="vertical" barSize={18}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={axisTickStyle}
                    tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                  <YAxis type="category" dataKey="vendor_name" axisLine={false} tickLine={false}
                    tick={axisTickStyle} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), 'Amount']} />
                  <Bar dataKey="total_spent" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                </BarChart>
            }
          </ChartCard>
        )}

        {(typeFilter === 'all' || typeFilter === 'receivable') && (
          <ChartCard title="Revenue by Client" subtitle="Top clients by billed amount (AR)">
            {clientData.length === 0
              ? <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>No client data</div>
              : <BarChart data={clientData} layout="vertical" barSize={18}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={axisTickStyle}
                    tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                  <YAxis type="category" dataKey="client_name" axisLine={false} tickLine={false}
                    tick={axisTickStyle} width={80} />
                  <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), 'Amount']} />
                  <Bar dataKey="total_revenue" fill="#22C55E" radius={[0, 4, 4, 0]} />
                </BarChart>
            }
          </ChartCard>
        )}
      </div>

      {/* Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Monthly Invoice Volume" subtitle="Invoice count and amount over time">
          {trendsData.length === 0
            ? <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>No trend data</div>
            : <LineChart data={trendsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="month" axisLine={false} tickLine={false} tick={axisTickStyle} />
                <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={axisTickStyle}
                  tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={axisTickStyle} />
                <Tooltip contentStyle={tooltipStyle}
                  formatter={(v, name) => [name === 'total_amount' ? formatCurrency(v) : v, name === 'total_amount' ? 'Amount' : 'Count']} />
                <Line yAxisId="left" type="monotone" dataKey="total_amount" stroke="var(--accent)"
                  strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} />
                <Line yAxisId="right" type="monotone" dataKey="invoice_count" stroke="#3B82F6"
                  strokeWidth={2} dot={{ r: 3, fill: '#3B82F6' }} strokeDasharray="4 4" />
              </LineChart>
          }
        </ChartCard>

        <ChartCard title="Payment Timing Distribution" subtitle="Days from issue to payment">
          {timingData.length === 0
            ? <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>No timing data</div>
            : <BarChart data={timingData} barSize={32}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="range" axisLine={false} tickLine={false} tick={axisTickStyle} />
                <YAxis axisLine={false} tickLine={false} tick={axisTickStyle} />
                <Tooltip contentStyle={tooltipStyle} formatter={v => [v, 'Invoices']} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {timingData.map((_, i) => (
                    <Cell key={i} fill={TIMING_COLORS[Math.min(i, TIMING_COLORS.length - 1)]} />
                  ))}
                </Bar>
              </BarChart>
          }
        </ChartCard>
      </div>

      {/* Row 3 — Overdue aging */}
      <div className="grid grid-cols-1 gap-4">
        <ChartCard title="Overdue Aging" subtitle="Outstanding amounts by days past due">
          {overdueData.length === 0
            ? <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>No overdue data</div>
            : <BarChart data={overdueData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="range" axisLine={false} tickLine={false} tick={axisTickStyle} />
                <YAxis axisLine={false} tickLine={false} tick={axisTickStyle}
                  tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), 'Amount']} />
                <Bar dataKey="amount" fill="#EF4444" radius={[4, 4, 0, 0]} />
              </BarChart>
          }
        </ChartCard>
      </div>
    </div>
  )
}
