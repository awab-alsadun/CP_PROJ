import React, { useEffect, useRef, useState } from 'react';
import { Send, Trash2, FileText, Scale } from 'lucide-react';
import { useChat } from '../context/ChatContext';

const QUERY_BADGE = {
  sql:            { label: 'SQL',    color: '#3B82F6' },
  rag_invoice:    { label: 'RAG',    color: '#8B5CF6' },
  rag_compliance: { label: 'RAG',    color: '#8B5CF6' },
  hybrid:         { label: 'Hybrid', color: '#D4A847' },
};

const SUGGESTIONS = [
  'Which vendors have the highest outstanding balances?',
  'Show me all overdue invoices from last month',
  'What is the total amount paid this quarter?',
  'Are there any compliance issues I should know about?',
];

export default function AiChat() {
  const { messages, sendMessage, clearMessages, isLoading } = useChat();
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isLoading]);

  function handleSend() {
    const q = input.trim();
    if (!q || isLoading) return;
    setInput('');
    sendMessage(q);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 112px)', maxWidth: 800, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Ask questions about your invoices, vendors, payments, and financial data.
        </div>
        {messages.length > 0 && (
          <button className="btn-ghost" onClick={clearMessages} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, padding: '5px 10px' }}>
            <Trash2 size={12} /> Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: 8 }}>
        {messages.length === 0 && (
          <div>
            <div style={{ textAlign: 'center', padding: '40px 0 32px', color: 'var(--text-muted)', fontSize: 14 }}>
              Start by asking a question about your financial data.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {SUGGESTIONS.map((s, i) => (
                <button key={i} className="card" onClick={() => { setInput(s); }} style={{
                  textAlign: 'left', padding: '12px 16px', cursor: 'pointer', fontSize: 12,
                  color: 'var(--text-secondary)', lineHeight: 1.5,
                  transition: 'transform 0.15s',
                }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}

        {isLoading && (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            <span className="loading-dot" />
            <span className="loading-dot" style={{ animationDelay: '0.15s' }} />
            <span className="loading-dot" style={{ animationDelay: '0.30s' }} />
            <span style={{ marginLeft: 6 }}>Thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ paddingTop: 16, borderTop: '1px solid var(--border)', display: 'flex', gap: 10 }}>
        <input
          className="input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder="Ask about invoices, vendors, payments, or analytics…"
          style={{ flex: 1, fontSize: 14, padding: '10px 16px' }}
          disabled={isLoading}
        />
        <button className="btn-primary" onClick={handleSend} disabled={isLoading || !input.trim()} style={{ padding: '10px 18px', borderRadius: 10 }}>
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  const [expanded, setExpanded] = useState(false);
  const isUser = msg.role === 'user';
  const badge = QUERY_BADGE[msg.queryType];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 6 }}>
      <div style={{
        maxWidth: '85%', padding: '12px 16px', borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
        background: isUser ? 'var(--accent)' : (msg.error ? '#EF444415' : 'var(--bg-card)'),
        color: isUser ? '#131310' : (msg.error ? '#EF4444' : 'var(--text-primary)'),
        border: isUser ? 'none' : '1px solid var(--border)',
        fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap',
      }}>
        {msg.content}
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        {badge && (
          <span style={{ fontSize: 10, fontWeight: 700, color: badge.color, background: badge.color + '18', padding: '2px 7px', borderRadius: 4 }}>
            {badge.label}
          </span>
        )}
        {msg.sources?.length > 0 && (
          <button className="btn-ghost" onClick={() => setExpanded(e => !e)} style={{ fontSize: 11, padding: '2px 8px', color: 'var(--text-muted)' }}>
            {expanded ? 'Hide sources' : `${msg.sources.length} source${msg.sources.length > 1 ? 's' : ''}`}
          </button>
        )}
      </div>

      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: '85%', width: '100%' }}>
          {msg.sources.slice(0, 6).map((s, i) => {
            const Icon = s.source_type === 'regulation' ? Scale : FileText;
            const invType = s.invoice_type || 'payable';
            return (
              <div key={i} style={{ padding: '10px 14px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                  <Icon size={12} color="var(--text-muted)" />
                  {s.invoice_id ? (
                    <a href={`/${invType === 'receivable' ? 'receivables' : 'payables'}/${s.invoice_id}`} style={{ fontWeight: 600, color: 'var(--accent)', textDecoration: 'none' }}>
                      {s.citation || `Invoice ${s.invoice_id.slice(0, 8)}`}
                    </a>
                  ) : (
                    <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>{s.citation || `Source ${i + 1}`}</span>
                  )}
                  {s.similarity != null && (
                    <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>{Math.round(s.similarity * 100)}% match</span>
                  )}
                </div>
                {s.chunk_text && (
                  <div style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>{s.chunk_text.slice(0, 200)}{s.chunk_text.length > 200 ? '…' : ''}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
