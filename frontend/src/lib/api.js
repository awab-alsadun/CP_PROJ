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
  create: (body) => request('/invoices/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/invoices/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id) => request(`/invoices/${id}`, { method: 'DELETE' }),
  transition: (id, newStatus) => request(`/invoices/${id}/transition`, {
    method: 'POST',
    body: JSON.stringify({ new_status: newStatus }),
  }),
  recordPayment: (id, data) => request(`/invoices/${id}/payments`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getPayments:  (id) => request(`/invoices/${id}/payments`),
  getLineItems: (id) => request(`/invoices/${id}/line-items`),
  getRaw:       (id) => request(`/invoices/${id}/raw`),
}

export const vendorsApi = {
  list: ({ page = 1, limit = 50 } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    return request(`/vendors/?${q}`)
  },
  get: (id) => request(`/vendors/${id}`),
  create: (body) => request('/vendors/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/vendors/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id) => request(`/vendors/${id}`, { method: 'DELETE' }),
}

export const clientsApi = {
  list: ({ page = 1, limit = 50 } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    return request(`/clients/?${q}`)
  },
  get: (id) => request(`/clients/${id}`),
  create: (body) => request('/clients/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/clients/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id) => request(`/clients/${id}`, { method: 'DELETE' }),
}

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

export const documentsApi = {
  upload: async (file, documentType = 'general', country = null) => {
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', documentType)
    if (country) form.append('country', country)
    const res = await fetch(`${BASE}/documents/upload`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  },
  list: () => request('/documents'),
  delete: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  update: (id, body) => request(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
}

export const analyticsApi = {
  dashboard: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/dashboard?${q}`)
  },
  spending: (months = 6) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), months })
    return request(`/analytics/spending?${q}`)
  },
  trends: (months = 12) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), months })
    return request(`/analytics/trends?${q}`)
  },
  paymentTiming: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/payment-timing?${q}`)
  },
  overdue: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/overdue?${q}`)
  },
  systemStats: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/system-stats?${q}`)
  },
}

export const notificationsApi = {
  list: (unreadOnly = false, limit = 20) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), limit })
    if (unreadOnly) q.set('unread_only', 'true')
    return request(`/notifications?${q}`)
  },
  markRead: (id) => request(`/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () => request(`/notifications/read-all`, { method: 'POST' }),
}

export const queryApi = {
  ask: (question) => request('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}