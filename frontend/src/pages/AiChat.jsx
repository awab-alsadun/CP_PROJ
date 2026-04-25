import { useRef, useEffect, useState } from 'react'
import { SendHorizontal, Trash2, Bot, Sparkles } from 'lucide-react'
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

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''} max-w-3xl ${isUser ? 'ml-auto' : 'mr-auto'} w-full`}>
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-semibold`}
        style={{
          background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
          color: isUser ? '#131310' : 'var(--text-secondary)',
          border: isUser ? 'none' : '1px solid var(--border)',
        }}>
        {isUser ? 'U' : <Bot size={15} />}
      </div>
      <div className={`flex flex-col gap-1.5 flex-1 ${isUser ? 'items-end' : ''}`}>
        <div className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
          style={{
            background: isUser ? 'var(--accent)' : 'var(--bg-secondary)',
            color: isUser ? '#131310' : 'var(--text-primary)',
            borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          }}>
          {msg.content}
        </div>
        {msg.citations?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
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

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = () => {
    if (!input.trim() || isLoading) return
    sendMessage(input.trim())
    setInput('')
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-primary)' }}>
      {/* Chat header */}
      <div className="flex items-center justify-between px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--accent)' }}>
            <Sparkles size={16} color="#131310" />
          </div>
          <div>
            <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Invoice AI Assistant</p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Hybrid SQL + RAG · Ask anything about your financial data
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
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="text-left text-xs px-3 py-2.5 rounded-xl border transition-all hover:border-[var(--accent)]"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-secondary)' }}
              >
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
            placeholder="Ask about your invoices, vendors, or financial data…"
            rows={1}
            className="flex-1 bg-transparent text-sm resize-none outline-none leading-relaxed"
            style={{ color: 'var(--text-primary)', minHeight: '24px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="btn-primary h-9 px-3 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
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