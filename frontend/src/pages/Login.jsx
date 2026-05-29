import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap } from 'lucide-react';

export default function Login() {
  const [uuid, setUuid] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  function handleEnter() {
    if (!UUID_RE.test(uuid.trim())) { setError('Enter a valid company UUID'); return; }
    localStorage.setItem('company_id', uuid.trim());
    navigate('/');
  }

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg-primary)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div className="card" style={{ width: 380, padding: 40, textAlign: 'center' }}>
        <div style={{ width: 52, height: 52, borderRadius: 14, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
          <Zap size={24} color="#131310" fill="#131310" />
        </div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 800, margin: '0 0 6px', color: 'var(--text-primary)' }}>InVox</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 28px' }}>AI Invoice Intelligence</p>

        <input
          className="input"
          placeholder="Company UUID"
          value={uuid}
          onChange={e => { setUuid(e.target.value); setError(''); }}
          onKeyDown={e => e.key === 'Enter' && handleEnter()}
          style={{ width: '100%', marginBottom: 12, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12 }}
        />
        {error && <div style={{ color: '#EF4444', fontSize: 12, marginBottom: 12 }}>{error}</div>}
        <button className="btn-primary" onClick={handleEnter} style={{ width: '100%', padding: '10px' }}>
          Enter Dashboard
        </button>
        <button
          className="btn-ghost"
          onClick={() => { setUuid('7bf697fc-7220-40c7-9678-542d624d22ad'); setError(''); }}
          style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
          Use demo UUID
        </button>
      </div>
    </div>
  );
}
