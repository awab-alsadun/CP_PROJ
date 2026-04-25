import { useRef, useEffect, useState } from 'react'
import { X, Maximize2, Minimize2, SendHorizontal, Trash2, Bot } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import { formatRelative, cn } from '../../lib/utils'

function ChatMessage({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={cn('flex gap-3 animate-fade-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div className={cn(
        'w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-semibold',
        isUser
          ? 'text-white'
          : 'border',
      )} style={{
        background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
        borderColor: 'var(--border)',
        color: isUser ? '#131310' : 'var(--text-secondary)',
      }}>
        {isUser ? 'U' : <Bot size={14} />}
      </div>

      <div className={cn('flex flex-col gap-1 max-w-[80%]', isUser && 'items-end')}>
        <div className={cn(
          'px-3 py-2.5 rounded-2xl text-sm leading-relaxed',
          isUser
            ? 'rounded-tr-sm text-[#131310]'
            : 'rounded-tl-sm',
          msg.error && 'border border-red-200 dark:border-red-900',
        )} style={{
          background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
          color: isUser ? '#131310' : 'var(--text-primary)',
        }}>
          {msg.content}
        </div>

        {/* Citations */}
        {msg.citations?.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {msg.citations.map((c, i) => (
              <span key={i} className="text-xs px-2 py-0.5 rounded-full border font-mono"
                style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
                {c}
              </span>
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

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop for non-expanded */}
      {!isExpanded && (
        <div className="fixed inset-0 z-40 pointer-events-none"
          style={{ background: 'transparent' }} />
      )}

      {/* Panel */}
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
            <button onClick={clearMessages} className="btn-ghost p-1.5 rounded-lg"
              title="Clear chat" aria-label="Clear chat">
              <Trash2 size={14} />
            </button>
            <button
              onClick={() => setIsExpanded(e => !e)}
              className="btn-ghost p-1.5 rounded-lg"
              title={isExpanded ? 'Collapse' : 'Expand'}
              aria-label={isExpanded ? 'Collapse chat' : 'Expand chat'}
            >
              {isExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button onClick={() => { setIsOpen(false); setIsExpanded(false) }}
              className="btn-ghost p-1.5 rounded-lg" aria-label="Close chat">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.map(msg => (
            <ChatMessage key={msg.id} msg={msg} />
          ))}
          {isLoading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {/* Suggested prompts — shown only if few messages */}
        {messages.length <= 1 && !isLoading && (
          <div className="px-4 pb-2 flex flex-col gap-1.5">
            <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              Suggestions
            </p>
            {[
              'Which vendors have unpaid invoices?',
              'Total revenue this month',
              'Show overdue invoices',
            ].map(s => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="text-left text-xs px-3 py-2 rounded-xl border transition-all duration-150 hover:border-[var(--accent)]"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-secondary)' }}
              >
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
              onKeyDown={handleKey}
              placeholder="Ask about your invoices..."
              rows={1}
              className="input flex-1 resize-none leading-relaxed"
              style={{ minHeight: '38px', maxHeight: '120px' }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="btn-primary h-9 px-3 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <SendHorizontal size={15} />
            </button>
          </div>
          <p className="text-xs mt-2 text-center" style={{ color: 'var(--text-muted)' }}>
            Enter to send · Shift+Enter for newline
          </p>
        </div>
      </div>
    </>
  )
}