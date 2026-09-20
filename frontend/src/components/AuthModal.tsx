import React, { useState } from 'react';
import { X, User, Mail, Lock, Eye, EyeOff } from 'lucide-react';
import { loginUser, registerUser, getMe, setStoredToken } from '../api/client';
import type { User as UserType } from '../api/client';

interface AuthModalProps {
  onClose: () => void;
  onSuccess: (user: UserType) => void;
  addToast: (type: 'success' | 'error', msg: string) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ onClose, onSuccess, addToast }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password) { setError('Username and password are required.'); return; }
    if (mode === 'register' && !email.trim()) { setError('Email is required.'); return; }

    setLoading(true);
    try {
      if (mode === 'register') {
        await registerUser(username, email, password);
      }
      const { access_token } = await loginUser(username, password);
      setStoredToken(access_token);
      const user = await getMe();
      onSuccess(user);
      addToast('success', `Welcome, ${user.username}!`);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="overlay fade-in">
      <div className="modal">
        <button className="btn btn-ghost" onClick={onClose}
          style={{ position: 'absolute', top: 16, right: 16 }}>
          <X size={18} />
        </button>

        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 20 }}>
          {mode === 'login' ? 'Access your job tracker board' : 'Start tracking your job applications'}
        </p>

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg)', borderRadius: 8, padding: 3, marginBottom: 20 }}>
          {(['login', 'register'] as const).map(m => (
            <button
              key={m}
              type="button"
              onClick={() => { setMode(m); setError(''); }}
              style={{
                flex: 1, padding: '6px 0', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontSize: '0.85rem', fontWeight: 600, transition: 'all 0.15s',
                background: mode === m ? 'var(--bg-card)' : 'transparent',
                color: mode === m ? 'var(--text)' : 'var(--text-muted)',
                boxShadow: mode === m ? 'var(--shadow)' : 'none',
              }}
            >
              {m === 'login' ? 'Sign in' : 'Register'}
            </button>
          ))}
        </div>

        {error && <div className="error-box" style={{ marginBottom: 16 }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label className="label">Username</label>
            <div style={{ position: 'relative' }}>
              <input className="input" type="text" placeholder="your_username"
                value={username} onChange={e => setUsername(e.target.value)}
                style={{ paddingLeft: 36 }} required />
              <User size={15} color="var(--text-dim)" style={{ position: 'absolute', left: 11, top: 10 }} />
            </div>
          </div>

          {mode === 'register' && (
            <div>
              <label className="label">Email</label>
              <div style={{ position: 'relative' }}>
                <input className="input" type="email" placeholder="you@email.com"
                  value={email} onChange={e => setEmail(e.target.value)}
                  style={{ paddingLeft: 36 }} required />
                <Mail size={15} color="var(--text-dim)" style={{ position: 'absolute', left: 11, top: 10 }} />
              </div>
            </div>
          )}

          <div>
            <label className="label">Password</label>
            <div style={{ position: 'relative' }}>
              <input className="input" type={showPass ? 'text' : 'password'} placeholder="••••••••"
                value={password} onChange={e => setPassword(e.target.value)}
                style={{ paddingLeft: 36, paddingRight: 36 }} required />
              <Lock size={15} color="var(--text-dim)" style={{ position: 'absolute', left: 11, top: 10 }} />
              <button type="button" className="btn btn-ghost"
                onClick={() => setShowPass(!showPass)}
                style={{ position: 'absolute', right: 6, top: 5, padding: 2 }}>
                {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          <button className="btn btn-primary" type="submit" disabled={loading}
            style={{ marginTop: 4, width: '100%', padding: '10px 0', justifyContent: 'center' }}>
            {loading ? 'Loading...' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  );
};
