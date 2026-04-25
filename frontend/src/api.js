const BASE = '/api/v1'

// company_id is stored after login — for demo we seed it from env/localStorage
export function getCompanyId() {
  return localStorage.getItem('company_id') || ''
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Invoices ──────────────────────────────────────────────
export const invoicesApi = {
  list: (params = {}) => {
    const q = new URLSearchParams()
    const cid = getCompanyId()
    if (cid) q.set('company_id', cid)
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, v))
    return request(`/invoices?${q}`)
  },
  get: (id) => request(`/invoices/${id}`),
  create: (body) => request('/invoices', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/invoices/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (id) => request(`/invoices/${id}`, { method: 'DELETE' }),
  transition: (id, status) => request(`/invoices/${id}/transition`, {
    method: 'POST', body: JSON.stringify({ status }),
  }),
  recordPayment: (id, body) => request(`/invoices/${id}/payments`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  getRaw: (id) => request(`/invoices/${id}/raw`),
}

// ── Vendors ───────────────────────────────────────────────
export const vendorsApi = {
  list: (params = {}) => {
    const q = new URLSearchParams()
    const cid = getCompanyId()
    if (cid) q.set('company_id', cid)
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, v))
    return request(`/vendors?${q}`)
  },
  get: (id) => request(`/vendors/${id}`),
  create: (body) => request('/vendors', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/vendors/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
}

// ── Clients ───────────────────────────────────────────────
export const clientsApi = {
  list: (params = {}) => {
    const q = new URLSearchParams()
    const cid = getCompanyId()
    if (cid) q.set('company_id', cid)
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, v))
    return request(`/clients?${q}`)
  },
  get: (id) => request(`/clients/${id}`),
  create: (body) => request('/clients', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/clients/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
}

// ── Upload ────────────────────────────────────────────────
export const uploadApi = {
  upload: async (file, companyId) => {
    const form = new FormData()
    form.append('file', file)
    form.append('company_id', companyId || getCompanyId())
    const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.json()
  }
}

// ── Analytics ─────────────────────────────────────────────
export const analyticsApi = {
  dashboard: () => {
    const cid = getCompanyId()
    return request(`/analytics/dashboard${cid ? `?company_id=${cid}` : ''}`)
  },
  spending: () => {
    const cid = getCompanyId()
    return request(`/analytics/spending${cid ? `?company_id=${cid}` : ''}`)
  },
  trends: () => {
    const cid = getCompanyId()
    return request(`/analytics/trends${cid ? `?company_id=${cid}` : ''}`)
  },
  paymentTiming: () => {
    const cid = getCompanyId()
    return request(`/analytics/payment-timing${cid ? `?company_id=${cid}` : ''}`)
  },
}

// ── Query (AI chat) ───────────────────────────────────────
export const queryApi = {
  ask: (question) => request('/query', {
    method: 'POST',
    body: JSON.stringify({ question, company_id: getCompanyId() }),
  })
}