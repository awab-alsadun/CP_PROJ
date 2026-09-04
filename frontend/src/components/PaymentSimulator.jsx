import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { vendorsApi, clientsApi, paymentsApi } from '../lib/api';
import { formatCurrency } from '../lib/utils';
import { StatusBadge, ConfirmDialog, toast } from './ui';

const CURRENCIES = ['USD','EUR','GBP','TRY','SAR','AED','EGP','BHD','DKK'];
const METHODS = ['bank_transfer', 'check', 'credit_card', 'cash', 'other'];

export default function PaymentSimulator() {
  const { t } = useTranslation();
  const [entityType, setEntityType] = useState('vendor');
  const [entities, setEntities] = useState([]);
  const [entityId, setEntityId] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [reference, setReference] = useState('');
  const [method, setMethod] = useState('bank_transfer');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [confirm, setConfirm] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    setEntityId(''); setResult(null);
    const fn = entityType === 'vendor' ? vendorsApi.list : clientsApi.list;
    fn({ limit: 200 }).then(r => setEntities(r.data || r || [])).catch(() => setEntities([]));
  }, [entityType]);

  const selectedEntity = entities.find(e => e.id === entityId);

  async function process() {
    setConfirm(false);
    setProcessing(true);
    setResult(null);
    try {
      const res = await paymentsApi.allocate({
        entity_id: entityId,
        entity_type: entityType,
        amount: parseFloat(amount),
        currency,
        method,
        reference,
        payment_date: date,
      });
      setResult(res);
      const count = res.allocations?.length ?? 0;
      toast(t('paymentSimulator.processedInvoicesUpdated', { count }));
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{t('paymentSimulator.title')}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 20 }}>
        {t('paymentSimulator.subtitle')}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {/* Entity type toggle */}
        <div style={{ gridColumn: '1 / -1' }}>
          <Label>{t('paymentSimulator.entityType')}</Label>
          <div style={{ display: 'flex', gap: 0, background: 'var(--bg-secondary)', borderRadius: 8, padding: 3, width: 'fit-content' }}>
            {['vendor', 'client'].map(entityTypeOption => (
              <button key={entityTypeOption} onClick={() => setEntityType(entityTypeOption)} style={{
                padding: '6px 18px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500, textTransform: 'capitalize',
                background: entityType === entityTypeOption ? 'var(--bg-card)' : 'transparent',
                color: entityType === entityTypeOption ? 'var(--text-primary)' : 'var(--text-muted)',
                transition: 'all 0.15s',
              }}>{entityTypeOption === 'vendor' ? t('paymentSimulator.vendorAP') : t('paymentSimulator.clientAR')}</button>
            ))}
          </div>
        </div>

        <div style={{ gridColumn: '1 / -1' }}>
          <Label>{t('paymentSimulator.entity')}</Label>
          <select className="input" value={entityId} onChange={e => setEntityId(e.target.value)} style={{ width: '100%' }}>
            <option value="">{t('paymentSimulator.selectEntity', { type: entityType === 'vendor' ? t('paymentSimulator.vendor') : t('paymentSimulator.client') })}</option>
            {entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </div>

        <div>
          <Label>{t('paymentSimulator.amount')}</Label>
          <input className="input" type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" style={{ width: '100%' }} />
        </div>
        <div>
          <Label>{t('paymentSimulator.currency')}</Label>
          <select className="input" value={currency} onChange={e => setCurrency(e.target.value)} style={{ width: '100%' }}>
            {CURRENCIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        <div>
          <Label>{t('paymentSimulator.method')}</Label>
          <select className="input" value={method} onChange={e => setMethod(e.target.value)} style={{ width: '100%' }}>
            {METHODS.map(m => <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div>
          <Label>{t('paymentSimulator.date')}</Label>
          <input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} style={{ width: '100%' }} />
        </div>

        <div style={{ gridColumn: '1 / -1' }}>
          <Label>{t('paymentSimulator.reference')}</Label>
          <input className="input" value={reference} onChange={e => setReference(e.target.value)} placeholder={t('paymentSimulator.referencePlaceholder')} style={{ width: '100%' }} />
        </div>
      </div>

      <button
        className="btn-primary"
        disabled={!entityId || !amount || parseFloat(amount) <= 0 || processing}
        onClick={() => setConfirm(true)}
        style={{ marginTop: 20, padding: '9px 20px' }}>
        {processing ? t('paymentSimulator.processing') : t('paymentSimulator.processPayment')}
      </button>

      {/* Result */}
      {result && (
        <div style={{ marginTop: 20, padding: '16px 18px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#22C55E', marginBottom: 12 }}>
            {t('paymentSimulator.paymentAllocated', { count: result.allocations?.length ?? 0 })}
          </div>
          {result.allocations?.map((a, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13 }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{a.invoice_number}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{formatCurrency(a.amount_applied, currency)}</span>
              <StatusBadge status={a.new_status} />
            </div>
          ))}
          {result.overpayment > 0 && (
            <div style={{ marginTop: 10, fontSize: 12, color: '#F59E0B', padding: '6px 10px', background: '#F59E0B15', borderRadius: 6 }}>
              {t('paymentSimulator.overpaymentCredited', { amount: formatCurrency(result.overpayment, currency), entity: selectedEntity?.name || t('paymentSimulator.entityFallback') })}
            </div>
          )}
          {result.total_applied != null && (
            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>
              {t('paymentSimulator.totalApplied', { applied: formatCurrency(result.total_applied, currency), total: formatCurrency(parseFloat(amount), currency) })}
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title={t('paymentSimulator.confirmPaymentTitle')}
        message={t('paymentSimulator.confirmPaymentMessage', { amount: formatCurrency(parseFloat(amount) || 0, currency), entity: selectedEntity?.name || t('paymentSimulator.selectedEntityFallback') })}
        onConfirm={process}
        onCancel={() => setConfirm(false)}
        confirmLabel={t('paymentSimulator.processPayment')}
      />
    </div>
  );
}

function Label({ children }) {
  return <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{children}</div>;
}
