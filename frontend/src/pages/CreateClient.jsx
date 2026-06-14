import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, UserPlus, Loader2, ChevronDown } from 'lucide-react'
import { clientsApi } from '../lib/api'

const CLIENT_COUNTRIES = [
  { code: 'USA', label: 'United States' },
  { code: 'TUR', label: 'Turkey' },
  { code: 'SAU', label: 'Saudi Arabia' },
  { code: 'ARE', label: 'UAE' },
  { code: 'GBR', label: 'United Kingdom' },
  { code: 'DEU', label: 'Germany' },
  { code: 'EGY', label: 'Egypt' },
  { code: 'DNK', label: 'Denmark' },
  { code: 'BHR', label: 'Bahrain' },
  { code: 'FIN', label: 'Finland' },
]

const EMPTY = {
  name: '', tax_id: '', email: '', phone: '',
  street: '', city: '', state: '', postal_code: '', country: '',
}

function Field({ label, required, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        {label}{required && <span style={{ color: '#EF4444' }}> *</span>}
      </label>
      {children}
    </div>
  )
}

export default function CreateClient() {
  const navigate = useNavigate()
  const [form,     setForm]     = useState(EMPTY)
  const [saving,   setSaving]   = useState(false)
  const [error,    setError]    = useState('')
  const [success,  setSuccess]  = useState(false)

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const submit = async () => {
    setError('')
    if (!form.name.trim())   { setError('Name is required.'); return }
    if (!form.tax_id.trim()) { setError('Tax ID is required.'); return }

    const addressFields = ['street', 'city', 'state', 'postal_code', 'country']
    const hasAddress    = addressFields.some(f => form[f].trim())
    const address       = hasAddress
      ? Object.fromEntries(addressFields.map(f => [f, form[f].trim() || null]))
      : null

    const payload = {
      name:    form.name.trim(),
      tax_id:  form.tax_id.trim(),
      email:   form.email.trim()  || null,
      phone:   form.phone.trim()  || null,
      address,
    }

    setSaving(true)
    try {
      await clientsApi.create(payload)
      setSuccess(true)
      setForm(EMPTY)
      setTimeout(() => navigate('/clients'), 1200)
    } catch (e) {
      const msg = e.message || ''
      if (/tax_id already exists/i.test(msg) || msg.includes('409')) {
        setError('A client with this Tax ID already exists.')
      } else {
        setError(msg || 'Failed to create client.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-2xl animate-fade-up">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/clients')} className="btn-ghost p-2 rounded-xl">
          <ArrowLeft size={16} />
        </button>
        <div>
          <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
            Create Client
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Add a new client for receivable invoices
          </p>
        </div>
      </div>

      <div className="card p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Name" required>
            <input className="input h-9 text-sm" value={form.name}
              onChange={e => set('name', e.target.value)} placeholder="Acme Corp" />
          </Field>
          <Field label="Tax ID" required>
            <input className="input h-9 text-sm font-mono" value={form.tax_id}
              onChange={e => set('tax_id', e.target.value)} placeholder="12-3456789" />
          </Field>
          <Field label="Email">
            <input className="input h-9 text-sm" type="email" value={form.email}
              onChange={e => set('email', e.target.value)} placeholder="billing@acme.com" />
          </Field>
          <Field label="Phone">
            <input className="input h-9 text-sm" value={form.phone}
              onChange={e => set('phone', e.target.value)} placeholder="+1 555 000 0000" />
          </Field>
        </div>

        <div className="pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
          <p className="text-xs font-medium mb-3" style={{ color: 'var(--text-muted)' }}>
            Address (optional)
          </p>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Street">
              <input className="input h-9 text-sm" value={form.street}
                onChange={e => set('street', e.target.value)} />
            </Field>
            <Field label="City">
              <input className="input h-9 text-sm" value={form.city}
                onChange={e => set('city', e.target.value)} />
            </Field>
            <Field label="State">
              <input className="input h-9 text-sm" value={form.state}
                onChange={e => set('state', e.target.value)} />
            </Field>
            <Field label="Postal Code">
              <input className="input h-9 text-sm font-mono" value={form.postal_code}
                onChange={e => set('postal_code', e.target.value)} />
            </Field>
            <Field label="Country">
              <div className="relative">
                <select className="input h-9 text-sm appearance-none pr-8" value={form.country}
                  onChange={e => set('country', e.target.value)}>
                  <option value="">No country</option>
                  {CLIENT_COUNTRIES.map(c => (
                    <option key={c.code} value={c.code}>{c.label}</option>
                  ))}
                </select>
                <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-muted)' }} />
              </div>
            </Field>
          </div>
        </div>

        {error && (
          <div className="px-3 py-2 rounded-lg text-xs"
            style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#EF4444' }}>
            {error}
          </div>
        )}

        {success && (
          <div className="px-3 py-2 rounded-lg text-xs"
            style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', color: '#16A34A' }}>
            Client created — redirecting…
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button onClick={() => navigate('/clients')} className="btn-secondary text-sm">
            Cancel
          </button>
          <button onClick={submit} disabled={saving} className="btn-primary text-sm disabled:opacity-50">
            {saving
              ? <><Loader2 size={14} className="animate-spin" /> Creating…</>
              : <><UserPlus size={14} /> Create Client</>}
          </button>
        </div>
      </div>
    </div>
  )
}