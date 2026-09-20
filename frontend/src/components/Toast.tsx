import React, { useEffect } from 'react';
import { CheckCircle2, XCircle, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error';
  message: string;
}

export const ToastContainer: React.FC<{
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}> = ({ toasts, onDismiss }) => (
  <div style={{
    position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
    display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none',
  }}>
    {toasts.map(t => <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />)}
  </div>
);

const ToastItem: React.FC<{ toast: ToastMessage; onDismiss: (id: string) => void }> = ({ toast, onDismiss }) => {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 4000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div className="fade-in" style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px',
      background: 'var(--bg-card)',
      border: `1px solid ${toast.type === 'success' ? 'rgba(34,197,94,.25)' : 'rgba(239,68,68,.25)'}`,
      borderRadius: 8,
      boxShadow: 'var(--shadow-md)',
      pointerEvents: 'auto',
      minWidth: 260, maxWidth: 360,
    }}>
      {toast.type === 'success'
        ? <CheckCircle2 size={16} color="var(--green)" style={{ flexShrink: 0 }} />
        : <XCircle size={16} color="var(--red)" style={{ flexShrink: 0 }} />
      }
      <span style={{ flex: 1, fontSize: '0.85rem', color: 'var(--text)' }}>{toast.message}</span>
      <button className="btn btn-ghost" style={{ flexShrink: 0 }} onClick={() => onDismiss(toast.id)}>
        <X size={13} />
      </button>
    </div>
  );
};
