const BASE = '/api/v1'

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
    // FastAPI 422 returns detail as an array of validation errors
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ')
      : (err.detail || err.error || `HTTP ${res.status}`)
    throw new Error(detail)
  }
  return res.json()
}

// ── Invoices ──────────────────────────────────────────────
// Backend: GET /api/v1/invoices/
//   params: company_id (required UUID), limit (1-200, default 50), offset (default 0)
export const invoicesApi = {
  list: ({ page = 1, limit = 50, status, search } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)   // backend uses offset, not page
    if (status && status !== 'all') q.set('status', status)
    if (search?.trim()) q.set('search', search.trim())
    return request(`/invoices/?${q}`)      // trailing slash matches backend registration
  },

  get: (id) => request(`/invoices/${id}`),

  create: (body) => request('/invoices/', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  update: (id, body) => request(`/invoices/${id}`, {
    method: 'PATCH',                       // backend uses PATCH not PUT
    body: JSON.stringify(body),
  }),

  delete: (id) => request(`/invoices/${id}`, { method: 'DELETE' }),

  // Not built yet — will 404 until backend adds this route
  transition: (id, status) => request(`/invoices/${id}/transition`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  }),

  // Backend: GET /api/v1/invoices/{invoice_id}/payments
  getPayments: (id) => request(`/invoices/${id}/payments`),

  // Backend: GET /api/v1/invoices/{invoice_id}/line-items
  getLineItems: (id) => request(`/invoices/${id}/line-items`),

  // Backend: GET /api/v1/invoices/{invoice_id}/raw-document  ← NOT /raw
  getRaw: (id) => request(`/invoices/${id}/raw-document`),
}

// ── Vendors ───────────────────────────────────────────────
// Backend: GET /api/v1/vendors/
//   params: company_id (required UUID), limit, offset
export const vendorsApi = {
  list: ({ page = 1, limit = 50 } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    return request(`/vendors/?${q}`)
  },

  get: (id) => request(`/vendors/${id}`),

  create: (body) => request('/vendors/', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  update: (id, body) => request(`/vendors/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),

  delete: (id) => request(`/vendors/${id}`, { method: 'DELETE' }),
}

// ── Clients ───────────────────────────────────────────────
// Backend: GET /api/v1/clients/
//   params: company_id (required UUID), limit, offset
export const clientsApi = {
  list: ({ page = 1, limit = 50 } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    return request(`/clients/?${q}`)
  },

  get: (id) => request(`/clients/${id}`),

  create: (body) => request('/clients/', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  update: (id, body) => request(`/clients/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),

  delete: (id) => request(`/clients/${id}`, { method: 'DELETE' }),
}

// ── Upload ────────────────────────────────────────────────
// Backend: POST /api/v1/upload
//   multipart/form-data, field name: "file"
//   company_id resolved by backend internally — do NOT send it
export const uploadApi = {
  upload: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  }
}

// ── Analytics ─────────────────────────────────────────────
// These endpoints do not exist yet (Phase 4)
export const analyticsApi = {
  dashboard: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/dashboard?${q}`)
  },
  spending: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/spending?${q}`)
  },
  trends: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/trends?${q}`)
  },
  paymentTiming: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/payment-timing?${q}`)
  },
}

// ── Query (AI chat) ───────────────────────────────────────
// Does not exist yet (Phase 3)
export const queryApi = {
  ask: (question) => request('/query', {
    method: 'POST',
    body: JSON.stringify({ question, company_id: getCompanyId() }),
  })
}