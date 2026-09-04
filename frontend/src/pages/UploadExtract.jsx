import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Upload, FileText, CheckCircle, AlertCircle, X, Loader2, FolderOpen } from 'lucide-react'
import { uploadApi, invoicesApi } from '../lib/api'

export default function UploadExtract() {
  const { t }     = useTranslation()
  const navigate  = useNavigate()
  const fileRef   = useRef(null)
  const folderRef = useRef(null)

  // ── single upload state ──────────────────────────────────────────────────────
  const [dragging,  setDragging]  = useState(false)
  const [file,      setFile]      = useState(null)
  const [uploading, setUploading] = useState(false)
  const [result,    setResult]    = useState(null)
  const [flags,     setFlags]     = useState([])
  const [error,     setError]     = useState(null)

  // ── batch state ──────────────────────────────────────────────────────────────
  const [batchActive,   setBatchActive]   = useState(false)
  const [batchTotal,    setBatchTotal]    = useState(0)
  const [batchDone,     setBatchDone]     = useState(0)
  const [batchSuccess,  setBatchSuccess]  = useState(0)
  const [batchFailures, setBatchFailures] = useState([])
  const [batchToast,    setBatchToast]    = useState(null)

  const cancelRef = useRef(false)
  const busy      = uploading || batchActive
  const batchPct  = batchTotal > 0 ? Math.round((batchDone / batchTotal) * 100) : 0

  // ── single upload helpers ────────────────────────────────────────────────────
  const handleFile = (f) => {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['pdf', 'png', 'jpg', 'jpeg', 'tiff'].includes(ext)) {
      setError(t('upload.unsupportedFile'))
      return
    }
    setFile(f)
    setResult(null)
    setFlags([])
    setError(null)
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }, [])

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    setFlags([])
    try {
      const res = await uploadApi.upload(file, 'payable')
      setResult(res)
      const invoiceId = res?.data?.invoice_id
      if (invoiceId) {
        try {
          const f = await invoicesApi.getComplianceFlags(invoiceId)
          setFlags(f || [])
        } catch (_) {
          setFlags([])
        }
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const reset = () => {
    setFile(null)
    setResult(null)
    setFlags([])
    setError(null)
    setUploading(false)
  }

  // ── batch: sequential per-file loop ─────────────────────────────────────────
  const handleFolderChange = async (e) => {
    const allFiles = Array.from(e.target.files || [])
    e.target.value = ''

    const pdfs = allFiles.filter(f => f.name.toLowerCase().endsWith('.pdf'))

    if (pdfs.length === 0) {
      setBatchToast({ message: t('upload.noPdfsFound'), type: 'error' })
      setTimeout(() => setBatchToast(null), 4000)
      return
    }

    cancelRef.current = false
    setBatchActive(true)
    setBatchTotal(pdfs.length)
    setBatchDone(0)
    setBatchSuccess(0)
    setBatchFailures([])
    setBatchToast(null)

    let successCount = 0
    let doneCount    = 0
    const failures   = []

    for (const pdf of pdfs) {
      if (cancelRef.current) {
        setBatchToast({
          message: t('upload.cancelledAt', { done: doneCount, total: pdfs.length, success: successCount }),
          type: 'warning',
        })
        setTimeout(() => setBatchToast(null), 5000)
        break
      }

      try {
        await uploadApi.upload(pdf, 'payable')
        successCount++
      } catch (err) {
        failures.push({ filename: pdf.name, error: err.message || t('upload.unknownError') })
      }

      doneCount++
      setBatchDone(doneCount)
      setBatchSuccess(successCount)
      setBatchFailures([...failures])
    }

    if (!cancelRef.current) {
      setBatchToast({
        message: t('upload.ingestedSuccess', { success: successCount, total: pdfs.length }),
        type: failures.length === 0 ? 'success' : 'warning',
      })
      setTimeout(() => setBatchToast(null), 5000)
    }

    setBatchActive(false)
  }

  // ── render ───────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-3xl space-y-5 animate-fade-up">
      <div>
        <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('upload.title')}
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {t('upload.subtitle')}
        </p>
      </div>

      {/* Drop zone */}
      {!result && (
        <div
          className={`card rounded-2xl flex flex-col items-center justify-center p-12 cursor-pointer border-2 border-dashed transition-all duration-200 ${dragging ? 'scale-[1.01]' : ''}`}
          style={{
            borderColor: dragging ? 'var(--accent)' : file ? 'var(--accent)' : 'var(--border)',
            background:  dragging ? 'var(--accent-light)' : 'var(--bg-card)',
          }}
          onClick={() => !busy && fileRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tiff"
            className="hidden"
            onChange={e => handleFile(e.target.files[0])}
          />
          {file ? (
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                style={{ background: 'var(--accent-light)' }}>
                <FileText size={22} style={{ color: 'var(--accent)' }} />
              </div>
              <div className="text-center">
                <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{file.name}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
              {!uploading && (
                <button
                  onClick={e => { e.stopPropagation(); reset() }}
                  className="text-xs flex items-center gap-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <X size={12} /> {t('upload.remove')}
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                style={{ background: 'var(--bg-secondary)' }}>
                <Upload size={22} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
              </div>
              <div>
                <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                  {t('upload.dropHint')}
                </p>
                <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                  {t('upload.supportsFormats')}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* uploading spinner */}
      {uploading && (
        <div className="card p-4 flex items-center gap-3">
          <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{t('upload.processingInvoice')}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card p-4 flex items-center gap-3" style={{ borderColor: '#FECACA' }}>
          <AlertCircle size={16} color="#EF4444" />
          <p className="text-sm" style={{ color: '#EF4444' }}>{error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-3 animate-fade-up">

          {/* Success / Duplicate banner */}
          {result.data?.status === 'duplicate' ? (
            <div className="card p-4 flex items-center gap-3" style={{ borderColor: '#FDE68A' }}>
              <AlertCircle size={16} color="#F59E0B" />
              <div className="flex-1">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {t('upload.duplicateDetected')}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {t('upload.duplicateExists', { number: result.data?.invoice_number })}
                </p>
              </div>
            </div>
          ) : (
            <div className="card p-4 flex items-center gap-3" style={{ borderColor: '#BBF7D0' }}>
              <CheckCircle size={16} color="#22C55E" />
              <div className="flex-1">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {t('upload.extractedSuccess')}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {t('upload.storedAs', { number: result.data?.invoice_number || t('upload.newInvoice') })}
                </p>
              </div>
            </div>
          )}

          {/* Compliance flags */}
          {flags.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
                <p className="text-xs font-semibold tracking-wide" style={{ color: 'var(--text-muted)' }}>
                  {t('upload.complianceFlags')}
                </p>
              </div>
              <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {[...new Map(flags.map(f => [f.flag_type, f])).values()].map((f, i) => (                  <div key={i} className="flex items-start gap-3 px-4 py-3">
                    <AlertCircle
                      size={14}
                      className="flex-shrink-0 mt-0.5"
                      color={f.severity === 'high' ? '#EF4444' : f.severity === 'medium' ? '#F59E0B' : '#6B7280'}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                        {f.flag_type.replace(/_/g, ' ')}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{f.reason}</p>
                    </div>
                    <span className="text-xs px-2 py-0.5 rounded-full flex-shrink-0" style={{
                      background: f.severity === 'high'   ? '#FEE2E2'
                                : f.severity === 'medium' ? '#FEF3C7'
                                : 'var(--bg-secondary)',
                      color:      f.severity === 'high'   ? '#EF4444'
                                : f.severity === 'medium' ? '#F59E0B'
                                : 'var(--text-muted)',
                    }}>
                      {f.severity}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={reset} className="btn-secondary">{t('upload.uploadAnother')}</button>
            {result.data?.invoice_id && result.data?.status !== 'duplicate' && (
              <button
                onClick={() => navigate(`/payables/${result.data.invoice_id}`)}
                className="btn-primary"
              >
                {t('upload.viewInvoice')}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!result && (
        <div className="flex items-center gap-3 flex-wrap">
          {file && !uploading && (
            <button onClick={handleUpload} disabled={busy} className="btn-primary disabled:opacity-50">
              <Upload size={15} /> {t('upload.extractInvoice')}
            </button>
          )}

          <button
            onClick={() => folderRef.current?.click()}
            disabled={busy}
            className="btn-secondary disabled:opacity-50"
          >
            {batchActive
              ? <><Loader2 size={14} className="animate-spin" /> {t('upload.ingesting')}</>
              : <><FolderOpen size={14} /> {t('upload.ingestFolder')}</>
            }
          </button>

          {batchActive && (
            <button
              onClick={() => { cancelRef.current = true }}
              className="btn-ghost text-xs h-8 px-3"
              style={{ color: '#EF4444' }}
            >
              <X size={13} /> {t('upload.cancel')}
            </button>
          )}

          <input
            ref={folderRef}
            type="file"
            webkitdirectory=""
            directory=""
            multiple
            className="hidden"
            onChange={handleFolderChange}
          />
        </div>
      )}

      {/* Batch progress */}
      {batchActive && batchTotal > 0 && (
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {t('upload.ingestingFolder')}
            </h2>
            <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              {batchDone} / {batchTotal}
            </span>
          </div>
          <div className="w-full rounded-full overflow-hidden" style={{ height: 6, background: 'var(--border)' }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${batchPct}%`, background: 'var(--accent)' }}
            />
          </div>
          <div className="flex gap-4 text-xs">
            <span style={{ color: '#22C55E' }}>✓ {batchSuccess} {t('upload.succeeded')}</span>
            {batchFailures.length > 0 && (
              <span style={{ color: '#EF4444' }}>✗ {batchFailures.length} {t('upload.failed')}</span>
            )}
            <span style={{ color: 'var(--text-muted)' }}>{batchPct}%</span>
          </div>
        </div>
      )}

      {/* Batch toast */}
      {batchToast && (
        <div
          className="card p-4 flex items-center gap-3"
          style={{
            borderColor: batchToast.type === 'error'   ? '#FECACA'
                       : batchToast.type === 'warning' ? '#FDE68A'
                       : '#BBF7D0',
          }}
        >
          {batchToast.type === 'success'
            ? <CheckCircle size={16} color="#22C55E" />
            : <AlertCircle size={16} color={batchToast.type === 'error' ? '#EF4444' : '#F59E0B'} />
          }
          <p className="text-sm flex-1"
            style={{
              color: batchToast.type === 'error'   ? '#EF4444'
                   : batchToast.type === 'warning' ? '#F59E0B'
                   : '#16A34A',
            }}>
            {batchToast.message}
          </p>
          <button onClick={() => setBatchToast(null)} className="opacity-50 hover:opacity-100">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Failed files list */}
      {batchFailures.length > 0 && !batchActive && (
        <div className="card overflow-hidden">
          <div className="px-5 py-3.5 border-b flex items-center justify-between"
            style={{ borderColor: 'var(--border)' }}>
            <h2 className="text-sm font-semibold" style={{ color: '#EF4444' }}>
              {t('upload.failedCount', { count: batchFailures.length })}
            </h2>
            <button
              onClick={() => setBatchFailures([])}
              className="btn-ghost p-1.5 rounded-lg flex items-center gap-1 text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              <X size={13} /> {t('upload.dismiss')}
            </button>
          </div>
          <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {batchFailures.map((f, i) => (
              <div key={i} className="flex items-start gap-3 px-5 py-3">
                <AlertCircle size={14} color="#EF4444" className="flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {f.filename}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{f.error}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}