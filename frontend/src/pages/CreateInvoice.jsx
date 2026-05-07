import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, ArrowLeft } from 'lucide-react'
import { invoicesApi, vendorsApi, clientsApi } from '../lib/api'
import { formatCurrency } from '../lib/utils'

const EMPTY_LINE = { description: '', quantity: 1, unit_price: 0, discount: 0 }

function Field({ label, required, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        {label} {required && <span style={{ color: 'var(--accent)' }}>*</span>}
      </label>
      {children}
    </div>
  )
}

export default function CreateInvoice() {
  const navigate = useNavigate()
  const [vendors, setVendors] = useState([])
  const [clients, setClients] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const [form, setForm] = useState({
    invoice_number: '',
    issue_date: new Date().toISOString().split('T')[0],
    due_date: '',
    currency: 'USD',
    tax_percent: 0,
    payment_method: '',
    description: '',
    discount: 0,
    vendor_id: '',
    client_id: '',
    status: 'draft',
  })

  const [lineItems, setLineItems] = useState([{ ...EMPTY_LINE }])

  useEffect(() => {
    vendorsApi.list().then(res => {
      const list = Array.isArray(res) ? res : (res?.vendors || res?.data || [])
      setVendors(list)
    }).catch(() => {})
    clientsApi.list().then(res => {
      const list = Array.isArray(res) ? res : (res?.clients || res?.data || [])
      setClients(list)
    }).catch(() => {})
  }, [])

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const setLine = (i, k, v) => setLineItems(prev =>
    prev.map((item, idx) => idx === i ? { ...item, [k]: v } : item)
  )

  const addLine = () => setLineItems(prev => [...prev, { ...EMPTY_LINE }])
  const removeLine = (i) => setLineItems(prev => prev.filter((_, idx) => idx !== i))

  // Live calculations
  const subtotal = lineItems.reduce((s, l) => {
    const qty = parseFloat(l.quantity) || 0
    const price = parseFloat(l.unit_price) || 0
    const disc = parseFloat(l.discount) || 0
    return s + (qty * price - disc)
  }, 0)
  const invoiceDiscount = parseFloat(form.discount) || 0
  const taxable = subtotal - invoiceDiscount
  const totalTax = taxable * ((parseFloat(form.tax_percent) || 0) / 100)
  const grandTotal = taxable + totalTax

  const handleSubmit = async (statusOverride) => {
    setSaving(true)
    setError(null)
    try {
      const payload = {
        ...form,
        status: statusOverride || form.status,
        subtotal,
        total_tax: totalTax,
        grand_total: grandTotal,
        tax_percent: parseFloat(form.tax_percent) || 0,
        discount: invoiceDiscount,
        line_items: lineItems.map(l => ({
          description: l.description,
          quantity: parseFloat(l.quantity) || 0,
          unit_price: parseFloat(l.unit_price) || 0,
          discount: parseFloat(l.discount) || 0,
          line_subtotal: (parseFloat(l.quantity) || 0) * (parseFloat(l.unit_price) || 0) - (parseFloat(l.discount) || 0),
        })),
      }
      const res = await invoicesApi.create(payload)
      navigate(`/invoices/${res.id || res.invoice?.id}`)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl space-y-5 animate-fade-up">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-ghost p-2 rounded-xl">
          <ArrowLeft size={16} />
        </button>
        <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          New Invoice
        </h1>
      </div>

      {error && (
        <div className="card p-4 border-red-200 dark:border-red-900 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Invoice header info */}
      <div className="card p-5 space-y-4">
        <h2 className="text-sm font-semibold pb-2 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
          Invoice Details
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <Field label="Invoice Number" required>
            <input className="input h-9 text-sm" value={form.invoice_number}
              onChange={e => setField('invoice_number', e.target.value)}
              placeholder="INV-001" />
          </Field>
          <Field label="Issue Date" required>
            <input className="input h-9 text-sm" type="date" value={form.issue_date}
              onChange={e => setField('issue_date', e.target.value)} />
          </Field>
          <Field label="Due Date">
            <input className="input h-9 text-sm" type="date" value={form.due_date}
              onChange={e => setField('due_date', e.target.value)} />
          </Field>
          <Field label="Currency" required>
            <select className="input h-9 text-sm" value={form.currency}
              onChange={e => setField('currency', e.target.value)}>
              {['USD', 'EUR', 'GBP', 'TRY', 'AED', 'SAR'].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </Field>
          <Field label="Tax Rate (%)">
            <input className="input h-9 text-sm" type="number" min="0" max="100" step="0.1"
              value={form.tax_percent}
              onChange={e => setField('tax_percent', e.target.value)}
              placeholder="0" />
          </Field>
          <Field label="Payment Method">
            <select className="input h-9 text-sm" value={form.payment_method}
              onChange={e => setField('payment_method', e.target.value)}>
              <option value="">— Select —</option>
              <option value="bank_transfer">Bank Transfer</option>
              <option value="credit_card">Credit Card</option>
              <option value="cash">Cash</option>
              <option value="check">Check</option>
            </select>
          </Field>
        </div>
        <Field label="Description">
          <textarea className="input text-sm resize-none" rows={2} value={form.description}
            onChange={e => setField('description', e.target.value)}
            placeholder="Optional invoice description" />
        </Field>
      </div>

      {/* Vendor & Client */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5 space-y-3">
          <h2 className="text-sm font-semibold pb-2 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
            Vendor
          </h2>
          <Field label="Select Vendor">
            <select className="input h-9 text-sm" value={form.vendor_id}
              onChange={e => setField('vendor_id', e.target.value)}>
              <option value="">— Select vendor —</option>
              {vendors.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="card p-5 space-y-3">
          <h2 className="text-sm font-semibold pb-2 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
            Client
          </h2>
          <Field label="Select Client">
            <select className="input h-9 text-sm" value={form.client_id}
              onChange={e => setField('client_id', e.target.value)}>
              <option value="">— Select client —</option>
              {clients.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </Field>
        </div>
      </div>

      {/* Line items */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3.5 border-b flex items-center justify-between"
          style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Line Items</h2>
          <button onClick={addLine} className="btn-secondary text-xs h-7">
            <Plus size={12} /> Add Line
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Description', 'Quantity', 'Unit Price', 'Discount', 'Subtotal', ''].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wide"
                    style={{ color: 'var(--text-muted)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lineItems.map((line, i) => {
                const sub = (parseFloat(line.quantity) || 0) * (parseFloat(line.unit_price) || 0) - (parseFloat(line.discount) || 0)
                return (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td className="px-4 py-2">
                      <input className="input h-8 text-sm min-w-[180px]"
                        value={line.description}
                        onChange={e => setLine(i, 'description', e.target.value)}
                        placeholder="Item description" />
                    </td>
                    <td className="px-4 py-2">
                      <input className="input h-8 text-sm w-20 font-mono"
                        type="number" min="0" step="0.01"
                        value={line.quantity}
                        onChange={e => setLine(i, 'quantity', e.target.value)} />
                    </td>
                    <td className="px-4 py-2">
                      <input className="input h-8 text-sm w-28 font-mono"
                        type="number" min="0" step="0.01"
                        value={line.unit_price}
                        onChange={e => setLine(i, 'unit_price', e.target.value)} />
                    </td>
                    <td className="px-4 py-2">
                      <input className="input h-8 text-sm w-24 font-mono"
                        type="number" min="0" step="0.01"
                        value={line.discount}
                        onChange={e => setLine(i, 'discount', e.target.value)} />
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {formatCurrency(sub, form.currency)}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {lineItems.length > 1 && (
                        <button onClick={() => removeLine(i)} className="btn-ghost p-1.5 text-red-400 hover:text-red-600">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Totals */}
        <div className="p-5 border-t" style={{ borderColor: 'var(--border)' }}>
          <div className="flex justify-end">
            <div className="w-64 space-y-2">
              <div className="flex justify-between text-sm">
                <span style={{ color: 'var(--text-muted)' }}>Subtotal</span>
                <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {formatCurrency(subtotal, form.currency)}
                </span>
              </div>
              <div className="flex justify-between text-sm items-center">
                <span style={{ color: 'var(--text-muted)' }}>Discount</span>
                <input className="input h-7 text-xs font-mono w-28 text-right"
                  type="number" min="0" step="0.01"
                  value={form.discount}
                  onChange={e => setField('discount', e.target.value)}
                  placeholder="0.00" />
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: 'var(--text-muted)' }}>Tax ({form.tax_percent}%)</span>
                <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {formatCurrency(totalTax, form.currency)}
                </span>
              </div>
              <div className="flex justify-between items-center pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Grand Total</span>
                <span className="font-mono text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {formatCurrency(grandTotal, form.currency)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pb-8">
        <button onClick={() => navigate(-1)} className="btn-secondary">Cancel</button>
        <button onClick={() => handleSubmit('draft')} disabled={saving} className="btn-secondary disabled:opacity-50">
          Save as Draft
        </button>
        <button onClick={() => handleSubmit('sent')} disabled={saving} className="btn-primary disabled:opacity-50">
          {saving ? 'Saving…' : 'Save & Send'}
        </button>
      </div>
    </div>
  )
}