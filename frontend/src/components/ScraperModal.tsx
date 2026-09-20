import React, { useState } from 'react';
import { X, Globe, Sparkles, CheckCircle2, ShieldCheck } from 'lucide-react';
import { previewJobUrl, confirmJobUrl } from '../api/client';
import type { ScrapePreview, ApplicationStatus } from '../api/client';
import { isValidUrl, sanitizeInput } from '../security/sanitizer';

interface ScraperModalProps {
  onClose: () => void;
  onSuccess: () => void;
  addToast: (type: 'success' | 'error', msg: string) => void;
}

export const ScraperModal: React.FC<ScraperModalProps> = ({ onClose, onSuccess, addToast }) => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<ScrapePreview | null>(null);
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState<ApplicationStatus>('APPLIED');
  const [error, setError] = useState('');

  const handleFetch = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!isValidUrl(url)) {
      setError('Enter a valid URL starting with http:// or https://');
      return;
    }
    setLoading(true);
    setPreview(null);
    try {
      const data = await previewJobUrl(url);
      setPreview(data);
    } catch (err: any) {
      setError(err.message || 'Could not scrape job page.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    if (!preview.company_name?.trim() || !preview.title?.trim()) {
      setError('Company name and job title are required.');
      return;
    }
    setLoading(true);
    try {
      await confirmJobUrl({
        job_url: preview.job_url,
        company_name: preview.company_name!,
        title: preview.title!,
        location: preview.location,
        description: preview.description,
        notes: sanitizeInput(notes) || null,
        status,
      });
      addToast('success', 'Application added to board!');
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to save application.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="overlay fade-in">
      <div className="modal" style={{ maxWidth: 520, maxHeight: '90vh', overflowY: 'auto' }}>
        <button className="btn btn-ghost" onClick={onClose} style={{ position: 'absolute', top: 16, right: 16 }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <Globe size={20} color="var(--blue)" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Add Job via URL</h2>
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 20 }}>
          Paste a job posting URL and we'll extract the details for you.
        </p>

        {/* URL Input */}
        <form onSubmit={handleFetch} style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input className="input" type="url" placeholder="https://..." value={url}
            onChange={e => setUrl(e.target.value)} required style={{ flex: 1 }} />
          <button className="btn btn-primary" type="submit" disabled={loading} style={{ flexShrink: 0 }}>
            {loading ? '...' : <><Sparkles size={14} /> Fetch</>}
          </button>
        </form>

        {error && <div className="error-box" style={{ marginBottom: 14 }}>{error}</div>}

        {/* Preview section */}
        {preview && (
          <div style={{ background: 'var(--bg)', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--green)', fontWeight: 600 }}>
              <CheckCircle2 size={14} /> Data extracted — review and confirm
            </div>

            <div>
              <label className="label">Job Title *</label>
              <input className="input" type="text" value={preview.title || ''}
                onChange={e => setPreview({ ...preview, title: e.target.value })} />
            </div>
            <div>
              <label className="label">Company Name *</label>
              <input className="input" type="text" value={preview.company_name || ''}
                onChange={e => setPreview({ ...preview, company_name: e.target.value })} />
            </div>
            <div>
              <label className="label">Location</label>
              <input className="input" type="text" value={preview.location || ''}
                onChange={e => setPreview({ ...preview, location: e.target.value })} />
            </div>
            <div>
              <label className="label">Status</label>
              <select className="input" value={status} onChange={e => setStatus(e.target.value as ApplicationStatus)}>
                <option value="APPLIED">Applied</option>
                <option value="INTERVIEWING">Interviewing</option>
                <option value="OFFERED">Offered</option>
                <option value="REJECTED">Rejected</option>
                <option value="WITHDRAWN">Withdrawn</option>
              </select>
            </div>
            <div>
              <label className="label">Notes (optional)</label>
              <textarea className="input" rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
            </div>

            <button className="btn btn-primary" onClick={handleConfirm} disabled={loading}
              style={{ width: '100%', justifyContent: 'center', padding: '10px 0' }}>
              {loading ? 'Saving...' : 'Save to Board'}
            </button>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 16, fontSize: '0.75rem', color: 'var(--text-dim)' }}>
          <ShieldCheck size={13} color="var(--green)" />
          URL validated — only http/https schemes allowed
        </div>
      </div>
    </div>
  );
};
