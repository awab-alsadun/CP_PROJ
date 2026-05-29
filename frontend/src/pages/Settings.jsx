import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Save, Eye, EyeOff, LogOut, Upload, Trash2, Loader2, ChevronDown } from 'lucide-react'
import { settingsApi, adminApi, documentsApi } from '../lib/api'

// ── Toast ─────────────────────────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([])
  const add = useCallback((message, type = 'success') => {
    const id = Date.now()
    setToasts(p => [...p, { id, message, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
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

// ── Field helpers ──────────────────────────────────────────────────────────────
function Field({ label, hint, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      {children}
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

const TABS = ['Company Profile', 'Tax & Compliance', 'Notifications', 'Documents', 'Pipeline', 'Security']

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

export default function Settings() {
  const navigate = useNavigate()
  const { toasts, add: toast } = useToast()
  const [tab, setTab] = useState(0)

  // ── Company Profile ──────────────────────────────────────────────────────────
  const [profile, setProfile] = useState({ name: '', country: '', address: '', phone: '', email: '', tax_id: '' })
  const [defaultTaxRate, setDefaultTaxRate] = useState(0)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileLoaded, setProfileLoaded] = useState(false)

  // ── Tax rates reference ──────────────────────────────────────────────────────
  const [taxRates, setTaxRates] = useState({})

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

  // ── Pipeline ─────────────────────────────────────────────────────────────────
  const [pipeline, setPipeline] = useState(null)

  // ── Security ─────────────────────────────────────────────────────────────────
  const [pw,        setPw]        = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [showPw,    setShowPw]    = useState(false)

  useEffect(() => {
    // Load settings
    settingsApi.get().then(s => {
      if (!s) return
      setProfile({
        name: s.name || '', country: s.country || '', address: s.address || '',
        phone: s.phone || '', email: s.email || '', tax_id: s.tax_id || '',
      })
      setDefaultTaxRate(s.default_tax_rate ?? 0)
      setProfileLoaded(true)
    }).catch(() => { setProfileLoaded(true) })

    settingsApi.taxRates().then(r => setTaxRates(r || {})).catch(() => {})
    settingsApi.pipeline().then(setPipeline).catch(() => {})
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
      await settingsApi.setPassword(pw)
      setPw(''); setPwConfirm('')
      toast('Password set')
    } catch (e) { toast(e.message, 'error') }
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

      {/* ── Tab 0: Company Profile ─────────────────────────────────────────────── */}
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
                  onChange={e => {
                    const c = e.target.value
                    setProfile(p => ({ ...p, country: c }))
                    if (taxRates[c]) setDefaultTaxRate(taxRates[c])
                  }}>
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
        </div>
      )}

      {/* ── Tab 1: Tax & Compliance ────────────────────────────────────────────── */}
      {tab === 1 && (
        <div className="space-y-4">
          <div className="card p-6 space-y-4">
            <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
              Tax Settings
            </h2>
            <Field label="Default Tax Rate (%)" hint="Applied when creating new invoices">
              <input className="input h-9 text-sm font-mono w-32" type="number" min="0" max="100" step="0.1"
                value={defaultTaxRate} onChange={e => setDefaultTaxRate(parseFloat(e.target.value) || 0)} />
            </Field>

            {Object.keys(taxRates).length > 0 && (
              <div>
                <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                  Country Tax Reference — click to apply
                </p>
                <div className="grid grid-cols-3 gap-1.5">
                  {Object.entries(taxRates).map(([country, rate]) => (
                    <button key={country}
                      onClick={() => { setProfile(p => ({ ...p, country })); setDefaultTaxRate(rate) }}
                      className="text-left text-xs px-3 py-2 rounded-xl border transition-all hover:border-[var(--accent)]"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-secondary)' }}>
                      <span className="font-medium">{country}</span>
                      <span className="ml-1 font-mono" style={{ color: 'var(--text-muted)' }}>{rate}%</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

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
      )}

      {/* ── Tab 2: Notifications ──────────────────────────────────────────────── */}
      {tab === 2 && (
        <div className="card p-6 space-y-4">
          <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
            Notification Settings
          </h2>
          {[['Email Notifications', 'email'], ['SMS Notifications', 'sms']].map(([label, key]) => (
            <div key={key} className="flex items-center justify-between py-2">
              <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{label}</span>
              <div className="w-9 h-5 rounded-full flex items-center px-0.5"
                style={{ background: 'var(--border)', opacity: 0.6 }}>
                <div className="w-4 h-4 rounded-full bg-white shadow-sm" />
              </div>
            </div>
          ))}
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {pipeline?.email_provider
              ? `Email provider: ${pipeline.email_provider}`
              : 'Mock mode — no real emails sent'}
          </p>
        </div>
      )}

      {/* ── Tab 3: Documents ──────────────────────────────────────────────────── */}
      {tab === 3 && (
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

      {/* ── Tab 4: Pipeline ───────────────────────────────────────────────────── */}
      {tab === 4 && (
        <div className="space-y-3">
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Read-only — configured via backend .env
          </p>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'OCR Engine',       key: 'ocr_engine'       },
              { label: 'LLM Provider',     key: 'llm_provider'     },
              { label: 'Embedding Model',  key: 'embedding_model'  },
              { label: 'Reranker',         key: 'reranker'         },
            ].map(({ label, key }) => (
              <div key={key} className="card px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</p>
                  <p className="text-sm font-medium mt-0.5" style={{ color: 'var(--text-primary)' }}>
                    {pipeline?.[key] || '—'}
                  </p>
                </div>
                <div className="w-2 h-2 rounded-full"
                  style={{ background: pipeline?.[key] ? '#22C55E' : 'var(--border)' }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Tab 5: Security ───────────────────────────────────────────────────── */}
      {tab === 5 && (
        <div className="space-y-4">
          <div className="card p-6 space-y-4">
            <h2 className="text-sm font-semibold pb-3 border-b" style={{ color: 'var(--text-primary)', borderColor: 'var(--border)' }}>
              Settings Password
            </h2>
            <div className="grid grid-cols-1 gap-3 max-w-sm">
              <Field label="New Password">
                <div className="relative">
                  <input className="input h-9 text-sm pr-10" type={showPw ? 'text' : 'password'}
                    value={pw} onChange={e => setPw(e.target.value)} />
                  <button onClick={() => setShowPw(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>
              <Field label="Confirm Password">
                <input className="input h-9 text-sm" type="password"
                  value={pwConfirm} onChange={e => setPwConfirm(e.target.value)} />
              </Field>
              <button onClick={setPassword} disabled={!pw || !pwConfirm} className="btn-primary text-sm disabled:opacity-50 w-fit">
                Set Password
              </button>
            </div>
          </div>

          <div className="card p-6">
            <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>Session</h2>
            <div className="space-y-2">
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Company ID: <span className="font-mono">{localStorage.getItem('company_id') || '—'}</span>
              </div>
              <button
                onClick={() => { localStorage.removeItem('company_id'); navigate('/login') }}
                className="btn-secondary text-sm"
                style={{ color: '#EF4444', borderColor: '#FECACA' }}
              >
                <LogOut size={14} /> Log Out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
