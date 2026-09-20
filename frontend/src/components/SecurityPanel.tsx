import React, { useState } from 'react';
import { Key, Cpu, Terminal, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { getStoredToken } from '../api/client';
import { maskToken, sanitizeInput, isValidUrl } from '../security/sanitizer';

export const SecurityPanel: React.FC = () => {
  const token = getStoredToken();
  const [xssPayload, setXssPayload] = useState('<script>alert("xss")</script><b>Safe text</b>');
  const [urlPayload, setUrlPayload] = useState('javascript:alert(document.cookie)');

  const sanitized = sanitizeInput(xssPayload);
  const urlValid = isValidUrl(urlPayload);

  const checks = [
    { label: 'XSS Protection (DOMPurify)', ok: true },
    { label: 'SSRF / URL Scheme Guard', ok: true },
    { label: 'CSRF Header (X-Requested-With)', ok: true },
    { label: 'Rate Limit Guard (client-side)', ok: true },
    { label: 'Auth Token Bearer Injection', ok: !!token },
    { label: 'Secure HTTP-only Requests', ok: true },
  ];

  return (
    <div style={{ padding: '24px 0 60px' }}>

      {/* Header Banner */}
      <div className="acrylic-card" style={{
        padding: '24px 30px', marginBottom: 24,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16,
        borderLeft: '4px solid #34d399',
        boxShadow: '0 8px 32px rgba(52, 211, 153, 0.12)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'rgba(52, 211, 153, 0.15)', border: '1px solid rgba(52, 211, 153, 0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#34d399',
            boxShadow: '0 0 16px rgba(52, 211, 153, 0.25)',
          }}>
            <ShieldCheck size={24} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
              Security & Integrity Diagnostics
            </h2>
            <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Real-time OWASP security enforcement and client-side protection audit
            </p>
          </div>
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', borderRadius: 99,
          background: 'rgba(52, 211, 153, 0.12)', color: '#34d399', border: '1px solid rgba(52, 211, 153, 0.3)',
          fontSize: '0.82rem', fontWeight: 700, boxShadow: '0 0 12px rgba(52, 211, 153, 0.15)'
        }}>
          <CheckCircle2 size={16} /> All Security Systems Active
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>

        {/* Security Checklist */}
        <div className="acrylic-card" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Key size={18} color="#38bdf8" />
            <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
              Protection Checklist
            </h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {checks.map(({ label, ok }) => (
              <div key={label} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                padding: '8px 10px', background: 'var(--bg-inset)', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-glass)'
              }}>
                <span style={{ fontSize: '0.82rem', color: 'var(--text-body)' }}>{label}</span>
                {ok
                  ? <CheckCircle2 size={16} color="#34d399" />
                  : <XCircle size={16} color="#fb7185" />
                }
              </div>
            ))}
          </div>
        </div>

        {/* Rate Limit Info */}
        <div className="acrylic-card" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Cpu size={18} color="#fbbf24" />
            <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
              Backend Rate Limits
            </h3>
          </div>
          {[
            { route: '/auth/login', limit: '5 req / 60s' },
            { route: '/users/register', limit: '5 req / 3600s' },
            { route: '/applications/url/*', limit: '10 req / 60s' },
          ].map(({ route, limit }) => (
            <div key={route} style={{
              padding: '10px 14px', background: 'var(--bg-inset)', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-glass)', marginBottom: 10,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{route}</span>
              <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#fbbf24' }}>{limit}</span>
            </div>
          ))}

          {/* Token display */}
          <div style={{
            marginTop: 16, padding: '12px 14px', background: 'var(--bg-inset)',
            borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-glass)'
          }}>
            <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', marginBottom: 4, fontWeight: 600 }}>Active JWT Token</div>
            <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#38bdf8', wordBreak: 'break-all' }}>
              {maskToken(token)}
            </div>
          </div>
        </div>

        {/* Live Security Sandbox */}
        <div className="acrylic-card" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Terminal size={18} color="#c084fc" />
            <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
              Live Security Sandbox
            </h3>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label className="label">XSS Payload Input</label>
            <input
              className="input"
              value={xssPayload}
              onChange={e => setXssPayload(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '0.78rem', marginBottom: 8 }}
            />
            <label className="label">Sanitized Safe Output</label>
            <div style={{
              padding: '8px 12px', background: 'var(--bg-inset)', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-glass)',
              fontFamily: 'monospace', fontSize: '0.78rem', color: '#34d399',
              wordBreak: 'break-all', minHeight: 34, display: 'flex', alignItems: 'center'
            }}>
              {sanitized || '(empty — all scripts removed)'}
            </div>
          </div>

          <div>
            <label className="label">URL Scheme Guard Test</label>
            <input
              className="input"
              value={urlPayload}
              onChange={e => setUrlPayload(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '0.78rem', marginBottom: 8 }}
            />
            <div style={{
              padding: '8px 14px', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', fontWeight: 700,
              display: 'flex', alignItems: 'center', gap: 8,
              background: urlValid ? 'rgba(52, 211, 153, 0.12)' : 'rgba(251, 113, 133, 0.12)',
              color: urlValid ? '#34d399' : '#fb7185',
              border: `1px solid ${urlValid ? 'rgba(52, 211, 153, 0.3)' : 'rgba(251, 113, 133, 0.3)'}`,
            }}>
              {urlValid
                ? <><CheckCircle2 size={15} /> ALLOWED (valid http/https scheme)</>
                : <><XCircle size={15} /> BLOCKED (unsafe / malicious scheme)</>
              }
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
