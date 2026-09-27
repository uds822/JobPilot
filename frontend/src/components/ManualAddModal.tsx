import React, { useState } from 'react';
import { X, PlusCircle } from 'lucide-react';
import { createManualApplication, extractErrorMessage } from '../api/client';
import type { ApplicationStatus } from '../api/client';
import { sanitizeInput, isValidUrl } from '../security/sanitizer';

interface ManualAddModalProps {
  onClose: () => void;
  onSuccess: () => void;
  addToast: (type: 'success' | 'error', msg: string) => void;
}

export const ManualAddModal: React.FC<ManualAddModalProps> = ({ onClose, onSuccess, addToast }) => {
  const [companyName, setCompanyName] = useState('');
  const [title, setTitle] = useState('');
  const [location, setLocation] = useState('');
  const [jobUrl, setJobUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState<ApplicationStatus>('APPLIED');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!companyName.trim()) { setError('Company name is required.'); return; }
    if (!title.trim()) { setError('Job title is required.'); return; }
    if (jobUrl && !isValidUrl(jobUrl)) { setError('Please enter a valid URL (http:// or https://).'); return; }

    setLoading(true);
    try {
      await createManualApplication({
        company_name: sanitizeInput(companyName),
        title: sanitizeInput(title),
        location: location.trim() ? sanitizeInput(location) : null,
        job_url: jobUrl.trim() || null,
        notes: notes.trim() ? sanitizeInput(notes) : null,
        status,
      });
      addToast('success', 'Application created!');
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(extractErrorMessage(err, 'Failed to create application.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="overlay fade-in">
      <div className="modal" style={{ maxWidth: 460 }}>
        <button className="btn btn-ghost" onClick={onClose} style={{ position: 'absolute', top: 16, right: 16 }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <PlusCircle size={20} color="var(--blue)" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Add Application Manually</h2>
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 20 }}>
          Enter the job details directly into your tracker board.
        </p>

        {error && <div className="error-box" style={{ marginBottom: 14 }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label className="label">Company Name *</label>
            <input className="input" type="text" placeholder="e.g. Google, Meta..."
              value={companyName} onChange={e => setCompanyName(e.target.value)} required />
          </div>

          <div>
            <label className="label">Job Title *</label>
            <input className="input" type="text" placeholder="e.g. Senior Backend Engineer"
              value={title} onChange={e => setTitle(e.target.value)} required />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label className="label">Location</label>
              <input className="input" type="text" placeholder="Remote, New York..."
                value={location} onChange={e => setLocation(e.target.value)} />
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
          </div>

          <div>
            <label className="label">Job URL (optional)</label>
            <input className="input" type="url" placeholder="https://..."
              value={jobUrl} onChange={e => setJobUrl(e.target.value)} />
          </div>

          <div>
            <label className="label">Notes (optional)</label>
            <textarea className="input" rows={3} placeholder="Referral contact, compensation details..."
              value={notes} onChange={e => setNotes(e.target.value)} />
          </div>

          <button className="btn btn-primary" type="submit" disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '10px 0', marginTop: 4 }}>
            {loading ? 'Creating...' : 'Add to Board'}
          </button>
        </form>
      </div>
    </div>
  );
};
