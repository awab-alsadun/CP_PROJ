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
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ')
      : (err.detail || err.error || `HTTP ${res.status}`)
    throw new Error(detail)
  }
  return res.json()
}

// ── Invoices ──────────────────────────────────────────────
export const invoicesApi = {
  list: ({ page = 1, limit = 50, status, search } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    if (status && status !== 'all') q.set('status', status)
    if (search?.trim()) q.set('search', search.trim())
    return request(`/invoices/?${q}`)
  },

  get: (id) => request(`/invoices/${id}`),

  create: (body) => request('/invoices/', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  update: (id, body) => request(`/invoices/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),

  delete: (id) => request(`/invoices/${id}`, { method: 'DELETE' }),

  transition: (id, status) => request(`/invoices/${id}/transition`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  }),

  getPayments: (id) => request(`/invoices/${id}/payments`),
  getLineItems: (id) => request(`/invoices/${id}/line-items`),
  getRaw: (id) => request(`/invoices/${id}/raw-document`),
}

// ── Vendors ───────────────────────────────────────────────
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

// ── Documents (Regulations / Compliance) ──────────────────
export const documentsApi = {
  upload: async (file, documentType = 'general', country = null) => {
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', documentType)
    if (country) form.append('country', country)

    const res = await fetch(`${BASE}/documents/upload`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  },

  list: () => request('/documents'),

  delete: (documentId) => request(`/documents/${documentId}`, {
    method: 'DELETE',
  }),

  update: (documentId, body) => request(`/documents/${documentId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),
}

// ── Analytics ─────────────────────────────────────────────
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
export const queryApi = {
  ask: (question) => request('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}