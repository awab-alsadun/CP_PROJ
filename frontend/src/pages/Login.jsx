import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Eye, EyeOff } from 'lucide-react'

export default function Login() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', company_id: '' })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      // For demo: store company_id and proceed. In production: call auth endpoint.
      const cid = form.company_id.trim()
      if (!cid) {
        throw new Error('Company ID is required.')
      }
      const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      if (!uuidPattern.test(cid)) {
        throw new Error('Company ID must be a valid UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).')
      }
      localStorage.setItem('company_id', cid)
      localStorage.setItem('user_email', form.email)
      // Simulate auth delay
      await new Promise(r => setTimeout(r, 500))
      navigate('/')
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4"
      style={{ background: 'var(--bg-primary)' }}>

      {/* Background texture */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full opacity-[0.04]"
          style={{ background: 'var(--accent)', filter: 'blur(80px)' }} />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full opacity-[0.04]"
          style={{ background: 'var(--accent)', filter: 'blur(80px)' }} />
      </div>

      <div className="w-full max-w-sm space-y-8 relative">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{ background: 'var(--accent)' }}>
            <Zap size={22} color="#131310" strokeWidth={2.5} />
          </div>
          <div className="text-center">
            <h1 className="font-display text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
              Invox
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              AI Invoice Intelligence
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="card p-8 space-y-5">
          <div>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Sign in</h2>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Enter your company credentials</p>
          </div>

          {error && (
            <div className="text-xs text-red-600 px-3 py-2.5 rounded-xl border border-red-200 dark:border-red-900">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Email
              </label>
              <input
                className="input h-10"
                type="email"
                placeholder="you@company.com"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Password
              </label>
              <div className="relative">
                <input
                  className="input h-10 pr-10"
                  type={showPass ? 'text' : 'password'}
                  placeholder="••••••••"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Company ID
              </label>
              <input
                className="input h-10 font-mono text-sm"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={form.company_id}
                onChange={e => setForm(f => ({ ...f, company_id: e.target.value }))}
                required
              />
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                UUID from your Supabase companies table
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full h-10 justify-center disabled:opacity-60"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}