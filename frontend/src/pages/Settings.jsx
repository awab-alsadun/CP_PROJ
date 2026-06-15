import { useState, useEffect, useCallback, Component } from 'react'
import { useNavigate } from 'react-router-dom'
import { Save, Eye, EyeOff, LogOut, Upload, Trash2, Loader2, ChevronDown, UserPlus, Image as ImageIcon } from 'lucide-react'
import { settingsApi, adminApi, documentsApi, clientsApi } from '../lib/api'

// ── Toast ─────────────────────────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([])
  const add = useCallback((message, type = 'success') => {
    const id = Date.now()
    setToasts(p => [...p, { id, message, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3000)
  }, [])
  return { toasts, add }
}

function Toasts({ toasts }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id}
          className="px-4 py-3 rounded-xl shadow-lg text-sm font-medium animate-fade-up pointer-events-auto"
          style={{
            background: 'var(--bg-card)',
            border: `1px solid ${t.type === 'error' ? '#FECACA' : '#BBF7D0'}`,
            color: t.type === 'error' ? '#EF4444' : '#16A34A',
            minWidth: 240,
          }}>
          {t.message}
        </div>
      ))}
    </div>
  )
}

// ── Error boundary (scoped per-tab) ───────────────────────────────────────────
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[Settings tab crash]', error, info?.componentStack)
  }
  reset = () => this.setState({ error: null })
  render() {
    if (this.state.error) {
      return (
        <div className="card p-6">
          <h2 className="text-sm font-semibold mb-2" style={{ color: '#EF4444' }}>
            This section failed to render
          </h2>
          <p className="text-xs mb-3 font-mono" style={{ color: 'var(--text-secondary)' }}>
            {this.state.error?.message || 'Unknown error'}
          </p>
          <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
            Other tabs are unaffected. See browser console for details.
          </p>
          <button onClick={this.reset} className="btn-secondary text-xs">
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ── Field helper ──────────────────────────────────────────────────────────────
function Field({ label, hint, required, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
        {label}{required && <span style={{ color: '#EF4444' }}> *</span>}
      </label>
      {children}
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

const TABS = ['Company Profile', 'Create Client', 'Invoice Branding', 'Tax & Compliance', 'Documents']

const DOC_TYPES = [
  { value: 'tax_regulation',   label: 'Tax Regulation'  },
  { value: 'compliance_guide', label: 'Compliance Guide' },
  { value: 'vat_rules',        label: 'VAT Rules'        },
  { value: 'customs',          label: 'Customs & Tariff' },
  { value: 'company_policy',   label: 'Company Policy'   },
  { value: 'general',          label: 'General'          },
]

const COUNTRIES = [
  { value: '',   label: 'No country' },
  { value: 'US', label: 'United States' },
  { value: 'TR', label: 'Turkey'        },
  { value: 'SA', label: 'Saudi Arabia'  },
  { value: 'AE', label: 'UAE'           },
  { value: 'GB', label: 'United Kingdom'},
  { value: 'DE', label: 'Germany'       },
  { value: 'EG', label: 'Egypt'         },
  { value: 'DK', label: 'Denmark'       },
  { value: 'BH', label: 'Bahrain'       },
  { value: 'FI', label: 'Finland'       },
]

const EMPTY_CLIENT = {
  name: '', tax_id: '', email: '', phone: '',
  street: '', city: '', state: '', postal_code: '', country: '',
}

// Branding defaults (from backend spec)
const BRANDING_DEFAULTS = {
  invoice_primary_color: '#1F2937',
  invoice_accent_color:  '#6B7280',
  invoice_text_color:    '#FFFFFF',
  invoice_footer_text:   '',
  logo_url:              null,
}

const HEX_RE = /^#[0-9A-Fa-f]{6}$/
const LOGO_MAX_BYTES = 2 * 1024 * 1024
const LOGO_ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']

export default function Settings() {
  const navigate = useNavigate()
  const { toasts, add: toast } = useToast()
  const [tab, setTab] = useState(0)

  // ── Company Profile ──────────────────────────────────────────────────────────
  const [profile, setProfile] = useState({ name: '', country: '', address: '', phone: '', email: '', tax_id: '' })
  const [defaultTaxRate, setDefaultTaxRate] = useState(0)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileLoaded, setProfileLoaded] = useState(false)

  // ── Admin ────────────────────────────────────────────────────────────────────
  const [overdueResult,    setOverdueResult]    = useState(null)
  const [complianceResult, setComplianceResult] = useState(null)
  const [adminLoading,     setAdminLoading]     = useState('')

  // ── Documents ────────────────────────────────────────────────────────────────
  const [docs,          setDocs]          = useState([])
  const [docsLoading,   setDocsLoading]   = useState(false)
  const [docFile,       setDocFile]       = useState(null)
  const [docType,       setDocType]       = useState('tax_regulation')
  const [docCountry,    setDocCountry]    = useState('US')
  const [docUploading,  setDocUploading]  = useState(false)

  // ── Create Client ────────────────────────────────────────────────────────────
  const [client,         setClient]         = useState(EMPTY_CLIENT)
  const [clientCreating, setClientCreating] = useState(false)
  const [clientError,    setClientError]    = useState('')

  // ── Account (password + session) ─────────────────────────────────────────────
  const [pwCurrent, setPwCurrent] = useState('')
  const [pw,        setPw]        = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [showPw,    setShowPw]    = useState(false)

  // ── Branding ─────────────────────────────────────────────────────────────────
  const [branding,        setBranding]        = useState(BRANDING_DEFAULTS)
  const [brandingLoaded,  setBrandingLoaded]  = useState(false)
  const [brandingSaving,  setBrandingSaving]  = useState(false)
  const [logoFile,        setLogoFile]        = useState(null)
  const [logoUploading,   setLogoUploading]   = useState(false)

  useEffect(() => {
    settingsApi.get().then(s => {
      if (!s) return
      setProfile({
        name: s.name || '', country: s.country || '', address: s.address || '',
        phone: s.phone || '', email: s.email || '', tax_id: s.tax_id || '',
      })
      setDefaultTaxRate(s.default_tax_rate ?? 0)
      setProfileLoaded(true)
    }).catch(() => { setProfileLoaded(true) })

    settingsApi.getBranding().then(b => {
      if (!b) return
      setBranding({
        invoice_primary_color: b.invoice_primary_color || BRANDING_DEFAULTS.invoice_primary_color,
        invoice_accent_color:  b.invoice_accent_color  || BRANDING_DEFAULTS.invoice_accent_color,
        invoice_text_color:    b.invoice_text_color    || BRANDING_DEFAULTS.invoice_text_color,
        invoice_footer_text:   b.invoice_footer_text   || '',
        logo_url:              b.logo_url              || null,
      })
      setBrandingLoaded(true)
    }).catch(() => { setBrandingLoaded(true) })

    loadDocs()
  }, [])

  const loadDocs = async () => {
    setDocsLoading(true)
    try {
      const res = await documentsApi.list()
      setDocs(res?.documents || res?.data || [])
    } catch {}
    finally { setDocsLoading(false) }
  }

  const saveProfile = async () => {
    setProfileSaving(true)
    try {
      await settingsApi.update({ ...profile, default_tax_rate: defaultTaxRate })
      toast('Settings saved')
    } catch (e) { toast(e.message, 'error') }
    finally { setProfileSaving(false) }
  }

  const runAdmin = async (action) => {
    setAdminLoading(action)
    try {
      const res = await (action === 'overdue' ? adminApi.runOverdueCheck() : adminApi.runComplianceCheck())
      if (action === 'overdue') setOverdueResult(res)
      else setComplianceResult(res)
      toast('Check completed')
    } catch (e) { toast(e.message, 'error') }
    finally { setAdminLoading('') }
  }

  const uploadDoc = async () => {
    if (!docFile) return
    setDocUploading(true)
    try {
      await documentsApi.upload(docFile, docType, docCountry || null)
      toast('Document uploaded')
      setDocFile(null)
      loadDocs()
    } catch (e) { toast(e.message, 'error') }
    finally { setDocUploading(false) }
  }

  const deleteDoc = async (id) => {
    try {
      await documentsApi.delete(id)
      toast('Document deleted')
      loadDocs()
    } catch (e) { toast(e.message, 'error') }
  }

  const setPassword = async () => {
    if (!pw || pw !== pwConfirm) { toast('Passwords do not match', 'error'); return }
    try {
      await settingsApi.setPassword(pw, pwCurrent)
      setPwCurrent(''); setPw(''); setPwConfirm('')
      toast('Password set')
    } catch (e) {
      const msg = e.message || ''
      if (msg.includes('403') || /incorrect|wrong password|invalid password/i.test(msg)) {
        toast('Current password is incorrect', 'error')
      } else {
        toast(msg || 'Failed to set password', 'error')
      }
    }
  }

  const logout = () => {
    localStorage.removeItem('company_id')
    navigate('/login')
  }

  const createClient = async () => {
    setClientError('')

    if (!client.name.trim()) { setClientError('Name is required.'); return }
    if (!client.tax_id.trim()) { setClientError('Tax ID is required.'); return }

    const addressFields = ['street', 'city', 'state', 'postal_code', 'country']
    const hasAddress = addressFields.some(f => client[f].trim())
    const address = hasAddress
      ? Object.fromEntries(addressFields.map(f => [f, client[f].trim() || null]))
      : null

    const payload = {
      name: client.name.trim(),
      tax_id: client.tax_id.trim(),
      email: client.email.trim() || null,
      phone: client.phone.trim() || null,
      address,
    }

    setClientCreating(true)
    try {
      await clientsApi.create(payload)
      setClient(EMPTY_CLIENT)
      toast('Client created')
    } catch (e) {
      const msg = e.message || ''
      if (/tax_id already exists/i.test(msg) || msg.includes('409')) {
        setClientError('A client with this tax ID already exists.')
      } else {
        setClientError(msg || 'Failed to create client.')
      }
    } finally {
      setClientCreating(false)
    }
  }

  // ── Branding handlers ────────────────────────────────────────────────────────
  const setColor = (key, value) => {
    setBranding(b => ({ ...b, [key]: value }))
  }

  const onLogoPick = (e) => {
    const f = e.target.files?.[0]
    if (!f) { setLogoFile(null); return }

    if (!LOGO_ACCEPTED_TYPES.includes(f.type)) {
      toast(`Unsupported file type. Allowed: PNG, JPEG, WebP`, 'error')
      e.target.value = ''
      setLogoFile(null)
      return
    }
    if (f.size > LOGO_MAX_BYTES) {
      toast('Logo exceeds 2 MB limit.', 'error')
      e.target.value = ''
      setLogoFile(null)
      return
    }
    setLogoFile(f)
  }

  const uploadLogo = async () => {
    if (!logoFile) return
    setLogoUploading(true)
    try {
      const res = await settingsApi.uploadLogo(logoFile)
      setBranding(b => ({ ...b, logo_url: res?.logo_url || b.logo_url }))
      setLogoFile(null)
      toast('Logo uploaded')
    } catch (e) {
      toast(e.message || 'Logo upload failed', 'error')
    } finally {
      setLogoUploading(false)
    }
  }

  const saveBranding = async () => {
    const colorKeys = ['invoice_primary_color', 'invoice_accent_color', 'invoice_text_color']
    for (const k of colorKeys) {
      if (!HEX_RE.test(branding[k] || '')) {
        toast(`Invalid hex color in ${k.replace(/_/g, ' ')}. Expected #RRGGBB.`, 'error')
        return
      }
    }

    setBrandingSaving(true)
    try {
      const payload = {
        invoice_primary_color: branding.invoice_primary_color,
        invoice_accent_color:  branding.invoice_accent_color,
        invoice_text_color:    branding.invoice_text_color,
        invoice_footer_text:   branding.invoice_footer_text.trim() || null,
      }
      const res = await settingsApi.updateBranding(payload)
      if (res) {
        setBranding(b => ({
          ...b,
          invoice_primary_color: res.invoice_primary_color || b.invoice_primary_color,
          invoice_accent_color:  res.invoice_accent_color  || b.invoice_accent_color,
          invoice_text_color:    res.invoice_text_color    || b.invoice_text_color,
          invoice_footer_text:   res.invoice_footer_text   || '',
          logo_url:              res.logo_url ?? b.logo_url,
        }))
      }
      toast('Branding saved')
    } catch (e) {
      toast(e.message || 'Failed to save branding', 'error')
    } finally {
      setBrandingSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-3xl space-y-5 animate-fade-up">
      <Toasts toasts={toasts} />

      {/* Tab bar */}
      <div className="flex gap-0 border-b overflow-x-auto" style={{ borderColor: 'var(--border)' }}>
        {TABS.map((t, i) => (
          <button key={i} onClick={() => setTab(i)}
            className="px-4 py-2.5 text-xs font-medium whitespace-nowrap transition-all"
            style={{
              color: tab === i ? 'var(--text-primary)' : 'var(--text-muted)',
              borderBottom: tab === i ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'transparent',
            }}>
            {t}
          </button>
        ))}
      </div>

      {/* ── Tab 0: Company Profile + Account ───────────────────────────────────── */}
      {tab === 0 && (
        <div className="card p-6 space-y-4">
          <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
            Company Profile
          </h2>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Company Name">
              <input className="input h-9 text-sm" value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))} />
            </Field>
            <Field label="Country">
              <div className="relative">
                <select className="input h-9 text-sm appearance-none pr-8" value={profile.country}
                  onChange={e => setProfile(p => ({ ...p, country: e.target.value }))}>
                  {COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
                <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-muted)' }} />
              </div>
            </Field>
            <Field label="Email">
              <input className="input h-9 text-sm" type="email" value={profile.email}
                onChange={e => setProfile(p => ({ ...p, email: e.target.value }))} />
            </Field>
            <Field label="Phone">
              <input className="input h-9 text-sm" value={profile.phone}
                onChange={e => setProfile(p => ({ ...p, phone: e.target.value }))} />
            </Field>
            <Field label="Tax ID">
              <input className="input h-9 text-sm font-mono" value={profile.tax_id}
                onChange={e => setProfile(p => ({ ...p, tax_id: e.target.value }))} />
            </Field>
            <Field label="Address">
              <input className="input h-9 text-sm" value={profile.address}
                onChange={e => setProfile(p => ({ ...p, address: e.target.value }))} />
            </Field>
          </div>
          <div className="flex justify-end pt-2">
            <button onClick={saveProfile} disabled={profileSaving} className="btn-primary disabled:opacity-50">
              <Save size={14} /> {profileSaving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>

          {/* ── Divider + Account section ───────────────────────────────────────── */}
          <div className="pt-6 mt-4" style={{ borderTop: '1px solid var(--border)' }}>
            <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
              Account
            </h2>

            <div className="space-y-3 max-w-sm">
              <Field label="Current Password" hint="Leave blank if no password is set yet.">
                <input className="input h-9 text-sm" type="password"
                  value={pwCurrent} onChange={e => setPwCurrent(e.target.value)}
                  autoComplete="current-password" />
              </Field>
              <Field label="New Password">
                <div className="relative">
                  <input className="input h-9 text-sm pr-10" type={showPw ? 'text' : 'password'}
                    value={pw} onChange={e => setPw(e.target.value)}
                    autoComplete="new-password" />
                  <button onClick={() => setShowPw(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>
              <Field label="Confirm New Password">
                <input className="input h-9 text-sm" type="password"
                  value={pwConfirm} onChange={e => setPwConfirm(e.target.value)}
                  autoComplete="new-password" />
              </Field>
              <button onClick={setPassword} disabled={!pw || !pwConfirm}
                className="btn-primary text-sm disabled:opacity-50 w-fit">
                Set Password
              </button>
            </div>

            <div className="pt-4 mt-6 space-y-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Company ID: <span className="font-mono">{localStorage.getItem('company_id') || '—'}</span>
              </div>
              <button onClick={logout} className="btn-secondary text-sm"
                style={{ color: '#EF4444', borderColor: '#FECACA' }}>
                <LogOut size={14} /> Log Out
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 1: Create Client ───────────────────────────────────────────────── */}
      {tab === 1 && (
        <div className="card p-6 space-y-4">
          <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
            Create Client
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Name" required>
              <input className="input h-9 text-sm" value={client.name}
                onChange={e => setClient(c => ({ ...c, name: e.target.value }))} />
            </Field>
            <Field label="Tax ID" required>
              <input className="input h-9 text-sm font-mono" value={client.tax_id}
                onChange={e => setClient(c => ({ ...c, tax_id: e.target.value }))} />
            </Field>
            <Field label="Email">
              <input className="input h-9 text-sm" type="email" value={client.email}
                onChange={e => setClient(c => ({ ...c, email: e.target.value }))} />
            </Field>
            <Field label="Phone">
              <input className="input h-9 text-sm" value={client.phone}
                onChange={e => setClient(c => ({ ...c, phone: e.target.value }))} />
            </Field>
          </div>

          <div className="pt-2">
            <p className="text-xs font-medium mb-3" style={{ color: 'var(--text-muted)' }}>
              Address (optional)
            </p>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Street">
                <input className="input h-9 text-sm" value={client.street}
                  onChange={e => setClient(c => ({ ...c, street: e.target.value }))} />
              </Field>
              <Field label="City">
                <input className="input h-9 text-sm" value={client.city}
                  onChange={e => setClient(c => ({ ...c, city: e.target.value }))} />
              </Field>
              <Field label="State">
                <input className="input h-9 text-sm" value={client.state}
                  onChange={e => setClient(c => ({ ...c, state: e.target.value }))} />
              </Field>
              <Field label="Postal Code">
                <input className="input h-9 text-sm font-mono" value={client.postal_code}
                  onChange={e => setClient(c => ({ ...c, postal_code: e.target.value }))} />
              </Field>
              <Field label="Country" hint="3-letter ISO code">
                <input className="input h-9 text-sm font-mono uppercase" maxLength={3}
                  placeholder="USA" value={client.country}
                  onChange={e => setClient(c => ({ ...c, country: e.target.value.toUpperCase() }))} />
              </Field>
            </div>
          </div>

          {clientError && (
            <div className="px-3 py-2 rounded-lg text-xs"
              style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#EF4444' }}>
              {clientError}
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button onClick={createClient} disabled={clientCreating}
              className="btn-primary disabled:opacity-50">
              {clientCreating
                ? <><Loader2 size={14} className="animate-spin" /> Creating…</>
                : <><UserPlus size={14} /> Create Client</>}
            </button>
          </div>
        </div>
      )}

      {/* ── Tab 2: Invoice Branding ────────────────────────────────────────────── */}
      {tab === 2 && (
        <ErrorBoundary>
          <div className="space-y-4">
            {/* Logo */}
            <div className="card p-6 space-y-4">
              <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
                Logo
              </h2>

              <div className="flex items-start gap-5">
                <div
                  className="rounded-lg flex items-center justify-center overflow-hidden flex-shrink-0"
                  style={{
                    width: 140, height: 60,
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                  }}
                >
                  {branding.logo_url ? (
                    <img src={branding.logo_url} alt="Company logo"
                      style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  ) : (
                    <ImageIcon size={20} style={{ color: 'var(--text-muted)' }} />
                  )}
                </div>

                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => document.getElementById('settings-logo-input').click()}
                      disabled={logoUploading}
                      className="btn-secondary text-sm"
                    >
                      <Upload size={13} />
                      {logoFile ? logoFile.name.slice(0, 28) : 'Choose Image'}
                    </button>
                    <input id="settings-logo-input" type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden" onChange={onLogoPick} />
                    {logoFile && (
                      <button onClick={uploadLogo} disabled={logoUploading}
                        className="btn-primary text-sm disabled:opacity-50">
                        {logoUploading
                          ? <><Loader2 size={13} className="animate-spin" /> Uploading…</>
                          : 'Upload'}
                      </button>
                    )}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    PNG, JPEG, or WebP. Max 2 MB. Recommended ratio ~7:3.
                  </p>
                </div>
              </div>
            </div>

            {/* Colors */}
            <div className="card p-6 space-y-4">
              <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
                Colors
              </h2>

              <ColorRow
                label="Primary color"
                hint="Total Due bar background"
                value={branding.invoice_primary_color}
                onChange={v => setColor('invoice_primary_color', v)}
              />
              <ColorRow
                label="Accent color"
                hint="Line items table header background"
                value={branding.invoice_accent_color}
                onChange={v => setColor('invoice_accent_color', v)}
              />
              <ColorRow
                label="Text color"
                hint="Text on Primary and Accent bars — needs contrast with both"
                value={branding.invoice_text_color}
                onChange={v => setColor('invoice_text_color', v)}
              />
            </div>

            {/* Footer text */}
            <div className="card p-6 space-y-4">
              <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
                Invoice Footer Text
              </h2>
              <Field label="Footer" hint="Payment instructions, IBAN, thank-you note. Plain text.">
                <textarea
                  className="input text-sm"
                  rows={4}
                  style={{ height: 'auto', resize: 'vertical', padding: '8px 12px' }}
                  value={branding.invoice_footer_text}
                  onChange={e => setBranding(b => ({ ...b, invoice_footer_text: e.target.value }))}
                  placeholder="Payment due within 30 days. Thank you."
                />
              </Field>
            </div>

            <div className="flex justify-end">
              <button onClick={saveBranding} disabled={brandingSaving || !brandingLoaded}
                className="btn-primary disabled:opacity-50">
                {brandingSaving
                  ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
                  : <><Save size={14} /> Save Branding</>}
              </button>
            </div>
          </div>
        </ErrorBoundary>
      )}

      {/* ── Tab 3: Tax & Compliance (wrapped in ErrorBoundary) ─────────────────── */}
      {tab === 3 && (
        <ErrorBoundary>
          <div className="space-y-4">
            <div className="card p-6 space-y-4">
              <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
                Tax Settings
              </h2>
              <Field label="Default Tax Rate (%)" hint="Applied when creating new invoices">
                <input className="input h-9 text-sm font-mono w-32" type="number" min="0" max="100" step="0.1"
                  value={defaultTaxRate} onChange={e => setDefaultTaxRate(parseFloat(e.target.value) || 0)} />
              </Field>

              <div className="flex justify-end">
                <button onClick={saveProfile} disabled={profileSaving} className="btn-primary text-sm disabled:opacity-50">
                  <Save size={13} /> Save
                </button>
              </div>
            </div>

            <div className="card p-6 space-y-4">
              <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
                Admin Actions
              </h2>
              <div className="flex gap-3 flex-wrap">
                <div>
                  <button
                    onClick={() => runAdmin('overdue')}
                    disabled={!!adminLoading}
                    className="btn-secondary text-sm disabled:opacity-50"
                  >
                    {adminLoading === 'overdue' ? <><Loader2 size={13} className="animate-spin" /> Running…</> : 'Run Overdue Check'}
                  </button>
                  {overdueResult && (
                    <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                      {overdueResult.marked_overdue ?? 0} invoices marked overdue
                    </p>
                  )}
                </div>
                <div>
                  <button
                    onClick={() => runAdmin('compliance')}
                    disabled={!!adminLoading}
                    className="btn-secondary text-sm disabled:opacity-50"
                  >
                    {adminLoading === 'compliance' ? <><Loader2 size={13} className="animate-spin" /> Running…</> : 'Run Compliance Check'}
                  </button>
                  {complianceResult && (
                    <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                      {complianceResult.invoices_checked ?? 0} checked · {complianceResult.flags_created ?? 0} new flags
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </ErrorBoundary>
      )}

      {/* ── Tab 4: Documents ──────────────────────────────────────────────────── */}
      {tab === 4 && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Upload Regulation Document
              </h2>
            </div>
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Document Type">
                  <div className="relative">
                    <select className="input h-9 text-sm appearance-none pr-8" value={docType}
                      onChange={e => setDocType(e.target.value)} disabled={docUploading}>
                      {DOC_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                    <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: 'var(--text-muted)' }} />
                  </div>
                </Field>
                <Field label="Country">
                  <div className="relative">
                    <select className="input h-9 text-sm appearance-none pr-8" value={docCountry}
                      onChange={e => setDocCountry(e.target.value)} disabled={docUploading}>
                      {COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                    <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: 'var(--text-muted)' }} />
                  </div>
                </Field>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => document.getElementById('settings-doc-input').click()}
                  disabled={docUploading}
                  className="btn-secondary text-sm"
                >
                  <Upload size={13} />
                  {docFile ? docFile.name.slice(0, 30) : 'Choose PDF'}
                </button>
                <input id="settings-doc-input" type="file" accept=".pdf" className="hidden"
                  onChange={e => setDocFile(e.target.files[0] || null)} />
                {docFile && (
                  <button onClick={uploadDoc} disabled={docUploading} className="btn-primary text-sm disabled:opacity-50">
                    {docUploading ? <><Loader2 size={13} className="animate-spin" /> Uploading…</> : 'Upload & Embed'}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="px-5 py-3.5 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Uploaded Documents</h2>
              <span className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                {docs.length}
              </span>
            </div>
            {docsLoading ? (
              <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin" style={{ color: 'var(--text-muted)' }} /></div>
            ) : docs.length === 0 ? (
              <div className="py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>No documents uploaded</div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Name', 'Type', 'Country', 'Chunks', 'Date', ''].map(h => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-medium uppercase tracking-wide"
                        style={{ color: 'var(--text-muted)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {docs.map(d => (
                    <tr key={d.document_id || d.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td className="px-5 py-3 text-sm font-medium truncate max-w-[180px]"
                        style={{ color: 'var(--text-primary)' }}>{d.document_name || d.name || '—'}</td>
                      <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>{d.document_type}</td>
                      <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>{d.country || '—'}</td>
                      <td className="px-5 py-3 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{d.chunk_count ?? '—'}</td>
                      <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                        {d.uploaded_at?.slice(0, 10) || '—'}
                      </td>
                      <td className="px-5 py-3">
                        <button onClick={() => deleteDoc(d.document_id || d.id)}
                          className="btn-ghost p-1.5 rounded-lg hover:text-red-500">
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── ColorRow — picker + synced hex text input ──────────────────────────────────
function ColorRow({ label, hint, value, onChange }) {
  const safeValue = HEX_RE.test(value || '') ? value : '#000000'

  return (
    <div className="flex items-start gap-4">
      <div className="flex-1">
        <Field label={label} hint={hint}>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={safeValue.toLowerCase()}
              onChange={e => onChange(e.target.value.toUpperCase())}
              className="cursor-pointer flex-shrink-0"
              style={{
                width: 44, height: 36,
                border: '1px solid var(--border)',
                borderRadius: 8,
                background: 'transparent',
                padding: 2,
              }}
            />
            <input
              type="text"
              value={value || ''}
              onChange={e => onChange(e.target.value)}
              className="input h-9 text-sm font-mono uppercase"
              style={{ width: 130 }}
              placeholder="#000000"
              maxLength={7}
              spellCheck={false}
            />
          </div>
        </Field>
      </div>
    </div>
  )
}