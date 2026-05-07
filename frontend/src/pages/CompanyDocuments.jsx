import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Upload, FileText, CheckCircle, AlertCircle, X, Loader2,
  Trash2, Edit3, Globe, Tag, BookOpen, AlertTriangle,
  ChevronDown, Eye
} from 'lucide-react'
import { documentsApi } from '../lib/api'
import { formatDate, cn } from '../lib/utils'

// ── Constants ────────────────────────────────────────────────────────────────

const DOCUMENT_TYPES = [
  { value: 'tax_regulation',    label: 'Tax Regulation' },
  { value: 'compliance_guide',  label: 'Compliance Guide' },
  { value: 'vat_rules',         label: 'VAT Rules' },
  { value: 'customs',           label: 'Customs & Tariff' },
  { value: 'company_policy',    label: 'Company Policy' },
  { value: 'general',           label: 'General' },
]

const COUNTRIES = [
  { value: '',   label: 'No country' },
  { value: 'US', label: 'United States' },
  { value: 'TR', label: 'Turkey' },
  { value: 'SA', label: 'Saudi Arabia' },
  { value: 'AE', label: 'UAE' },
  { value: 'GB', label: 'United Kingdom' },
  { value: 'DE', label: 'Germany' },
  { value: 'FR', label: 'France' },
]

const typeLabel = (val) => DOCUMENT_TYPES.find(t => t.value === val)?.label || val
const countryLabel = (val) => COUNTRIES.find(c => c.value === val)?.label || val || '—'

// ── Toast notification ───────────────────────────────────────────────────────

function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [onClose])

  return (
    <div className={cn(
      'fixed bottom-6 right-6 z-[100] flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border animate-fade-up',
      type === 'success' && 'border-emerald-200 dark:border-emerald-900',
      type === 'error' && 'border-red-200 dark:border-red-900',
      type === 'warning' && 'border-amber-200 dark:border-amber-900',
    )} style={{ background: 'var(--bg-card)' }}>
      {type === 'success' && <CheckCircle size={16} color="#22C55E" />}
      {type === 'error' && <AlertCircle size={16} color="#EF4444" />}
      {type === 'warning' && <AlertTriangle size={16} color="#F59E0B" />}
      <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{message}</p>
      <button onClick={onClose} className="btn-ghost p-1 rounded-lg">
        <X size={12} />
      </button>
    </div>
  )
}

// ── Confirm dialog ───────────────────────────────────────────────────────────

function ConfirmDialog({ title, message, onConfirm, onCancel, confirmLabel = 'Delete', danger = true }) {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center">
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onCancel} />
      <div className="relative w-full max-w-sm rounded-2xl border p-6 shadow-xl animate-fade-up"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
        <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{title}</h3>
        <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>{message}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="btn-secondary text-sm">Cancel</button>
          <button
            onClick={onConfirm}
            className={cn('text-sm px-4 py-2 rounded-xl font-medium', danger ? 'bg-red-500 text-white hover:bg-red-600' : 'btn-primary')}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Edit modal ───────────────────────────────────────────────────────────────

function EditModal({ doc, onSave, onClose }) {
  const [docType, setDocType] = useState(doc.document_type || 'general')
  const [country, setCountry] = useState(doc.country || '')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(doc.document_id, { document_type: docType, country: country || null })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center">
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl border p-6 shadow-xl animate-fade-up"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
        <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
          Edit Document Tags
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
          {doc.document_name}
        </p>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>
              Document Type
            </label>
            <div className="relative">
              <select
                value={docType}
                onChange={e => setDocType(e.target.value)}
                className="input w-full appearance-none pr-8"
              >
                {DOCUMENT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--text-muted)' }} />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>
              Country
            </label>
            <div className="relative">
              <select
                value={country}
                onChange={e => setCountry(e.target.value)}
                className="input w-full appearance-none pr-8"
              >
                {COUNTRIES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--text-muted)' }} />
            </div>
          </div>
        </div>

        <div className="flex gap-2 justify-end mt-6">
          <button onClick={onClose} className="btn-secondary text-sm">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary text-sm">
            {saving ? <Loader2 size={14} className="animate-spin" /> : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Document card ────────────────────────────────────────────────────────────

function DocumentCard({ doc, onEdit, onDelete }) {
  return (
    <div className="card p-4 flex items-start gap-4 group">
      <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'var(--bg-secondary)' }}>
        <BookOpen size={18} style={{ color: 'var(--text-secondary)' }} />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {doc.document_name}
        </p>
        <div className="flex flex-wrap gap-2 mt-1.5">
          <span className="text-xs px-2 py-0.5 rounded-full border font-medium"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
            <Tag size={10} className="inline mr-1" />
            {typeLabel(doc.document_type)}
          </span>
          {doc.country && (
            <span className="text-xs px-2 py-0.5 rounded-full border"
              style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
              <Globe size={10} className="inline mr-1" />
              {countryLabel(doc.country)}
            </span>
          )}
          <span className="text-xs px-2 py-0.5 rounded-full border"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
            {doc.chunk_count} chunks
          </span>
          {doc.last_page && (
            <span className="text-xs px-2 py-0.5 rounded-full border"
              style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
              {doc.last_page} pages
            </span>
          )}
          {doc.version > 1 && (
            <span className="text-xs px-2 py-0.5 rounded-full border"
              style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
              v{doc.version}
            </span>
          )}
        </div>
        <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
          Uploaded {formatDate(doc.uploaded_at)}
        </p>
      </div>

      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onEdit(doc)}
          className="btn-ghost p-2 rounded-lg"
          title="Edit tags"
        >
          <Edit3 size={14} />
        </button>
        <button
          onClick={() => onDelete(doc)}
          className="btn-ghost p-2 rounded-lg hover:text-red-500"
          title="Delete document"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function CompanyDocuments() {
  const fileRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState(null)
  const [docType, setDocType] = useState('tax_regulation')
  const [country, setCountry] = useState('US')
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)

  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [toast, setToast] = useState(null)
  const [editDoc, setEditDoc] = useState(null)
  const [deleteDoc, setDeleteDoc] = useState(null)

  // ── Load documents ──────────────────────────────────────────────────────
  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const res = await documentsApi.list()
      setDocuments(res.documents || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchDocuments() }, [fetchDocuments])

  // ── File handling ───────────────────────────────────────────────────────
  const handleFile = (f) => {
    if (!f) return
    setUploadResult(null)

    // Only PDF allowed
    const ext = f.name.split('.').pop().toLowerCase()
    if (ext !== 'pdf') {
      setToast({ message: 'Only PDF files are supported for regulation documents.', type: 'error' })
      return
    }

    // Size check — 50MB max
    if (f.size > 50 * 1024 * 1024) {
      setToast({ message: 'File too large. Maximum size is 50 MB.', type: 'error' })
      return
    }

    setFile(f)
    setError(null)
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }, [])

  // ── Upload ──────────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    setUploadResult(null)

    try {
      const res = await documentsApi.upload(file, docType, country || null)
      setUploadResult(res.data || res)

      // Check classification warning
      const classification = res.data?.classification || res.classification
      if (classification === 'invoice') {
        setToast({
          message: 'This document looks like an invoice, not a regulation. You can re-tag it using the edit button.',
          type: 'warning',
        })
      } else {
        setToast({ message: `Document processed: ${res.data?.chunk_count || res.chunk_count} chunks embedded.`, type: 'success' })
      }

      // Refresh list
      fetchDocuments()

      // Reset upload form
      setFile(null)
    } catch (e) {
      setToast({ message: e.message, type: 'error' })
    } finally {
      setUploading(false)
    }
  }

  const resetUpload = () => {
    setFile(null)
    setUploadResult(null)
    setError(null)
  }

  // ── Edit ────────────────────────────────────────────────────────────────
  const handleEditSave = async (documentId, updates) => {
    try {
      await documentsApi.update(documentId, updates)
      setToast({ message: 'Document tags updated.', type: 'success' })
      setEditDoc(null)
      fetchDocuments()
    } catch (e) {
      setToast({ message: e.message, type: 'error' })
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────
  const handleDeleteConfirm = async () => {
    if (!deleteDoc) return
    try {
      await documentsApi.delete(deleteDoc.document_id)
      setToast({ message: `"${deleteDoc.document_name}" deleted.`, type: 'success' })
      setDeleteDoc(null)
      fetchDocuments()
    } catch (e) {
      setToast({ message: e.message, type: 'error' })
    }
  }

  return (
    <div className="p-6 max-w-4xl space-y-6 animate-fade-up">
      {/* Header */}
      <div>
        <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Company Documents
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Upload regulation and compliance PDFs. The AI assistant uses these to answer compliance questions about your invoices.
        </p>
      </div>

      {/* Upload section */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Upload Regulation Document
          </h2>
        </div>

        <div className="p-5 space-y-4">
          {/* Metadata selectors */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>
                Document Type
              </label>
              <div className="relative">
                <select
                  value={docType}
                  onChange={e => setDocType(e.target.value)}
                  className="input w-full appearance-none pr-8"
                  disabled={uploading}
                >
                  {DOCUMENT_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-muted)' }} />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--text-secondary)' }}>
                Country
              </label>
              <div className="relative">
                <select
                  value={country}
                  onChange={e => setCountry(e.target.value)}
                  className="input w-full appearance-none pr-8"
                  disabled={uploading}
                >
                  {COUNTRIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                  style={{ color: 'var(--text-muted)' }} />
              </div>
            </div>
          </div>

          {/* Drop zone */}
          <div
            className={cn(
              'rounded-2xl flex flex-col items-center justify-center p-10 cursor-pointer border-2 border-dashed transition-all duration-200',
              dragging && 'scale-[1.01]',
            )}
            style={{
              borderColor: dragging ? 'var(--accent)' : file ? 'var(--accent)' : 'var(--border)',
              background: dragging ? 'var(--accent-light)' : 'var(--bg-secondary)',
            }}
            onClick={() => !uploading && fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={e => handleFile(e.target.files[0])}
            />

            {file ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: 'var(--accent-light)' }}>
                  <FileText size={20} style={{ color: 'var(--accent)' }} />
                </div>
                <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{file.name}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {(file.size / 1024).toFixed(1)} KB
                </p>
                {!uploading && (
                  <button
                    onClick={e => { e.stopPropagation(); resetUpload() }}
                    className="text-xs flex items-center gap-1 mt-1"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <X size={12} /> Remove
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-center">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: 'var(--bg-card)' }}>
                  <Upload size={20} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
                </div>
                <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                  Drop a PDF here or click to browse
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  PDF only · Max 100 pages · 50 MB limit
                </p>
              </div>
            )}
          </div>

          {/* Upload button */}
          {file && !uploading && (
            <div className="flex justify-end">
              <button onClick={handleUpload} className="btn-primary">
                <Upload size={15} />
                Upload & Embed
              </button>
            </div>
          )}

          {/* Uploading indicator */}
          {uploading && (
            <div className="flex items-center gap-3 p-4 rounded-xl" style={{ background: 'var(--bg-secondary)' }}>
              <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  Processing document...
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  Extracting text, detecting sections, generating embeddings
                </p>
              </div>
            </div>
          )}

          {/* Upload result */}
          {uploadResult && (
            <div className="flex items-center gap-3 p-4 rounded-xl border border-emerald-200 dark:border-emerald-900"
              style={{ background: 'var(--bg-card)' }}>
              <CheckCircle size={16} color="#22C55E" />
              <div className="flex-1">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  Document embedded successfully
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {uploadResult.chunk_count} chunks from {uploadResult.page_count} pages
                  {uploadResult.version > 1 && ` · Version ${uploadResult.version}`}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Document list */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3.5 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Uploaded Documents
          </h2>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
            {documents.length}
          </span>
        </div>

        <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-8 text-center">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
                style={{ background: 'var(--bg-secondary)' }}>
                <BookOpen size={22} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
              </div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                No documents uploaded yet
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                Upload regulation PDFs above to enable compliance queries
              </p>
            </div>
          ) : (
            documents.map(doc => (
              <DocumentCard
                key={doc.document_id}
                doc={doc}
                onEdit={setEditDoc}
                onDelete={setDeleteDoc}
              />
            ))
          )}
        </div>
      </div>

      {/* Modals */}
      {editDoc && (
        <EditModal
          doc={editDoc}
          onSave={handleEditSave}
          onClose={() => setEditDoc(null)}
        />
      )}

      {deleteDoc && (
        <ConfirmDialog
          title="Delete Document"
          message={`Delete "${deleteDoc.document_name}" and all its embeddings? This cannot be undone.`}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteDoc(null)}
        />
      )}

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  )
}