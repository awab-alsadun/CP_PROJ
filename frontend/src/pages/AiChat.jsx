import { useRef, useEffect, useState } from 'react'
import { SendHorizontal, Trash2, Bot, Sparkles, FileText, Scale, ChevronDown, ChevronUp } from 'lucide-react'
import { useChat } from '../context/ChatContext'
import { formatRelative } from '../lib/utils'

const SUGGESTIONS = [
  'Which vendors have the most unpaid invoices?',
  'What is the total revenue for last month?',
  'Show me all overdue invoices',
  'Which clients pay the slowest?',
  'Compare spending across vendors this quarter',
  'Are there any duplicate invoice numbers?',
]

const QUERY_BADGE = {
  sql:            { label: 'SQL',    bg: '#EFF6FF', color: '#3B82F6' },
  rag_invoice:    { label: 'RAG',    bg: '#F5F3FF', color: '#8B5CF6' },
  rag_compliance: { label: 'RAG',    bg: '#F5F3FF', color: '#8B5CF6' },
  hybrid:         { label: 'Hybrid', bg: '#FFFBEB', color: '#D4A847' },
}

function SourceCard({ source }) {
  const [expanded, setExpanded] = useState(false)
  const isInvoice = source.source_type === 'invoices'
  const Icon = isInvoice ? FileText : Scale
  const iconColor = isInvoice ? '#3B82F6' : '#8B5CF6'
  const pct = source.similarity != null ? Math.round(source.similarity * 100) : null

  return (
    <div className="rounded-xl border text-xs overflow-hidden"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
      <div
        className="flex items-center gap-2.5 px-3 py-2.5 cursor-pointer"
        onClick={() => source.chunk_text && setExpanded(v => !v)}
      >
        <Icon size={13} style={{ color: iconColor }} className="flex-shrink-0" />
        <span className="flex-1 font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {source.citation || source.invoice_number || source.document_name || 'Source'}
        </span>
        {source.section_title && (
          <span className="text-xs truncate max-w-[120px]" style={{ color: 'var(--text-muted)' }}>
            {source.section_title}
          </span>
        )}
        {pct != null && (
          <span className="font-mono font-medium flex-shrink-0 text-xs px-1.5 py-0.5 rounded"
            style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
            {pct}%
          </span>
        )}
        {source.chunk_text && (
          expanded
            ? <ChevronUp size={12} style={{ color: 'var(--text-muted)' }} />
            : <ChevronDown size={12} style={{ color: 'var(--text-muted)' }} />
        )}
      </div>
      {expanded && source.chunk_text && (
        <div className="px-3 pb-3 border-t" style={{ borderColor: 'var(--border)' }}>
          <p className="mt-2 leading-relaxed"
            style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            {source.chunk_text.slice(0, 400)}{source.chunk_text.length > 400 ? '…' : ''}
          </p>
        </div>
      )}
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  const badge = !isUser && msg.queryType ? QUERY_BADGE[msg.queryType] : null
  const sources = msg.sources || []

  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''} max-w-3xl ${isUser ? 'ml-auto' : 'mr-auto'} w-full`}>
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-semibold"
        style={{
          background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
          color: isUser ? '#131310' : 'var(--text-secondary)',
          border: isUser ? 'none' : '1px solid var(--border)',
        }}>
        {isUser ? 'U' : <Bot size={15} />}
      </div>

      <div className={`flex flex-col gap-2 flex-1 ${isUser ? 'items-end' : ''}`}>
        {/* Query type badge */}
        {badge && (
          <span className="self-start text-xs px-2.5 py-0.5 rounded-full font-medium"
            style={{ background: badge.bg, color: badge.color }}>
            {badge.label}
          </span>
        )}

        <div className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
          style={{
            background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
            color: isUser ? '#131310' : 'var(--text-primary)',
            borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          }}>
          {msg.content}
        </div>

        {/* Sources */}
        {!isUser && sources.length > 0 && (
          <div className="w-full space-y-1.5">
            <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
              Sources ({sources.length})
            </p>
            {sources.slice(0, 6).map((s, i) => (
              <SourceCard key={i} source={s} />
            ))}
          </div>
        )}

        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {formatRelative(msg.timestamp)}
        </span>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-4 max-w-3xl mr-auto w-full">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 border"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
        <Bot size={15} style={{ color: 'var(--text-secondary)' }} />
      </div>
      <div className="px-4 py-3.5 rounded-2xl flex items-center gap-1.5"
        style={{ background: 'var(--bg-secondary)', borderRadius: '4px 16px 16px 16px' }}>
        <span className="loading-dot" />
        <span className="loading-dot" />
        <span className="loading-dot" />
      </div>
    </div>
  )
}

export default function AiChat() {
  const { messages, isLoading, sendMessage, clearMessages } = useChat()
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => { inputRef.current?.focus() }, [])

  const handleSend = () => {
    if (!input.trim() || isLoading) return
    sendMessage(input.trim())
    setInput('')
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-primary)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--accent)' }}>
            <Sparkles size={16} color="#131310" />
          </div>
          <div>
            <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
              Invoice AI Assistant
            </p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Hybrid SQL + RAG · Invoices + Compliance Documents
            </p>
          </div>
        </div>
        <button onClick={clearMessages} className="btn-ghost text-xs h-8">
          <Trash2 size={13} /> Clear
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ background: 'var(--accent-light)' }}>
              <Sparkles size={24} style={{ color: 'var(--accent)' }} />
            </div>
            <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              Ask about your invoices
            </p>
            <p className="text-sm text-center max-w-xs" style={{ color: 'var(--text-muted)' }}>
              Query invoice data with SQL precision or search compliance documents semantically
            </p>
          </div>
        )}

        {messages.map(msg => <Message key={msg.id} msg={msg} />)}
        {isLoading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && !isLoading && (
        <div className="px-8 pb-4">
          <p className="text-xs font-medium mb-3" style={{ color: 'var(--text-muted)' }}>
            Suggested questions
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => sendMessage(s)}
                className="text-left text-xs px-3 py-2.5 rounded-xl border transition-all hover:border-[var(--accent)]"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-secondary)' }}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="px-8 pb-6">
        <div className="flex gap-3 items-end p-3 rounded-2xl border"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder="Ask about your invoices, vendors, or compliance documents…"
            rows={1}
            className="flex-1 bg-transparent text-sm resize-none outline-none leading-relaxed"
            style={{ color: 'var(--text-primary)', minHeight: '24px', maxHeight: '120px' }}
          />
          <button onClick={handleSend} disabled={!input.trim() || isLoading}
            className="btn-primary h-9 px-3 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed">
            <SendHorizontal size={15} />
          </button>
        </div>
        <p className="text-xs text-center mt-2" style={{ color: 'var(--text-muted)' }}>
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}