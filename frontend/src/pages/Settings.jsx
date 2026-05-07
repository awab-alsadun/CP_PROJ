import { useState, useEffect } from 'react'
import { Save, Eye, EyeOff } from 'lucide-react'

function SettingsSection({ title, description, children }) {
  return (
    <div className="card p-6 space-y-5">
      <div className="pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
        {description && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{description}</p>}
      </div>
      {children}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      {children}
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

export default function Settings() {
  const [saved, setSaved] = useState(false)
  const [showKey, setShowKey] = useState(false)

  const [config, setConfig] = useState({
    company_id: localStorage.getItem('company_id') || '',
    backend_url: localStorage.getItem('backend_url') || 'http://127.0.0.1:8000',
    openai_key_hint: '(stored in backend .env)',
  })

  const handleSave = () => {
    localStorage.setItem('company_id', config.company_id)
    localStorage.setItem('backend_url', config.backend_url)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="p-6 max-w-2xl space-y-5 animate-fade-up">
      <div>
        <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Settings
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Configure your workspace and connection settings.
        </p>
      </div>

      <SettingsSection
        title="Workspace"
        description="Multi-tenant configuration. The company ID scopes all data to your organization."
      >
        <Field
          label="Company ID"
          hint="UUID of your company in Supabase. All API calls are scoped to this ID."
        >
          <input
            className="input h-9 text-sm font-mono"
            value={config.company_id}
            onChange={e => setConfig(c => ({ ...c, company_id: e.target.value }))}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          />
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Backend"
        description="FastAPI server connection. Change this if your backend runs on a different port."
      >
        <Field label="Backend URL" hint="The Vite dev proxy will forward /api requests to this address.">
          <input
            className="input h-9 text-sm font-mono"
            value={config.backend_url}
            onChange={e => setConfig(c => ({ ...c, backend_url: e.target.value }))}
          />
        </Field>
        <Field label="OpenAI API Key" hint="Managed in backend/.env — not stored in the frontend.">
          <div className="relative">
            <input
              className="input h-9 text-sm pr-10"
              type={showKey ? 'text' : 'password'}
              value={config.openai_key_hint}
              readOnly
            />
            <button
              onClick={() => setShowKey(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-muted)' }}
            >
              {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </Field>
      </SettingsSection>

      <SettingsSection title="Pipeline" description="Invoice processing defaults.">
        <div className="grid grid-cols-2 gap-4">
          <Field label="OCR Engine">
            <select className="input h-9 text-sm">
              <option value="tesseract">Tesseract (primary)</option>
              <option value="pymupdf">PyMuPDF (native text)</option>
            </select>
          </Field>
          <Field label="LLM Model">
            <select className="input h-9 text-sm">
              <option value="gpt-4o">GPT-4o (OpenAI)</option>
              <option value="local">Local model (toggle)</option>
            </select>
          </Field>
          <Field label="Embedding Model">
            <select className="input h-9 text-sm">
              <option value="text-embedding-3-small">text-embedding-3-small</option>
              <option value="text-embedding-3-large">text-embedding-3-large</option>
            </select>
          </Field>
          <Field label="Max Workers">
            <input className="input h-9 text-sm font-mono" type="number"
              defaultValue={3} min={1} max={10} />
          </Field>
        </div>
      </SettingsSection>

      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary">
          <Save size={14} />
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}