import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FileDown, FileUp, AlertCircle, TrendingUp, TrendingDown, Users, Building2 } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { analyticsApi } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/utils';
import { MetricCard, StatusBadge, InvoiceTypeBadge, ErrorState, PageLoader } from '../components/ui';

const PIE_COLORS = {
  draft: '#A8A89F', sent: '#3B82F6', paid: '#22C55E',
  overdue: '#EF4444', unpaid: '#6B7280', partially_paid: '#F59E0B',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [dash,    setDash]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const d = await analyticsApi.dashboard();
      setDash(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <PageLoader />;
  if (error && !dash) return <ErrorState message={error} onRetry={load} />;

  const statusBreakdown = dash?.status_breakdown
    ? Object.entries(dash.status_breakdown).map(([name, value]) => ({ name, value }))
    : [];

  const monthlyRevenue = dash?.monthly_revenue || [];
  const recent         = dash?.recent_invoices  || [];

  const netIncome    = dash?.net_income    ?? 0;
  const totalIncome  = dash?.total_income  ?? 0;
  const totalSpending = dash?.total_spending ?? 0;
  const vendorCount  = dash?.vendor_count  ?? '—';
  const clientCount  = dash?.client_count  ?? '—';
  const topClient    = dash?.top_client;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Row 1 — AP/AR outstanding + overdue */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <MetricCard
          label={t('dashboard.payablesOutstanding')}
          value={formatCurrency(dash?.total_payables_outstanding)}
          icon={FileDown}
          accentColor="#3B82F6"
        />
        <MetricCard
          label={t('dashboard.receivablesOutstanding')}
          value={formatCurrency(dash?.total_receivables_outstanding)}
          icon={FileUp}
          accentColor="#22C55E"
        />
        <MetricCard
          label={t('dashboard.overdueBoth')}
          value={dash?.overdue_count ?? '—'}
          icon={AlertCircle}
          accentColor="#EF4444"
          onClick={() => navigate('/payables')}
        />
      </div>

      {/* Row 2 — Financial KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <MetricCard
          label={t('dashboard.netIncome')}
          value={formatCurrency(netIncome)}
          icon={netIncome >= 0 ? TrendingUp : TrendingDown}
          accentColor={netIncome >= 0 ? '#22C55E' : '#EF4444'}
        />
        <MetricCard
          label={t('dashboard.totalRevenue')}
          value={formatCurrency(totalIncome)}
          icon={FileUp}
          accentColor="#22C55E"
        />
        <MetricCard
          label={t('dashboard.totalExpenses')}
          value={formatCurrency(totalSpending)}
          icon={FileDown}
          accentColor="#6B7280"
        />
      </div>

      {/* Row 3 — Vendors / Clients / Top Client */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <MetricCard
          label={t('dashboard.vendors')}
          value={vendorCount}
          icon={Building2}
          accentColor="#8B5CF6"
          onClick={() => navigate('/vendors')}
        />
        <MetricCard
          label={t('dashboard.clients')}
          value={clientCount}
          icon={Users}
          accentColor="#F59E0B"
          onClick={() => navigate('/clients')}
        />
        <div
          style={{
            padding: '16px 20px',
            background: 'var(--bg-card)',
            borderRadius: 12,
            border: '1px solid var(--border)',
            cursor: topClient ? 'default' : 'default',
          }}
        >
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            {t('dashboard.topClient')}
          </div>
          {topClient ? (
            <>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>
                {topClient.client_name}
              </div>
              <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: '#22C55E' }}>
                {formatCurrency(topClient.total_billed)}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 20, fontFamily: 'var(--font-mono)', fontWeight: 700 }}>—</div>
          )}
        </div>
      </div>

      {/* Row 4 — Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>{t('dashboard.statusBreakdown')}</div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={statusBreakdown}
                dataKey="value"
                nameKey="name"
                cx="50%" cy="50%"
                outerRadius={70}
                label={({ name, percent }) => `${name} ${Math.round(percent * 100)}%`}
                labelLine={false}
                fontSize={11}
              >
                {statusBreakdown.map((entry, i) => (
                  <Cell key={i} fill={PIE_COLORS[entry.name] || '#ccc'} />
                ))}
              </Pie>
              <Tooltip formatter={(v, n) => [v, n]} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>{t('dashboard.monthlyCashFlow')}</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={monthlyRevenue} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
              <Tooltip formatter={v => formatCurrency(v)} />
              <Bar dataKey="receivable_amount" fill="#22C55E" radius={[3,3,0,0]} name={t('dashboard.received')} />
              <Bar dataKey="payable_amount" fill="#3B82F6" radius={[3,3,0,0]} name={t('dashboard.paidLegend')} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Row 5 — Recent Activity */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600 }}>
          {t('dashboard.recentActivity')}
        </div>
        {recent.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            {t('dashboard.noRecentInvoices')}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {[t('common.table.type'), t('common.table.invoiceNumber'), t('common.table.entity'), t('common.table.amount'), t('common.table.status'), t('common.table.date')].map(h => (
                  <th key={h} style={{
                    padding: '9px 16px', textAlign: 'left', fontSize: 11,
                    fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: '0.06em', color: 'var(--text-muted)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.map(inv => (
                <tr
                  key={inv.id}
                  className="table-row-hover"
                  onClick={() => navigate(`/${inv.invoice_type === 'receivable' ? 'receivables' : 'payables'}/${inv.id}`)}
                  style={{ cursor: 'pointer', borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <td style={{ padding: '10px 16px' }}>
                    <InvoiceTypeBadge type={inv.invoice_type} />
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                    {inv.invoice_number}
                  </td>
                  <td style={{ padding: '10px 16px', fontSize: 13 }}>
                    {inv.entity_name || inv.vendor_name || inv.client_name || '—'}
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                    {formatCurrency(inv.grand_total)}
                  </td>
                  <td style={{ padding: '10px 16px' }}>
                    <StatusBadge status={inv.status} />
                  </td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-muted)' }}>
                    {formatDate(inv.issue_date)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}