const BASE = '/api/v1'

export function getCompanyId() {
  return localStorage.getItem('company_id') || ''
}

async function request(path, options = {}) {
  const { headers: optHeaders, ...rest } = options
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...optHeaders },
  })
  if (!res.ok) {
    const ct = res.headers.get('content-type') || ''
    if (ct.includes('application/pdf') || ct.includes('application/octet-stream')) {
      throw new Error(`HTTP ${res.status}`)
    }
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ')
      : (err.detail || err.error || `HTTP ${res.status}`)
    throw new Error(detail)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/pdf') || ct.includes('application/octet-stream')) {
    return res.blob()
  }
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

// ── Invoices ─────────────────────────────────────────────────────────────────

export const invoicesApi = {
  list: ({ page = 1, limit = 50, status, search, invoice_type } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    if (status && status !== 'all') q.set('status', status)
    if (search?.trim()) q.set('search', search.trim())
    if (invoice_type) q.set('invoice_type', invoice_type)
    return request(`/invoices/?${q}`)
  },
  get:          (id)       => request(`/invoices/${id}`),
  create:       (body)     => request('/invoices/', { method: 'POST', body: JSON.stringify(body) }),
  update:       (id, body) => request(`/invoices/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete:       (id)       => request(`/invoices/${id}`, { method: 'DELETE' }),
  transition:   (id, newStatus) => request(`/invoices/${id}/transition`, {
    method: 'POST',
    body: JSON.stringify({ new_status: newStatus }),
  }),
  recordPayment: (id, data) => request(`/invoices/${id}/payments`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getPayments:        (id) => request(`/invoices/${id}/payments`),
  getLineItems:       (id) => request(`/invoices/${id}/line-items`),
  getPdf:             (id) => request(`/invoices/${id}/pdf`),
  getComplianceFlags: (id) => request(`/invoices/${id}/compliance-flags`),
  creditNote: (id, { amount, reason }) => request(`/invoices/${id}/credit-note`, {
    method: 'POST',
    body: JSON.stringify({ amount, reason }),
  }),
  refund: (id, { payment_id, amount }) => request(`/invoices/${id}/refund`, {
    method: 'POST',
    body: JSON.stringify({ payment_id, amount }),
  }),
}

// ── Vendors ───────────────────────────────────────────────────────────────────

export const vendorsApi = {
  list: ({ page = 1, limit = 50, search } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    if (search?.trim()) q.set('search', search.trim())
    return request(`/vendors/?${q}`)
  },
  get:    (id)       => request(`/vendors/${id}`),
  create: (body)     => request('/vendors/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/vendors/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id)       => request(`/vendors/${id}`, { method: 'DELETE' }),
}

// ── Clients ───────────────────────────────────────────────────────────────────

export const clientsApi = {
  list: ({ page = 1, limit = 50, search } = {}) => {
    const q = new URLSearchParams()
    q.set('company_id', getCompanyId())
    q.set('limit', limit)
    q.set('offset', (page - 1) * limit)
    if (search?.trim()) q.set('search', search.trim())
    return request(`/clients/?${q}`)
  },
  get:    (id)       => request(`/clients/${id}`),
  create: (body)     => request('/clients/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => request(`/clients/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id)       => request(`/clients/${id}`, { method: 'DELETE' }),
  getLatestAddress(clientId) {
    return request(`/clients/${clientId}/latest-address`)
  },
}

// ── Upload ────────────────────────────────────────────────────────────────────

export const uploadApi = {
  upload: async (file, invoiceType = 'payable') => {
    const form = new FormData()
    form.append('file', file)
    form.append('invoice_type', invoiceType)
    const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  },
  uploadBatch: async (files, invoiceType = 'payable') => {
    const form = new FormData()
    const list = Array.isArray(files) ? files : Array.from(files)
    list.forEach(f => form.append('files', f))
    form.append('invoice_type', invoiceType)
    const res = await fetch(`${BASE}/upload/batch`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Batch upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  },
}

// ── Documents ─────────────────────────────────────────────────────────────────

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
  list:   ()        => request('/documents'),
  delete: (id)      => request(`/documents/${id}`, { method: 'DELETE' }),
  update: (id, body)=> request(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export const analyticsApi = {
  dashboard: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/analytics/dashboard?${q}`)
  },
  spending: (months = 6) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), months })
    return request(`/analytics/spending?${q}`)
  },
  revenue: (months = 6) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), months })
    return request(`/analytics/revenue?${q}`)
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
  pageMetrics: (invoiceType) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), invoice_type: invoiceType })
    return request(`/analytics/page-metrics?${q}`)
  },
}

// ── Notifications ─────────────────────────────────────────────────────────────

export const notificationsApi = {
  list: (unreadOnly = false, limit = 20) => {
    const q = new URLSearchParams({ company_id: getCompanyId(), limit })
    if (unreadOnly) q.set('unread_only', 'true')
    return request(`/notifications?${q}`)
  },
  markRead:    (id) => request(`/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: ()   => request(`/notifications/read-all`,  { method: 'POST' }),
}

// ── Query ─────────────────────────────────────────────────────────────────────

export const queryApi = {
  ask: (question) => request('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  }),
}

// ── Settings ──────────────────────────────────────────────────────────────────

export const settingsApi = {
  getBranding: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/settings/branding?${q}`)
  },
  updateBranding: (data) => request('/settings/branding', {
    method: 'PATCH',
    body: JSON.stringify({ ...data, company_id: getCompanyId() }),
  }),
  uploadLogo: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/settings/branding/logo?company_id=${encodeURIComponent(getCompanyId())}`, {
      method: 'POST',
      body: form,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(err.detail || err.error || `HTTP ${res.status}`)
    }
    return res.json()
  },
  get: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/settings?${q}`)
  },
  update: (data) => request('/settings', {
    method: 'PATCH',
    body: JSON.stringify({ ...data, company_id: getCompanyId() }),
  }),
  taxRates: () => request('/settings/tax-rates'),
  pipeline: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/settings/pipeline?${q}`)
  },
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  runOverdueCheck: () => request('/admin/run-overdue-check', {
    method: 'POST',
    body: JSON.stringify({ company_id: getCompanyId() }),
  }),
  runComplianceCheck: () => request('/admin/run-compliance-check', {
    method: 'POST',
    body: JSON.stringify({ company_id: getCompanyId() }),
  }),
}

// ── Compliance ────────────────────────────────────────────────────────────────

export const complianceApi = {
  summary: () => {
    const q = new URLSearchParams({ company_id: getCompanyId() })
    return request(`/compliance/summary?${q}`)
  },
}