import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Files, Loader2, CheckCircle, AlertCircle, X } from 'lucide-react'
import { uploadApi } from '../lib/api'
import { toast } from '../components/ui'

const CARDS = [
  { key: 'payable_single',    title: 'Upload Payable',    subtitle: 'Single PDF or image',   icon: FileText, invoiceType: 'payable',    mode: 'single' },
  { key: 'receivable_single', title: 'Upload Receivable', subtitle: 'Single PDF or image',   icon: FileText, invoiceType: 'receivable', mode: 'single' },
  { key: 'payable_batch',     title: 'Payable Batch',     subtitle: 'Pick a folder of PDFs', icon: Files,    invoiceType: 'payable',    mode: 'batch'  },
  { key: 'receivable_batch',  title: 'Receivable Batch',  subtitle: 'Pick a folder of PDFs', icon: Files,    invoiceType: 'receivable', mode: 'batch'  },
]

const SINGLE_ACCEPT = '.pdf,.png,.jpg,.jpeg,.tiff'
const BATCH_ACCEPT  = '.pdf'

// ── Progress hook — counter-based, not time-based ──────────────────────────────
function useUploadProgress() {
  const [current, setCurrent] = useState(0)
  const [total,   setTotal]   = useState(0)
  const [phase,   setPhase]   = useState('idle') // 'idle' | 'running' | 'done' | 'error'
  const doneTimerRef = useRef(null)

  const clear = () => {
    if (doneTimerRef.current) { clearTimeout(doneTimerRef.current); doneTimerRef.current = null }
  }

  const reset = useCallback(() => {
    clear()
    setCurrent(0)
    setTotal(0)
    setPhase('idle')
  }, [])

  const start = useCallback((n) => {
    clear()
    setCurrent(0)
    setTotal(n)
    setPhase('running')
  }, [])

  const advance = useCallback(() => {
    setCurrent(c => c + 1)
  }, [])

  const finish = useCallback(() => {
    clear()
    setPhase('done')
    doneTimerRef.current = setTimeout(reset, 1500)
  }, [reset])

  const fail = useCallback(() => {
    clear()
    setPhase('error')
  }, [])

  useEffect(() => () => clear(), [])

  return { current, total, phase, start, advance, finish, fail, reset }
}

// ── Progress banner ────────────────────────────────────────────────────────────
function ProgressBanner({ current, total, phase, canCancel, onCancel }) {
  if (phase === 'idle') return null

  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0

  const fillColor =
    phase === 'done'  ? '#22C55E' :
    phase === 'error' ? '#EF4444' :
    'var(--accent)'

  const label =
    phase === 'done'  ? 'Done' :
    phase === 'error' ? 'Upload failed' :
    'Extracting…'

  return (
    <div
      className="card p-4 space-y-2"
      style={{
        borderColor:
          phase === 'done'  ? '#BBF7D0' :
          phase === 'error' ? '#FECACA' :
          'var(--border)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          {phase === 'done'    && <CheckCircle size={14} color="#22C55E" />}
          {phase === 'error'   && <AlertCircle size={14} color="#EF4444" />}
          {phase === 'running' && <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />}
          <span style={{ color: fillColor }}>{label}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            {current}/{total}
          </span>
          {canCancel && phase === 'running' && (
            <button
              onClick={onCancel}
              className="btn-ghost text-xs h-7 px-2 flex items-center gap-1"
              style={{ color: '#EF4444' }}
            >
              <X size={12} /> Cancel
            </button>
          )}
        </div>
      </div>

      <div
        className="w-full rounded-full overflow-hidden"
        style={{ height: 5, background: 'var(--border)' }}
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: fillColor,
            transition: 'width 0.2s ease',
          }}
        />
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function UploadExtract() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(null)
  const inputRefs = useRef({})
  const cancelRef = useRef(false)
  const progress  = useUploadProgress()

  const openPicker = (card) => {
    if (busy) return
    inputRefs.current[card.key]?.click()
  }

  const handleChange = async (e, card) => {
    const picked = Array.from(e.target.files || [])
    e.target.value = ''
    if (picked.length === 0) return

    // Filter PDFs for batch mode upfront
    const files = card.mode === 'batch'
      ? picked.filter(f => f.name.toLowerCase().endsWith('.pdf'))
      : picked.slice(0, 1)

    if (card.mode === 'batch' && files.length === 0) {
      toast('No PDF files found in selection', 'error')
      return
    }

    setBusy(card.key)
    cancelRef.current = false
    progress.start(files.length)

    const failures = []
    let success = 0
    let firstResult = null

    for (const file of files) {
      if (cancelRef.current) break
      try {
        const res = await uploadApi.upload(file, card.invoiceType)
        if (!firstResult) firstResult = res
        success++
      } catch (err) {
        failures.push({ filename: file.name, error: err.message || 'Unknown error' })
      }
      progress.advance()
    }

    setBusy(null)

    // Single upload — navigate to detail page
    if (card.mode === 'single') {
      if (success === 1 && firstResult) {
        const id     = firstResult?.data?.invoice_id     || firstResult?.invoice?.id             || firstResult?.id
        const number = firstResult?.data?.invoice_number || firstResult?.invoice?.invoice_number || firstResult?.invoice_number
        progress.finish()
        toast(`Invoice ${number || 'extracted'} ingested`, 'success')
        if (id) {
          const dest = card.invoiceType === 'receivable' ? `/receivables/${id}` : `/payables/${id}`
          setTimeout(() => navigate(dest), 1500)
        }
      } else {
        progress.fail()
        toast(failures[0]?.error || 'Upload failed', 'error')
      }
      return
    }

    // Batch
    const total = files.length
    const label = card.invoiceType === 'receivable' ? 'receivables' : 'payables'

    if (cancelRef.current) {
      progress.fail()
      toast(`Cancelled — ${success}/${total} ${label} ingested`, 'warning')
    } else if (success === 0) {
      progress.fail()
      toast(`All ${total} uploads failed`, 'error')
    } else if (failures.length > 0) {
      progress.finish()
      toast(`${success}/${total} ${label} ingested — ${failures.length} failed`, 'warning')
    } else {
      progress.finish()
      toast(`${success}/${total} ${label} ingested`, 'success')
    }
  }

  return (
    <div className="p-6 max-w-4xl space-y-5 animate-fade-up">
      <div>
        <h1 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Upload & Extract
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Pick an entry point. Each card runs the full OCR + LLM extraction pipeline server-side.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CARDS.map(card => {
          const Icon     = card.icon
          const active   = busy === card.key
          const disabled = busy !== null && !active
          return (
            <div
              key={card.key}
              onClick={() => !disabled && !active && openPicker(card)}
              className={`card p-5 transition-all duration-200 ${
                disabled ? 'opacity-40 cursor-not-allowed'
                : active ? 'cursor-wait'
                : 'cursor-pointer hover:scale-[1.005]'
              }`}
              style={{
                borderColor: active ? 'var(--accent)' : 'var(--border)',
                background:  active ? 'var(--accent-light)' : 'var(--bg-card)',
              }}
            >
              <div className="flex items-start gap-4">
                <div
                  className="w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0"
                  style={{ background: active ? 'var(--bg-card)' : 'var(--bg-secondary)' }}
                >
                  {active
                    ? <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
                    : <Icon    size={20} style={{ color: 'var(--text-secondary)' }} strokeWidth={1.5} />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                    {card.title}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    {active
                      ? (card.mode === 'batch' ? 'Processing batch…' : 'Processing…')
                      : card.subtitle
                    }
                  </p>
                </div>
              </div>

              <input
                ref={el => { inputRefs.current[card.key] = el }}
                type="file"
                accept={card.mode === 'single' ? SINGLE_ACCEPT : BATCH_ACCEPT}
                multiple={card.mode === 'batch'}
                {...(card.mode === 'batch' ? { webkitdirectory: '', directory: '' } : {})}
                className="hidden"
                onChange={e => handleChange(e, card)}
              />
            </div>
          )
        })}
      </div>

      <ProgressBanner
        current={progress.current}
        total={progress.total}
        phase={progress.phase}
        canCancel={progress.total > 1}
        onCancel={() => { cancelRef.current = true }}
      />
    </div>
  )
}