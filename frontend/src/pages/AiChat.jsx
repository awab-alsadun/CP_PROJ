import React, { useEffect, useRef, useState } from 'react';
import { Send, Trash2, FileText, Scale } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChat } from '../context/ChatContext';

const QUERY_BADGE = {
  sql:            { label: 'SQL',    color: '#3B82F6' },
  rag_invoice:    { label: 'RAG',    color: '#8B5CF6' },
  rag_compliance: { label: 'RAG',    color: '#8B5CF6' },
  hybrid:         { label: 'Hybrid', color: '#D4A847' },
};

// Provider/product names — left untranslated like "InVox" in Login.jsx and the
// "SQL"/"RAG" labels in QUERY_BADGE above; these are brand names, not UI copy.
const PROVIDER_LABEL = {
  gemini:     'Gemini',
  openrouter: 'OpenRouter',
  ollama:     'Ollama',
  grok:       'Grok',
  openai:     'OpenAI',
};

export default function AiChat() {
  const { t, i18n } = useTranslation();
  // Derived directly from i18n.language rather than the <html dir> attribute —
  // see ChatPanel.jsx for why (App.jsx's effect that sets document.documentElement.dir
  // runs after this component's own render in the same commit, so reading the DOM
  // attribute here would show the *previous* language's direction for one render).
  const dir = i18n.language === 'ar' ? 'rtl' : 'ltr';
  const { messages, sendMessage, clearMessages, isLoading, llmProvider, setLlmProvider } = useChat();
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);
  const SUGGESTIONS = [t('chat.suggestion1'), t('chat.suggestion2'), t('chat.suggestion3'), t('chat.suggestion4')];

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
          {t('chat.pageIntro')}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <select
            value={llmProvider}
            onChange={e => setLlmProvider(e.target.value)}
            title={t('chat.modelLabel')}
            style={{
              fontSize: 12, padding: '5px 8px', borderRadius: 8,
              background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', cursor: 'pointer',
            }}
          >
            <option value="">{t('chat.defaultModel')}</option>
            <option value="gemini">Gemini</option>
            <option value="openrouter">OpenRouter</option>
            <option value="ollama">Ollama {t('chat.local')}</option>
          </select>
          {messages.length > 0 && (
            <button className="btn-ghost" onClick={clearMessages} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, padding: '5px 10px' }}>
              <Trash2 size={12} /> {t('chat.clear')}
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: 8 }}>
        {messages.length === 0 && (
          <div>
            <div style={{ textAlign: 'center', padding: '40px 0 32px', color: 'var(--text-muted)', fontSize: 14 }}>
              {t('chat.startPrompt')}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {SUGGESTIONS.map((s, i) => (
                <button key={i} className="card" onClick={() => { setInput(s); }} style={{
                  textAlign: dir === 'rtl' ? 'right' : 'left', padding: '12px 16px', cursor: 'pointer', fontSize: 12,
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
          <ChatMessage key={msg.id} msg={msg} dir={dir} />
        ))}

        {isLoading && (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            <span className="loading-dot" />
            <span className="loading-dot" style={{ animationDelay: '0.15s' }} />
            <span className="loading-dot" style={{ animationDelay: '0.30s' }} />
            <span style={{ [dir === 'rtl' ? 'marginRight' : 'marginLeft']: 6 }}>{t('chat.thinking')}</span>
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
          placeholder={t('chat.inputPlaceholder')}
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

function ChatMessage({ msg, dir }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const isUser = msg.role === 'user';
  const badge = QUERY_BADGE[msg.queryType];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 6 }}>
      <div style={{
        maxWidth: '85%', padding: '12px 16px',
        // border-radius corners are physical (top-left/top-right/bottom-right/bottom-left) and don't
        // auto-mirror under dir="rtl" the way alignItems: 'flex-end'/'flex-start' does above — swap the
        // sharp "tail" corner to the opposite side so it still points at the edge the bubble hugs after
        // the flex alignment flips. Same class of fix as ChatPanel.jsx's message bubbles (Task 10).
        borderRadius: isUser
          ? (dir === 'rtl' ? '16px 16px 16px 4px' : '16px 16px 4px 16px')
          : (dir === 'rtl' ? '16px 4px 16px 16px' : '4px 16px 16px 16px'),
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
        {msg.provider && (
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', background: 'var(--bg-secondary)', padding: '2px 7px', borderRadius: 4 }}>
            {PROVIDER_LABEL[msg.provider] || msg.provider}
          </span>
        )}
        {msg.sources?.length > 0 && (
          <button className="btn-ghost" onClick={() => setExpanded(e => !e)} style={{ fontSize: 11, padding: '2px 8px', color: 'var(--text-muted)' }}>
            {expanded ? t('chat.hideSourcesLong') : t('chat.sources', { count: msg.sources.length })}
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
                      {s.citation || t('chat.invoiceFallback', { id: s.invoice_id.slice(0, 8) })}
                    </a>
                  ) : (
                    <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>{s.citation || t('chat.sourceFallback', { number: i + 1 })}</span>
                  )}
                  {s.similarity != null && (
                    <span style={{ [dir === 'rtl' ? 'marginRight' : 'marginLeft']: 'auto', color: 'var(--text-muted)' }}>{t('chat.matchPercent', { pct: Math.round(s.similarity * 100) })}</span>
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
