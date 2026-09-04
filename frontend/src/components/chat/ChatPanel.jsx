import React, { useEffect, useRef, useState } from 'react';
import { X, Send, FileText, Scale, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChat } from '../../context/ChatContext';
import { formatDate } from '../../lib/utils';

const QUERY_BADGE = {
  sql:            { label: 'SQL',    color: '#3B82F6' },
  rag_invoice:    { label: 'RAG',    color: '#8B5CF6' },
  rag_compliance: { label: 'RAG',    color: '#8B5CF6' },
  hybrid:         { label: 'Hybrid', color: '#D4A847' },
};

const PROVIDER_LABEL = {
  gemini:     'Gemini',
  openrouter: 'OpenRouter',
  ollama:     'Ollama',
  grok:       'Grok',
  openai:     'OpenAI',
};

export default function ChatPanel({ open, onClose }) {
  const { t, i18n } = useTranslation();
  const { messages, sendMessage, clearMessages, isLoading, llmProvider, setLlmProvider } = useChat();
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);
  // Derived directly from i18n.language (not getDirection()/document.documentElement.dir):
  // the <html dir> attribute is set by an effect in App.jsx that runs AFTER this
  // component's own render in the same commit (React flushes effects leaf-first),
  // so reading the DOM attribute here would show the *previous* language's
  // direction for one render whenever the drawer is open during a language switch.
  // i18n.language updates synchronously with this render, so deriving dir from it
  // avoids that one-frame staleness.
  const dir = i18n.language === 'ar' ? 'rtl' : 'ltr';

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  function handleSend() {
    const q = input.trim();
    if (!q || isLoading) return;
    setInput('');
    sendMessage(q);
  }

  return (
    <div style={{
      position: 'fixed',
      [dir === 'rtl' ? 'left' : 'right']: open ? 0 : -400,
      top: 0, bottom: 0, width: 380,
      background: 'var(--bg-card)',
      [dir === 'rtl' ? 'borderRight' : 'borderLeft']: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', zIndex: 300,
      transition: `${dir === 'rtl' ? 'left' : 'right'} 0.25s ease`,
      boxShadow: open ? (dir === 'rtl' ? '8px 0 40px rgba(0,0,0,0.15)' : '-8px 0 40px rgba(0,0,0,0.15)') : 'none',
    }}>
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 14, fontFamily: 'var(--font-display)' }}>{t('chat.jarvis')}</span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <select
            value={llmProvider}
            onChange={e => setLlmProvider(e.target.value)}
            title={t('chat.modelLabel')}
            style={{
              fontSize: 11, padding: '4px 6px', borderRadius: 6,
              background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', cursor: 'pointer',
            }}
          >
            <option value="">{t('chat.defaultModel')}</option>
            <option value="gemini">Gemini</option>
            <option value="openrouter">OpenRouter</option>
            <option value="ollama">Ollama (local)</option>
          </select>
          <button className="btn-ghost" onClick={clearMessages} title={t('chat.clear')} style={{ padding: 6, borderRadius: 6 }}><Trash2 size={14} /></button>
          <button className="btn-ghost" onClick={onClose} style={{ padding: 6, borderRadius: 6 }}><X size={14} /></button>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12, marginTop: 40 }}>
            {t('chat.emptyState')}
          </div>
        )}
        {messages.map(msg => (
          <Message key={msg.id} msg={msg} dir={dir} />
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: 4, padding: '8px 0' }}>
            {[0,1,2].map(i => <span key={i} className="loading-dot" style={{ animationDelay: `${i*0.15}s` }} />)}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
        <input
          className="input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={t('chat.placeholder')}
          style={{ flex: 1, fontSize: 13, padding: '8px 12px' }}
        />
        <button className="btn-primary" onClick={handleSend} disabled={isLoading} style={{ padding: '8px 12px', borderRadius: 8 }}>
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}

function Message({ msg, dir }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const badge = QUERY_BADGE[msg.queryType];
  const isUser = msg.role === 'user';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 4 }}>
      <div style={{
        maxWidth: '90%', padding: '8px 12px',
        borderRadius: isUser
          ? (dir === 'rtl' ? '12px 12px 12px 4px' : '12px 12px 4px 12px')
          : (dir === 'rtl' ? '12px 12px 4px 12px' : '12px 12px 12px 4px'),
        background: isUser ? 'var(--accent)' : (msg.error ? '#EF444422' : 'var(--bg-secondary)'),
        color: isUser ? '#131310' : (msg.error ? '#EF4444' : 'var(--text-primary)'),
        fontSize: 13, lineHeight: 1.6,
      }}>
        {msg.content}
      </div>

      {(badge || msg.provider) && (
        <div style={{ display: 'flex', gap: 4 }}>
          {badge && (
            <span style={{ fontSize: 10, fontWeight: 600, color: badge.color, background: badge.color + '20', padding: '1px 6px', borderRadius: 4 }}>
              {badge.label}
            </span>
          )}
          {msg.provider && (
            <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', background: 'var(--bg-secondary)', padding: '1px 6px', borderRadius: 4 }}>
              {PROVIDER_LABEL[msg.provider] || msg.provider}
            </span>
          )}
        </div>
      )}

      {msg.sources?.length > 0 && (
        <button
          className="btn-ghost"
          onClick={() => setExpanded(e => !e)}
          style={{ fontSize: 11, padding: '2px 6px', color: 'var(--text-muted)' }}>
          {expanded ? t('chat.hideSources') : t('chat.sources', { count: msg.sources.length })}
        </button>
      )}

      {expanded && msg.sources.slice(0, 6).map((s, i) => {
        const Icon = s.source_type === 'regulation' ? Scale : FileText;
        return (
          <div key={i} style={{ width: '90%', padding: '8px 10px', borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 11 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
              <Icon size={11} color="var(--text-muted)" />
              <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>{s.citation || `Source ${i + 1}`}</span>
              {s.similarity != null && <span style={{ color: 'var(--text-muted)', [dir === 'rtl' ? 'marginRight' : 'marginLeft']: 'auto' }}>{Math.round(s.similarity * 100)}%</span>}
            </div>
            {s.chunk_text && <div style={{ color: 'var(--text-muted)', lineHeight: 1.5 }}>{s.chunk_text.slice(0, 120)}…</div>}
          </div>
        );
      })}
    </div>
  );
}
