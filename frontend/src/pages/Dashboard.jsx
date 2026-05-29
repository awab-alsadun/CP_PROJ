import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileDown, FileUp, AlertCircle, ShieldAlert } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { analyticsApi, complianceApi } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/utils';
import { MetricCard, StatusBadge, InvoiceTypeBadge, ErrorState, PageLoader } from '../components/ui';

const PIE_COLORS = { draft: '#A8A89F', sent: '#3B82F6', paid: '#22C55E', overdue: '#EF4444', unpaid: '#6B7280', partially_paid: '#F59E0B' };

export default function Dashboard() {
  const navigate = useNavigate();
  const [dash, setDash] = useState(null);
  const [stats, setStats] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const [d, s, c] = await Promise.allSettled([
        analyticsApi.dashboard(),
        analyticsApi.systemStats(),
        complianceApi.summary(),
      ]);
      if (d.status === 'fulfilled') setDash(d.value);
      if (s.status === 'fulfilled') setStats(s.value);
      if (c.status === 'fulfilled') setCompliance(c.value);
      if (d.status === 'rejected') setError(d.reason.message);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <PageLoader />;
  if (error && !dash) return <ErrorState message={error} onRetry={load} />;

  const statusBreakdown = dash?.status_breakdown ? Object.entries(dash.status_breakdown).map(([name, value]) => ({ name, value })) : [];
  const monthlyRevenue = dash?.monthly_revenue || [];
  const recent = dash?.recent_invoices || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Row 1 — Key Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <MetricCard label="Payables Outstanding" value={formatCurrency(dash?.total_payables_outstanding)} icon={FileDown} color="#3B82F6" />
        <MetricCard label="Receivables Outstanding" value={formatCurrency(dash?.total_receivables_outstanding)} icon={FileUp} color="#22C55E" />
        <MetricCard
          label="Overdue (Both)" icon={AlertCircle} color="#EF4444"
          value={dash?.overdue_count ?? (dash?.ap_overdue_count ?? 0) + (dash?.ar_overdue_count ?? 0)}
          sub={dash?.ap_overdue_count != null ? `AP: ${dash.ap_overdue_count} · AR: ${dash.ar_overdue_count}` : undefined}
          onClick={() => navigate('/payables')}
        />
        <MetricCard label="Compliance Issues" value={compliance?.high_severity_count ?? '—'} icon={ShieldAlert} color="#F97316" />
      </div>

      {/* Row 2 — Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Status breakdown */}
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Invoice Status Breakdown</div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={statusBreakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name} ${Math.round(percent * 100)}%`} labelLine={false} fontSize={11}>
                {statusBreakdown.map((entry, i) => <Cell key={i} fill={PIE_COLORS[entry.name] || '#ccc'} />)}
              </Pie>
              <Tooltip formatter={(v, n) => [v, n]} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Monthly revenue */}
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Monthly Cash Flow</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={monthlyRevenue} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={v => formatCurrency(v)} />
              <Bar dataKey="revenue" fill="#22C55E" radius={[3,3,0,0]} name="Received" />
              <Bar dataKey="expenses" fill="#3B82F6" radius={[3,3,0,0]} name="Paid" />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Row 3 — Recent Activity */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600 }}>Recent Activity</div>
        {recent.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No recent invoices</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Type', 'Invoice #', 'Entity', 'Amount', 'Status', 'Date'].map(h => (
                  <th key={h} style={{ padding: '9px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>{h}</th>
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
                  <td style={{ padding: '10px 16px' }}><InvoiceTypeBadge type={inv.invoice_type} /></td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>{inv.invoice_number}</td>
                  <td style={{ padding: '10px 16px', fontSize: 13 }}>{inv.vendor_name || inv.client_name || '—'}</td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontSize: 13 }}>{formatCurrency(inv.grand_total, inv.currency)}</td>
                  <td style={{ padding: '10px 16px' }}><StatusBadge status={inv.status} /></td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-muted)' }}>{formatDate(inv.issue_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Row 4 — System Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { label: 'Vendors', value: stats.vendor_count ?? '—' },
            { label: 'Clients', value: stats.client_count ?? '—' },
            { label: 'Embeddings', value: stats.embedding_count ?? '—' },
            { label: 'Documents', value: stats.document_count ?? '—' },
          ].map(m => (
            <div key={m.label} style={{ padding: '14px 18px', background: 'var(--bg-secondary)', borderRadius: 10, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{m.label}</div>
              <div style={{ fontSize: 22, fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{m.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
