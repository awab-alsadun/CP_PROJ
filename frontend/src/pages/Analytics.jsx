import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, Legend
} from 'recharts'
import { analyticsApi } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { PageLoader } from '../components/ui'

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

const Empty = ({ text }) => (
  <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
    {text}
  </div>
)

const tooltipStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  fontSize: 12,
  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
}

const axisTickStyle = { fontSize: 11, fill: 'var(--text-muted)' }
const TIMING_COLORS = ['#22C55E', '#86EFAC', '#FDE68A', '#FCA5A5', '#EF4444']

export default function Analytics() {
  const { t } = useTranslation()
  const [spending, setSpending] = useState(null)
  const [revenue,  setRevenue]  = useState(null)
  const [trends,   setTrends]   = useState(null)
  const [timing,   setTiming]   = useState(null)
  const [overdue,  setOverdue]  = useState(null)
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [s, r, t, pt, o] = await Promise.allSettled([
        analyticsApi.spending(),
        analyticsApi.revenue(),
        analyticsApi.trends(),
        analyticsApi.paymentTiming(),
        analyticsApi.overdue(),
      ])
      if (s.status  === 'fulfilled') setSpending(s.value)
      if (r.status  === 'fulfilled') setRevenue(r.value)
      if (t.status  === 'fulfilled') setTrends(t.value)
      if (pt.status === 'fulfilled') setTiming(pt.value)
      if (o.status  === 'fulfilled') setOverdue(o.value)
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className="p-6"><PageLoader /></div>

  const vendorData  = spending?.vendors      || []
  const clientData  = revenue?.clients       || []
  const timingData  = timing?.distribution   || []
  const overdueData = overdue?.aging_buckets || []

  // Merge payables + receivables into one month series
  const monthMap = {}
  ;(trends?.payables || []).forEach(m => {
    if (!monthMap[m.month]) monthMap[m.month] = { month: m.month, payable_amount: 0, receivable_amount: 0 }
    monthMap[m.month].payable_amount = m.total_amount
  })
  ;(trends?.receivables || []).forEach(m => {
    if (!monthMap[m.month]) monthMap[m.month] = { month: m.month, payable_amount: 0, receivable_amount: 0 }
    monthMap[m.month].receivable_amount = m.total_amount
  })
  const mergedTrends = Object.values(monthMap).sort((a, b) => a.month.localeCompare(b.month))

  return (
    <div className="p-6 space-y-4 animate-fade-up">

      {/* Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title={t('analyticsPage.spendingByVendor')} subtitle={t('analyticsPage.spendingByVendorSub')}>
          {vendorData.length === 0 ? <Empty text={t('analyticsPage.noData')} /> :
            <BarChart data={vendorData} layout="vertical" barSize={18}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
              <XAxis type="number" axisLine={false} tickLine={false} tick={axisTickStyle}
                tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
              <YAxis type="category" dataKey="vendor_name" axisLine={false} tickLine={false}
                tick={axisTickStyle} width={90} />
              <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), t('analyticsPage.amountTooltip')]} />
              <Bar dataKey="total_spent" fill="var(--accent)" radius={[0, 4, 4, 0]} />
            </BarChart>
          }
        </ChartCard>

        <ChartCard title={t('analyticsPage.revenueByClient')} subtitle={t('analyticsPage.revenueByClientSub')}>
          {clientData.length === 0 ? <Empty text={t('analyticsPage.noData')} /> :
            <BarChart data={clientData} layout="vertical" barSize={18}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
              <XAxis type="number" axisLine={false} tickLine={false} tick={axisTickStyle}
                tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
              <YAxis type="category" dataKey="client_name" axisLine={false} tickLine={false}
                tick={axisTickStyle} width={90} />
              <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), t('analyticsPage.amountTooltip')]} />
              <Bar dataKey="total_invoiced" fill="#22C55E" radius={[0, 4, 4, 0]} />
            </BarChart>
          }
        </ChartCard>
      </div>

      {/* Row 2 — Monthly volume: payables vs receivables on one chart */}
      <ChartCard title={t('analyticsPage.monthlyVolume')} subtitle={t('analyticsPage.monthlyVolumeSub')} height={240}>
        {mergedTrends.length === 0 ? <Empty text={t('analyticsPage.noData')} /> :
          <LineChart data={mergedTrends}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={axisTickStyle} />
            <YAxis axisLine={false} tickLine={false} tick={axisTickStyle}
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip contentStyle={tooltipStyle}
              formatter={(v, name) => [
                formatCurrency(v),
                name === 'payable_amount' ? t('analyticsPage.payablesLegend') : t('analyticsPage.receivablesLegend'),
              ]} />
            <Legend
              formatter={name => name === 'payable_amount' ? t('analyticsPage.payablesAP') : t('analyticsPage.receivablesAR')}
              wrapperStyle={{ fontSize: 11 }}
            />
            <Line type="monotone" dataKey="payable_amount" stroke="#3B82F6"
              strokeWidth={2} dot={{ r: 3, fill: '#3B82F6' }} />
            <Line type="monotone" dataKey="receivable_amount" stroke="#22C55E"
              strokeWidth={2} dot={{ r: 3, fill: '#22C55E' }} />
          </LineChart>
        }
      </ChartCard>

      {/* Row 3 — Payment timing + Overdue aging */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title={t('analyticsPage.paymentTiming')} subtitle={t('analyticsPage.paymentTimingSub')}>
          {timingData.length === 0 ? <Empty text={t('analyticsPage.noData')} /> :
            <BarChart data={timingData} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="range" axisLine={false} tickLine={false} tick={axisTickStyle} />
              <YAxis axisLine={false} tickLine={false} tick={axisTickStyle} />
              <Tooltip contentStyle={tooltipStyle} formatter={v => [v, t('analyticsPage.invoicesTooltip')]} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {timingData.map((_, i) => (
                  <Cell key={i} fill={TIMING_COLORS[Math.min(i, TIMING_COLORS.length - 1)]} />
                ))}
              </Bar>
            </BarChart>
          }
        </ChartCard>

        <ChartCard title={t('analyticsPage.overdueAging')} subtitle={t('analyticsPage.overdueAgingSub')}>
          {overdueData.length === 0 ? <Empty text={t('analyticsPage.noData')} /> :
            <BarChart data={overdueData} barSize={36}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="range" axisLine={false} tickLine={false} tick={axisTickStyle} />
              <YAxis axisLine={false} tickLine={false} tick={axisTickStyle}
                tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={v => [formatCurrency(v), t('analyticsPage.amountTooltip')]} />
              <Bar dataKey="amount" fill="#EF4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          }
        </ChartCard>
      </div>
    </div>
  )
}