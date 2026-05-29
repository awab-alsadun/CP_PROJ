import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileDown, FileUp, Plus, Trash2 } from 'lucide-react';
import { invoicesApi, vendorsApi, clientsApi, settingsApi, uploadApi } from '../lib/api';
import { formatCurrency } from '../lib/utils';
import { toast, PageLoader } from '../components/ui';

const CURRENCIES = ['USD','EUR','GBP','TRY','SAR','AED','EGP','BHD','DKK','FIN'];
const EMPTY_ITEM = { description: '', quantity: 1, unit_price: 0, discount: 0 };

export default function CreateInvoice() {
  const navigate = useNavigate();
  const [type, setType] = useState(null); // 'payable' | 'receivable'
  const [vendors, setVendors] = useState([]);
  const [clients, setClients] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);

  // Form state
  const [entityId, setEntityId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [issueDate, setIssueDate] = useState(new Date().toISOString().slice(0,10));
  const [dueDate, setDueDate] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [taxRate, setTaxRate] = useState(0);
  const [description, setDescription] = useState('');
  const [lineItems, setLineItems] = useState([{ ...EMPTY_ITEM }]);
  const [file, setFile] = useState(null);

  useEffect(() => {
    vendorsApi.list({ limit: 200 }).then(r => setVendors(r.data || r || [])).catch(() => {});
    clientsApi.list({ limit: 200 }).then(r => setClients(r.data || r || [])).catch(() => {});
    settingsApi.get().then(s => { setSettings(s); setTaxRate(s?.default_tax_rate || 0); }).catch(() => {});
  }, []);

  // Calculations
  const subtotal = lineItems.reduce((s, i) => s + ((i.quantity * i.unit_price) - (i.discount || 0)), 0);
  const totalTax = subtotal * (taxRate / 100);
  const grandTotal = subtotal + totalTax;

  function updateItem(idx, field, value) {
    setLineItems(prev => prev.map((item, i) => i === idx ? { ...item, [field]: field === 'description' ? value : parseFloat(value) || 0 } : item));
  }

  function addItem() { setLineItems(prev => [...prev, { ...EMPTY_ITEM }]); }
  function removeItem(idx) { setLineItems(prev => prev.filter((_, i) => i !== idx)); }

  async function handleSubmit(sendNow = false) {
    if (!entityId) { toast('Select a ' + (type === 'payable' ? 'vendor' : 'client'), 'error'); return; }
    if (!invoiceNumber) { toast('Enter an invoice number', 'error'); return; }
    setLoading(true);
    try {
      const body = {
        invoice_type: type,
        invoice_number: invoiceNumber,
        issue_date: issueDate,
        due_date: dueDate || null,
        currency,
        tax_percent: taxRate,
        subtotal,
        total_tax: totalTax,
        grand_total: grandTotal,
        description: description || null,
        status: type === 'payable' ? 'unpaid' : (sendNow ? 'draft' : 'draft'),
        ...(type === 'payable' ? { vendor_id: entityId } : { client_id: entityId }),
      };
      const inv = await invoicesApi.create(body);
      // Create line items
      for (const li of lineItems) {
        if (li.description) {
          await fetch(`/api/v1/invoices/${inv.id}/line-items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...li, invoice_id: inv.id, line_subtotal: (li.quantity * li.unit_price) - li.discount, company_id: inv.company_id }),
          }).catch(() => {});
        }
      }
      // Upload file if payable
      if (type === 'payable' && file) {
        await uploadApi.upload(file).catch(() => {});
      }
      // Send if receivable + sendNow
      if (type === 'receivable' && sendNow) {
        await invoicesApi.transition(inv.id, 'sent').catch(() => {});
      }
      toast(`Invoice ${inv.invoice_number} created`);
      navigate(`/${type === 'payable' ? 'payables' : 'receivables'}/${inv.id}`);
    } catch (e) { toast(e.message, 'error'); }
    finally { setLoading(false); }
  }

  if (!type) {
    return (
      <div style={{ maxWidth: 600, margin: '60px auto', textAlign: 'center' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Create Invoice</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 32, fontSize: 14 }}>Choose the invoice type to begin</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <TypeCard
            icon={FileDown} label="Record a Payable"
            sub="An invoice you received from a vendor"
            color="#3B82F6"
            onClick={() => setType('payable')}
          />
          <TypeCard
            icon={FileUp} label="Create a Receivable"
            sub="An invoice you're sending to a client"
            color="#22C55E"
            onClick={() => setType('receivable')}
          />
        </div>
      </div>
    );
  }

  const entityList = type === 'payable' ? vendors : clients;
  const entityLabel = type === 'payable' ? 'Vendor' : 'Client';

  return (
    <div style={{ maxWidth: 780, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button className="btn-ghost" onClick={() => setType(null)} style={{ fontSize: 13, padding: '6px 12px' }}>← Back</button>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>
          {type === 'payable' ? 'Record Payable' : 'Create Receivable'}
        </h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div className="card" style={{ padding: 20 }}>
          <FormField label={entityLabel}>
            <select className="input" value={entityId} onChange={e => setEntityId(e.target.value)} style={{ width: '100%' }}>
              <option value="">Select {entityLabel}…</option>
              {entityList.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </FormField>
          <FormField label="Invoice Number">
            <input className="input" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} placeholder="INV-001" style={{ width: '100%' }} />
          </FormField>
          <FormField label="Currency">
            <select className="input" value={currency} onChange={e => setCurrency(e.target.value)} style={{ width: '100%' }}>
              {CURRENCIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </FormField>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <FormField label="Issue Date">
            <input className="input" type="date" value={issueDate} onChange={e => setIssueDate(e.target.value)} style={{ width: '100%' }} />
          </FormField>
          <FormField label="Due Date">
            <input className="input" type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} style={{ width: '100%' }} />
          </FormField>
          <FormField label={`Tax Rate (%)`}>
            <input className="input" type="number" value={taxRate} onChange={e => setTaxRate(parseFloat(e.target.value) || 0)} style={{ width: '100%' }} />
          </FormField>
        </div>
      </div>

      {/* Line Items */}
      <div className="card" style={{ marginBottom: 16, padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>Line Items</span>
          <button className="btn-secondary" onClick={addItem} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', fontSize: 12 }}>
            <Plus size={12} /> Add Row
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Description', 'Qty', 'Unit Price', 'Discount', 'Total', ''].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lineItems.map((li, idx) => {
                const lineTotal = (li.quantity * li.unit_price) - li.discount;
                return (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 12px', minWidth: 200 }}>
                      <input className="input" value={li.description} onChange={e => updateItem(idx, 'description', e.target.value)} placeholder="Item description" style={{ width: '100%', fontSize: 12 }} />
                    </td>
                    <td style={{ padding: '8px 12px', width: 70 }}>
                      <input className="input" type="number" value={li.quantity} onChange={e => updateItem(idx, 'quantity', e.target.value)} style={{ width: '100%', fontSize: 12 }} />
                    </td>
                    <td style={{ padding: '8px 12px', width: 110 }}>
                      <input className="input" type="number" value={li.unit_price} onChange={e => updateItem(idx, 'unit_price', e.target.value)} style={{ width: '100%', fontSize: 12 }} />
                    </td>
                    <td style={{ padding: '8px 12px', width: 90 }}>
                      <input className="input" type="number" value={li.discount} onChange={e => updateItem(idx, 'discount', e.target.value)} style={{ width: '100%', fontSize: 12 }} />
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>{formatCurrency(lineTotal, currency)}</td>
                    <td style={{ padding: '8px 12px' }}>
                      {lineItems.length > 1 && <button className="btn-ghost" onClick={() => removeItem(idx)} style={{ padding: 4 }}><Trash2 size={13} color="#EF4444" /></button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ minWidth: 220, display: 'flex', flexDirection: 'column', gap: 5, fontSize: 13 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Subtotal</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{formatCurrency(subtotal, currency)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Tax ({taxRate}%)</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{formatCurrency(totalTax, currency)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, fontSize: 15, borderTop: '1px solid var(--border)', paddingTop: 6, marginTop: 2 }}>
              <span>Total</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{formatCurrency(grandTotal, currency)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Notes + file upload */}
      <div style={{ display: 'grid', gridTemplateColumns: type === 'payable' ? '1fr 1fr' : '1fr', gap: 16, marginBottom: 24 }}>
        <div className="card" style={{ padding: 20 }}>
          <FormField label="Description / Notes">
            <textarea className="input" value={description} onChange={e => setDescription(e.target.value)} rows={3} style={{ width: '100%', resize: 'vertical' }} />
          </FormField>
        </div>
        {type === 'payable' && (
          <div className="card" style={{ padding: 20 }}>
            <FormField label="Attach Invoice (PDF / Image)">
              <div
                onClick={() => document.getElementById('fi').click()}
                style={{ border: '1.5px dashed var(--border)', borderRadius: 8, padding: '20px', textAlign: 'center', cursor: 'pointer', fontSize: 13, color: file ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                {file ? file.name : 'Click to attach file'}
              </div>
              <input id="fi" type="file" accept=".pdf,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={e => setFile(e.target.files[0])} />
            </FormField>
          </div>
        )}
      </div>

      {/* Submit */}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button className="btn-secondary" onClick={() => navigate(-1)} style={{ padding: '10px 20px' }}>Cancel</button>
        {type === 'receivable' && (
          <button className="btn-secondary" onClick={() => handleSubmit(false)} disabled={loading} style={{ padding: '10px 20px' }}>
            Save as Draft
          </button>
        )}
        <button className="btn-primary" onClick={() => handleSubmit(type === 'receivable')} disabled={loading} style={{ padding: '10px 24px' }}>
          {loading ? 'Creating…' : type === 'payable' ? 'Record Payable' : 'Save & Send'}
        </button>
      </div>
    </div>
  );
}

function TypeCard({ icon: Icon, label, sub, color, onClick }) {
  return (
    <div className="card" onClick={onClick} style={{ cursor: 'pointer', padding: '28px 24px', textAlign: 'center', transition: 'transform 0.15s, box-shadow 0.15s' }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.1)'; }}
      onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}>
      <div style={{ width: 48, height: 48, borderRadius: 12, background: color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px' }}>
        <Icon size={22} color={color} />
      </div>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{sub}</div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      {children}
    </div>
  );
}
