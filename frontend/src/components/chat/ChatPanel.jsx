import { useRef, useEffect, useState } from 'react'
import { X, Maximize2, Minimize2, SendHorizontal, Trash2, Bot, FileText, Scale, ChevronDown, ChevronUp } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import { formatRelative, cn } from '../../lib/utils'

const QUERY_TYPE_BADGE = {
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
      style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer"
        onClick={() => source.chunk_text && setExpanded(v => !v)}
      >
        <Icon size={12} style={{ color: iconColor }} className="flex-shrink-0" />
        <span className="flex-1 font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {source.citation || source.invoice_number || source.document_name || 'Source'}
        </span>
        {pct != null && (
          <span className="font-mono flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
            {pct}%
          </span>
        )}
        {source.chunk_text && (
          expanded
            ? <ChevronUp size={11} style={{ color: 'var(--text-muted)' }} className="flex-shrink-0" />
            : <ChevronDown size={11} style={{ color: 'var(--text-muted)' }} className="flex-shrink-0" />
        )}
      </div>
      {expanded && source.chunk_text && (
        <div className="px-3 pb-2.5 pt-0 border-t" style={{ borderColor: 'var(--border)' }}>
          <p className="leading-relaxed line-clamp-4 mt-1.5"
            style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
            {source.chunk_text.slice(0, 300)}{source.chunk_text.length > 300 ? '…' : ''}
          </p>
          {source.section_title && (
            <p className="mt-1 font-medium" style={{ color: 'var(--text-muted)', fontSize: 10 }}>
              {source.section_title}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ChatMessage({ msg }) {
  const isUser = msg.role === 'user'
  const badge = msg.queryType ? QUERY_TYPE_BADGE[msg.queryType] : null
  const sources = msg.sources || []

  return (
    <div className={cn('flex gap-3 animate-fade-up', isUser && 'flex-row-reverse')}>
      <div className={cn(
        'w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-semibold',
        isUser ? 'text-white' : 'border',
      )} style={{
        background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
        borderColor: 'var(--border)',
        color: isUser ? '#131310' : 'var(--text-secondary)',
      }}>
        {isUser ? 'U' : <Bot size={14} />}
      </div>

      <div className={cn('flex flex-col gap-1.5 max-w-[82%]', isUser && 'items-end')}>
        {/* Query type badge */}
        {!isUser && badge && (
          <span className="self-start text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: badge.bg, color: badge.color }}>
            {badge.label}
          </span>
        )}

        <div className={cn(
          'px-3 py-2.5 rounded-2xl text-sm leading-relaxed',
          isUser ? 'rounded-tr-sm' : 'rounded-tl-sm',
          msg.error && 'border border-red-200',
        )} style={{
          background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
          color: isUser ? '#131310' : 'var(--text-primary)',
        }}>
          {msg.content}
        </div>

        {/* Source cards */}
        {!isUser && sources.length > 0 && (
          <div className="w-full space-y-1 mt-0.5">
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
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-xl flex items-center justify-center border flex-shrink-0"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
        <Bot size={14} style={{ color: 'var(--text-secondary)' }} />
      </div>
      <div className="px-3 py-3 rounded-2xl rounded-tl-sm flex items-center gap-1"
        style={{ background: 'var(--bg-secondary)' }}>
        <span className="loading-dot" />
        <span className="loading-dot" />
        <span className="loading-dot" />
      </div>
    </div>
  )
}

export default function ChatPanel() {
  const { isOpen, setIsOpen, isExpanded, setIsExpanded, messages, isLoading, sendMessage, clearMessages } = useChat()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen, messages])

  const handleSend = () => {
    if (!input.trim()) return
    sendMessage(input.trim())
    setInput('')
  }

  if (!isOpen) return null

  return (
    <div
      className={cn(
        'fixed top-0 right-0 h-full z-50 flex flex-col border-l animate-slide-in-right',
        isExpanded ? 'w-full max-w-2xl' : 'w-80 sm:w-96'
      )}
      style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-14 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--accent)' }}>
            <Bot size={14} color="#131310" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-none" style={{ color: 'var(--text-primary)' }}>
              Invoice AI
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Ask anything about your data
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={clearMessages} className="btn-ghost p-1.5 rounded-lg" title="Clear chat">
            <Trash2 size={14} />
          </button>
          <button onClick={() => setIsExpanded(e => !e)} className="btn-ghost p-1.5 rounded-lg">
            {isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button onClick={() => { setIsOpen(false); setIsExpanded(false) }}
            className="btn-ghost p-1.5 rounded-lg">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map(msg => <ChatMessage key={msg.id} msg={msg} />)}
        {isLoading && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && !isLoading && (
        <div className="px-4 pb-2 flex flex-col gap-1.5">
          <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>Suggestions</p>
          {[
            'Which vendors have unpaid invoices?',
            'Total revenue this month',
            'Show overdue invoices',
          ].map(s => (
            <button key={s} onClick={() => sendMessage(s)}
              className="text-left text-xs px-3 py-2 rounded-xl border transition-all duration-150 hover:border-[var(--accent)]"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-secondary)' }}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder="Ask about your invoices..."
            rows={1}
            className="input flex-1 resize-none leading-relaxed"
            style={{ minHeight: '38px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="btn-primary h-9 px-3 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <SendHorizontal size={15} />
          </button>
        </div>
        <p className="text-xs mt-2 text-center" style={{ color: 'var(--text-muted)' }}>
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}