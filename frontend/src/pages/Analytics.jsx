import { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie, Legend
} from 'recharts'
import { analyticsApi } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { PageLoader } from '../components/ui'

// Mock data until analytics endpoints are built (Phase 4)
const MOCK_SPENDING = [
  { vendor: 'Acme Corp', amount: 42000 }, { vendor: 'TechSupply', amount: 31500 },
  { vendor: 'GlobalShip', amount: 28900 }, { vendor: 'Medicore', amount: 19400 },
  { vendor: 'BuildRight', amount: 15200 },
]
const MOCK_TRENDS = [
  { month: 'Jun', invoices: 8, amount: 42000 }, { month: 'Jul', invoices: 12, amount: 58000 },
  { month: 'Aug', invoices: 10, amount: 51000 }, { month: 'Sep', invoices: 15, amount: 67000 },
  { month: 'Oct', invoices: 18, amount: 74000 }, { month: 'Nov', invoices: 22, amount: 89000 },
]
const MOCK_TIMING = [
  { range: '0-7 days', count: 18 }, { range: '8-14 days', count: 12 },
  { range: '15-30 days', count: 9 }, { range: '31-60 days', count: 6 },
  { range: '60+ days', count: 5 },
]
const MOCK_OVERDUE = [
  { month: 'Jun', rate: 8 }, { month: 'Jul', rate: 12 }, { month: 'Aug', rate: 9 },
  { month: 'Sep', rate: 15 }, { month: 'Oct', rate: 11 }, { month: 'Nov', rate: 7 },
]

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
  const [data, setData] = useState({
    spending: MOCK_SPENDING,
    trends: MOCK_TRENDS,
    timing: MOCK_TIMING,
    overdue: MOCK_OVERDUE,
  })
  const [loading] = useState(false)

  // When analytics endpoints are built, fetch real data:
  // useEffect(() => { analyticsApi.spending().then(...) }, [])

  if (loading) return <div className="p-6"><PageLoader /></div>

  return (
    <div className="p-6 space-y-4 animate-fade-up">
      <div>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          Charts are displaying mock data — analytics endpoints will be wired in Phase 4.
        </p>
      </div>

      {/* Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Spending by Vendor" subtitle="Top 5 vendors by invoice amount">
          <BarChart data={data.spending} layout="vertical" barSize={18}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
            <XAxis type="number" axisLine={false} tickLine={false} tick={axisTickStyle}
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
            <YAxis type="category" dataKey="vendor" axisLine={false} tickLine={false}
              tick={axisTickStyle} width={80} />
            <Tooltip contentStyle={tooltipStyle}
              formatter={v => [formatCurrency(v), 'Amount']} />
            <Bar dataKey="amount" fill="var(--accent)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>

        <ChartCard title="Monthly Invoice Volume" subtitle="Invoice count vs amount over time">
          <LineChart data={data.trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={axisTickStyle} />
            <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={axisTickStyle}
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
            <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={axisTickStyle} />
            <Tooltip contentStyle={tooltipStyle}
              formatter={(v, name) => [name === 'amount' ? formatCurrency(v) : v, name === 'amount' ? 'Revenue' : 'Count']} />
            <Line yAxisId="left" type="monotone" dataKey="amount" stroke="var(--accent)"
              strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} />
            <Line yAxisId="right" type="monotone" dataKey="invoices" stroke="#3B82F6"
              strokeWidth={2} dot={{ r: 3, fill: '#3B82F6' }} strokeDasharray="4 4" />
          </LineChart>
        </ChartCard>
      </div>

      {/* Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Payment Timing Distribution" subtitle="Days from issue to payment">
          <BarChart data={data.timing} barSize={32}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="range" axisLine={false} tickLine={false} tick={axisTickStyle} />
            <YAxis axisLine={false} tickLine={false} tick={axisTickStyle} />
            <Tooltip contentStyle={tooltipStyle} formatter={v => [v, 'Invoices']} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {data.timing.map((entry, i) => (
                <Cell key={i} fill={i < 2 ? '#22C55E' : i < 3 ? '#F59E0B' : '#EF4444'} />
              ))}
            </Bar>
          </BarChart>
        </ChartCard>

        <ChartCard title="Overdue Rate Over Time" subtitle="% of invoices past due date by month">
          <LineChart data={data.overdue}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={axisTickStyle} />
            <YAxis axisLine={false} tickLine={false} tick={axisTickStyle} tickFormatter={v => `${v}%`} />
            <Tooltip contentStyle={tooltipStyle} formatter={v => [`${v}%`, 'Overdue Rate']} />
            <Line type="monotone" dataKey="rate" stroke="#EF4444" strokeWidth={2}
              dot={{ r: 3, fill: '#EF4444' }} />
          </LineChart>
        </ChartCard>
      </div>
    </div>
  )
}