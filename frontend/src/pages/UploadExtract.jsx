import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, FileText, CheckCircle, AlertCircle, X, Loader2, FolderOpen } from 'lucide-react'
import { uploadApi, getCompanyId } from '../lib/api'
import { ConfidenceBar } from '../components/ui'

const STAGES = [
  { key: 'ocr',        label: 'OCR Extraction',  desc: 'Reading document text'        },
  { key: 'parsing',    label: 'LLM Parsing',      desc: 'Extracting structured data'   },
  { key: 'validating', label: 'Validation',       desc: 'Checking data integrity'      },
  { key: 'storing',    label: 'Storing',          desc: 'Saving to database'           },
  { key: 'embedding',  label: 'Embedding',        desc: 'Generating vector embeddings' },
]

function StageRow({ stage, status }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0">
        {status === 'done'    && <CheckCircle size={16} color="#22C55E" />}
        {status === 'active'  && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />}
        {status === 'error'   && <AlertCircle size={16} color="#EF4444" />}
        {status === 'pending' && <div className="w-4 h-4 rounded-full border-2" style={{ borderColor: 'var(--border)' }} />}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium" style={{
          color: status === 'active' ? 'var(--text-primary)'
               : status === 'done'   ? '#22C55E'
               : status === 'error'  ? '#EF4444'
               : 'var(--text-muted)',
        }}>
          {stage.label}
        </p>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{stage.desc}</p>
      </div>
    </div>
  )
}

export default function UploadExtract() {
  const navigate  = useNavigate()
  const fileRef   = useRef(null)
  const folderRef = useRef(null)

  // ── single upload state ──────────────────────────────────────────────────────
  const [dragging,    setDragging]    = useState(false)
  const [file,        setFile]        = useState(null)
  const [uploading,   setUploading]   = useState(false)
  const [stageStatus, setStageStatus] = useState({})
  const [result,      setResult]      = useState(null)
  const [error,       setError]       = useState(null)

  // ── batch state ──────────────────────────────────────────────────────────────
  const [batchActive,   setBatchActive]   = useState(false)
  const [batchTotal,    setBatchTotal]    = useState(0)
  const [batchDone,     setBatchDone]     = useState(0)
  const [batchSuccess,  setBatchSuccess]  = useState(0)
  const [batchFailures, setBatchFailures] = useState([])
  const [batchToast,    setBatchToast]    = useState(null)

  const cancelRef = useRef(false)

  const busy    = uploading || batchActive
  const batchPct = batchTotal > 0 ? Math.round((batchDone / batchTotal) * 100) : 0

  // ── single upload helpers ────────────────────────────────────────────────────
  const setStage = (key, status) =>
    setStageStatus(prev => ({ ...prev, [key]: status }))

  const handleFile = (f) => {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['pdf', 'png', 'jpg', 'jpeg', 'tiff'].includes(ext)) {
      setError('Only PDF and image files are supported.')
      return
    }
    setFile(f)
    setResult(null)
    setError(null)
    setStageStatus({})
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }, [])

  const simulateProgress = async () => {
    for (const stage of STAGES) {
      setStage(stage.key, 'active')
      await new Promise(r => setTimeout(r, 600))
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    setStageStatus(Object.fromEntries(STAGES.map(s => [s.key, 'pending'])))
    const animPromise = simulateProgress()
    try {
      const res = await uploadApi.upload(file, 'payable')
      await animPromise
      STAGES.forEach(s => setStage(s.key, 'done'))
      setResult(res)
    } catch (e) {
      await animPromise
      STAGES.forEach(s => setStage(s.key, prev => prev === 'active' ? 'error' : prev))
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const reset = () => {
    setFile(null)
    setResult(null)
    setError(null)
    setStageStatus({})
    setUploading(false)
  }

  // ── batch: sequential per-file loop ─────────────────────────────────────────
  const handleFolderChange = async (e) => {
    const allFiles = Array.from(e.target.files || [])
    e.target.value = ''

    const pdfs = allFiles.filter(f => f.name.toLowerCase().endsWith('.pdf'))

    if (pdfs.length === 0) {
      setBatchToast({ message: 'No PDF files found in selected folder', type: 'error' })
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
          message: `Cancelled at ${doneCount}/${pdfs.length} — ${successCount} ingested`,
          type: 'warning',
        })
        setTimeout(() => setBatchToast(null), 5000)
        break
      }

      try {
        await uploadApi.upload(pdf, 'payable')
        successCount++
      } catch (err) {
        failures.push({ filename: pdf.name, error: err.message || 'Unknown error' })
      }

      doneCount++
      setBatchDone(doneCount)
      setBatchSuccess(successCount)
      setBatchFailures([...failures])
    }

    if (!cancelRef.current) {
      setBatchToast({
        message: `${successCount}/${pdfs.length} invoices ingested successfully`,
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
          Upload & Extract
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Upload a PDF or invoice image. The AI pipeline will extract structured data automatically.
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
                  <X size={12} /> Remove
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
                  Drop a file here or click to browse
                </p>
                <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                  Supports PDF, PNG, JPG, TIFF
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error (single upload) */}
      {error && (
        <div className="card p-4 flex items-center gap-3" style={{ borderColor: '#FECACA' }}>
          <AlertCircle size={16} color="#EF4444" />
          <p className="text-sm" style={{ color: '#EF4444' }}>{error}</p>
        </div>
      )}

      {/* Pipeline stages (single upload) */}
      {Object.keys(stageStatus).length > 0 && !result && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            Processing Pipeline
          </h2>
          <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {STAGES.map(s => (
              <StageRow key={s.key} stage={s} status={stageStatus[s.key] || 'pending'} />
            ))}
          </div>
        </div>
      )}

      {/* Result (single upload) */}
      {result && (
        <div className="space-y-4 animate-fade-up">
          <div className="card p-4 flex items-center gap-3" style={{ borderColor: '#BBF7D0' }}>
            <CheckCircle size={16} color="#22C55E" />
            <div className="flex-1">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                Invoice extracted successfully
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Stored as {result.invoice_number || result.invoice?.invoice_number || 'new invoice'}
              </p>
            </div>
            {(result.confidence_score || result.invoice?.confidence_score) != null && (
              <ConfidenceBar score={result.confidence_score || result.invoice?.confidence_score} />
            )}
          </div>
          <div className="card overflow-hidden">
            <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border)' }}>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Extracted Data</h2>
            </div>
            <pre className="p-5 text-xs font-mono overflow-x-auto leading-relaxed"
              style={{ color: 'var(--text-secondary)', background: 'var(--bg-secondary)', maxHeight: 400 }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
          <div className="flex gap-3">
            <button onClick={reset} className="btn-secondary">Upload Another</button>
            {(result.id || result.invoice?.id) && (
              <button
                onClick={() => navigate(`/payables/${result.id || result.invoice?.id}`)}
                className="btn-primary"
              >
                View Invoice
              </button>
            )}
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!result && (
        <div className="flex items-center gap-3 flex-wrap">
          {/* Single upload */}
          {file && !uploading && (
            <button onClick={handleUpload} disabled={busy} className="btn-primary disabled:opacity-50">
              <Upload size={15} /> Extract Invoice
            </button>
          )}

          {/* Folder ingest */}
          <button
            onClick={() => folderRef.current?.click()}
            disabled={busy}
            className="btn-secondary disabled:opacity-50"
          >
            {batchActive
              ? <><Loader2 size={14} className="animate-spin" /> Ingesting…</>
              : <><FolderOpen size={14} /> Ingest Folder</>
            }
          </button>

          {/* Cancel — only during batch */}
          {batchActive && (
            <button
              onClick={() => { cancelRef.current = true }}
              className="btn-ghost text-xs h-8 px-3"
              style={{ color: '#EF4444' }}
            >
              <X size={13} /> Cancel
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
              Ingesting folder
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
            <span style={{ color: '#22C55E' }}>✓ {batchSuccess} succeeded</span>
            {batchFailures.length > 0 && (
              <span style={{ color: '#EF4444' }}>✗ {batchFailures.length} failed</span>
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
              Failed ({batchFailures.length})
            </h2>
            <button
              onClick={() => setBatchFailures([])}
              className="btn-ghost p-1.5 rounded-lg flex items-center gap-1 text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              <X size={13} /> Dismiss
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