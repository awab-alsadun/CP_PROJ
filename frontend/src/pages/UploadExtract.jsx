import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, CheckCircle, AlertTriangle, FileText, ArrowRight } from 'lucide-react';
import { uploadApi } from '../lib/api';
import { InvoiceTypeBadge, toast } from '../components/ui';

const STAGES = ['Uploading', 'OCR Extraction', 'LLM Parsing', 'DB Storage', 'Done'];

export default function UploadExtract() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState(-1); // -1 = idle
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  function handleFile(f) {
    if (!f) return;
    setFile(f); setResult(null); setError(null); setStage(-1);
  }

  async function handleUpload() {
    if (!file) return;
    setError(null); setResult(null);

    // Animate stages
    for (let i = 0; i < STAGES.length - 1; i++) {
      setStage(i);
      await new Promise(r => setTimeout(r, 400));
    }

    try {
      const res = await uploadApi.upload(file);
      setStage(STAGES.length - 1);
      setResult(res);
      if (res.duplicate) {
        toast('Duplicate invoice detected', 'warning');
      } else {
        toast('Invoice extracted and stored');
      }
    } catch (e) {
      setStage(-1);
      setError(e.message);
      toast(e.message, 'error');
    }
  }

  function handleDrop(e) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--accent-light)', border: '1px solid var(--accent)33', borderRadius: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
        Uploaded invoices are recorded as <strong>Payables (AP)</strong> — invoices you received from vendors.
      </div>

      {/* Drop zone */}
      <div
        className="card"
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          padding: '48px 24px', textAlign: 'center', cursor: 'pointer',
          border: `2px dashed ${dragging ? 'var(--accent)' : file ? '#22C55E' : 'var(--border)'}`,
          background: dragging ? 'var(--accent-light)' : 'var(--bg-card)',
          transition: 'all 0.2s', marginBottom: 16,
        }}>
        <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={e => handleFile(e.target.files[0])} />
        <Upload size={36} color={file ? '#22C55E' : 'var(--text-muted)'} style={{ margin: '0 auto 12px' }} />
        {file ? (
          <div>
            <div style={{ fontWeight: 600, fontSize: 15, color: '#22C55E', marginBottom: 4 }}>{file.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{(file.size / 1024).toFixed(0)} KB · Click to change</div>
          </div>
        ) : (
          <div>
            <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Drop invoice here</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>PDF, JPG, PNG · Click to browse</div>
          </div>
        )}
      </div>

      {file && stage === -1 && (
        <button className="btn-primary" onClick={handleUpload} style={{ width: '100%', padding: '12px', fontSize: 14, marginBottom: 16 }}>
          Extract Invoice
        </button>
      )}

      {/* Pipeline stages */}
      {stage >= 0 && (
        <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>Processing</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {STAGES.map((s, i) => {
              const done = i < stage || (stage === STAGES.length - 1);
              const active = i === stage && stage < STAGES.length - 1;
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    background: done ? '#22C55E20' : active ? 'var(--accent-light)' : 'var(--bg-secondary)',
                    border: `1.5px solid ${done ? '#22C55E' : active ? 'var(--accent)' : 'var(--border)'}`,
                  }}>
                    {done ? <CheckCircle size={12} color="#22C55E" /> : active ? <div className="loading-dot" style={{ width: 6, height: 6 }} /> : <span style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 700 }}>{i + 1}</span>}
                  </div>
                  <span style={{ fontSize: 13, color: done ? '#22C55E' : active ? 'var(--accent)' : 'var(--text-muted)', fontWeight: active ? 600 : 400 }}>{s}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="card" style={{ padding: 20 }}>
          {result.duplicate ? (
            <div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
                <AlertTriangle size={18} color="#F59E0B" />
                <span style={{ fontWeight: 600, color: '#F59E0B' }}>Duplicate Invoice Detected</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
                This invoice already exists in the system.
              </div>
              {result.existing_id && (
                <button
                  className="btn-secondary"
                  onClick={() => navigate(`/payables/${result.existing_id}`)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', fontSize: 13 }}>
                  View existing invoice <ArrowRight size={13} />
                </button>
              )}
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
                <CheckCircle size={18} color="#22C55E" />
                <span style={{ fontWeight: 600, color: '#22C55E' }}>Extraction Complete</span>
                <InvoiceTypeBadge type="payable" />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
                {result.invoice_number && <div><span style={{ color: 'var(--text-muted)' }}>Invoice #:</span> <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{result.invoice_number}</span></div>}
                {result.vendor_name && <div><span style={{ color: 'var(--text-muted)' }}>Vendor:</span> {result.vendor_name}</div>}
                {result.grand_total != null && <div><span style={{ color: 'var(--text-muted)' }}>Total:</span> <span style={{ fontFamily: 'var(--font-mono)' }}>{result.currency} {result.grand_total}</span></div>}
                {result.confidence_score != null && <div><span style={{ color: 'var(--text-muted)' }}>Confidence:</span> {Math.round(result.confidence_score * 100)}%</div>}
              </div>
              {result.id && (
                <button
                  className="btn-primary"
                  onClick={() => navigate(`/payables/${result.id}`)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', fontSize: 13 }}>
                  <FileText size={13} /> View Invoice <ArrowRight size={13} />
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{ padding: '14px 16px', background: '#EF444420', border: '1px solid #EF444433', borderRadius: 8, color: '#EF4444', fontSize: 13 }}>
          {error}
        </div>
      )}
    </div>
  );
}
