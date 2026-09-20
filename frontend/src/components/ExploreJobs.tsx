import React, { useState } from 'react';
import {
  Globe, MapPin, Plus, Check, Search, Compass, Briefcase, ArrowUpRight
} from 'lucide-react';
import type { Job, Company, EnrichedApplication } from '../api/client';

interface ExploreJobsProps {
  jobs: Job[];
  companies: Company[];
  userApplications: EnrichedApplication[];
  onTrackJob: (job: Job, company?: Company) => Promise<void>;
  addToast: (type: 'success' | 'error', msg: string) => void;
  isDemoMode?: boolean;
}

export const ExploreJobs: React.FC<ExploreJobsProps> = ({
  jobs,
  companies,
  userApplications,
  onTrackJob,
  addToast,
}) => {
  const [search, setSearch] = useState('');
  const [trackingJobId, setTrackingJobId] = useState<number | null>(null);

  // Map user's applied job_ids or job titles/company combinations
  const appliedJobIds = new Set(userApplications.map(a => a.job_id));
  const appliedTitlesAndCompanies = new Set(
    userApplications.map(a => `${(a.company?.name || '').toLowerCase()}:${(a.job?.title || '').toLowerCase()}`)
  );

  const filteredJobs = jobs.filter(j => {
    const q = search.toLowerCase();
    const company = companies.find(c => c.id === j.company_id);
    return (
      j.title.toLowerCase().includes(q) ||
      (j.location || '').toLowerCase().includes(q) ||
      (company?.name || '').toLowerCase().includes(q)
    );
  });

  // Group jobs company-wise
  const companyMap: Record<number, { company?: Company; jobs: Job[] }> = {};

  // First register known companies
  companies.forEach(c => {
    companyMap[c.id] = { company: c, jobs: [] };
  });

  // Populate jobs
  filteredJobs.forEach(j => {
    if (!companyMap[j.company_id]) {
      companyMap[j.company_id] = {
        company: { id: j.company_id, name: `Company #${j.company_id}`, website: null, industry: null, location: null, description: null },
        jobs: [],
      };
    }
    companyMap[j.company_id].jobs.push(j);
  });

  // Filter out company blocks with zero matching jobs
  const companyBlocks = Object.values(companyMap).filter(block => block.jobs.length > 0);

  const handleTrack = async (job: Job, company?: Company) => {
    setTrackingJobId(job.id);
    try {
      await onTrackJob(job, company);
    } catch (e: any) {
      addToast('error', e.message || 'Failed to track application');
    } finally {
      setTrackingJobId(null);
    }
  };

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const totalPages = Math.ceil(companyBlocks.length / pageSize) || 1;
  const paginatedBlocks = companyBlocks.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div style={{ padding: '24px 0 60px' }}>
      {/* Header Banner */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(236, 72, 153, 0.1) 100%)',
        border: '1px solid rgba(99, 102, 241, 0.25)',
        borderRadius: 'var(--radius-lg)',
        padding: '28px 32px',
        marginBottom: 28,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 20,
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'linear-gradient(135deg, #6366f1 0%, #3b82f6 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff'
            }}>
              <Compass size={18} />
            </div>
            <h2 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
              Company & Public Jobs Directory
            </h2>
          </div>
          <p style={{ color: 'var(--text-body)', fontSize: '0.9rem', maxWidth: 620, lineHeight: 1.5 }}>
            Browse open positions grouped company-wise across top tech organizations. View original apply URLs or add them directly to your personal tracker.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{
            background: 'var(--bg-inset)', padding: '10px 18px', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-glass)', textAlign: 'center'
          }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#38bdf8', fontFamily: 'var(--font-heading)' }}>
              {companies.length}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600 }}>Companies</div>
          </div>
          <div style={{
            background: 'var(--bg-inset)', padding: '10px 18px', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-glass)', textAlign: 'center'
          }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#34d399', fontFamily: 'var(--font-heading)' }}>
              {jobs.length}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600 }}>Open Jobs</div>
          </div>
        </div>
      </div>

      {/* Search Bar & Page Controls */}
      <div style={{
        display: 'flex', gap: 14, marginBottom: 28, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between',
        background: 'rgba(15, 22, 41, 0.65)', backdropFilter: 'blur(16px)',
        padding: '12px 20px', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-glass)'
      }}>
        <div style={{ position: 'relative', flexGrow: 1, maxWidth: 420 }}>
          <input
            className="input"
            placeholder="Search by job title, location, or company name..."
            value={search}
            onChange={e => { setSearch(e.target.value); setCurrentPage(1); }}
            style={{ paddingLeft: 40 }}
          />
          <Search size={16} color="var(--text-dim)" style={{ position: 'absolute', left: 14, top: 12 }} />
        </div>

        {/* Page Size Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Show:</span>
          <select
            className="input"
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
            style={{ width: 90, padding: '5px 10px', fontSize: '0.78rem' }}
          >
            <option value={5}>5 per page</option>
            <option value={10}>10 per page</option>
            <option value={25}>25 per page</option>
            <option value={50}>50 per page</option>
          </select>
        </div>
      </div>

      {/* Company Blocks List */}
      {companyBlocks.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 24px', background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-glass)'
        }}>
          <Briefcase size={36} color="var(--text-dim)" style={{ marginBottom: 12, opacity: 0.5 }} />
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', marginBottom: 6 }}>No Jobs Found</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>No public jobs or companies matching "{search}".</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          {paginatedBlocks.map(({ company, jobs: companyJobs }) => {
            const companyName = company?.name || 'Company';
            const companyInitials = companyName.slice(0, 2).toUpperCase();

            return (
              <div key={company?.id || companyName} className="acrylic-card" style={{ padding: 24 }}>
                {/* Company Header Block */}
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  paddingBottom: 16, marginBottom: 20, borderBottom: '1px solid var(--border-glass)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: 12,
                      background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.25) 0%, rgba(56, 189, 248, 0.15) 100%)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '1rem', fontWeight: 800, color: '#38bdf8',
                      boxShadow: '0 0 16px rgba(56, 189, 248, 0.15)',
                    }}>
                      {companyInitials}
                    </div>

                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-heading)' }}>
                          {companyName}
                        </h3>
                        {company?.website && (
                          <a
                            href={company.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: '#38bdf8', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 4 }}
                          >
                            <Globe size={13} /> {company.website.replace(/^https?:\/\//, '')}
                          </a>
                        )}
                      </div>
                      {company?.industry && (
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          {company.industry} {company.location ? `· ${company.location}` : ''}
                        </div>
                      )}
                    </div>
                  </div>

                  <span style={{
                    fontSize: '0.78rem', fontWeight: 700, color: '#38bdf8',
                    background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.3)',
                    borderRadius: 99, padding: '4px 12px',
                  }}>
                    {companyJobs.length} Open {companyJobs.length === 1 ? 'Role' : 'Roles'}
                  </span>
                </div>

                {/* Company Jobs Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
                  {companyJobs.map(job => {
                    const isAlreadyApplied = appliedJobIds.has(job.id) ||
                      appliedTitlesAndCompanies.has(`${companyName.toLowerCase()}:${job.title.toLowerCase()}`);

                    const existingApp = userApplications.find(a => a.job_id === job.id);

                    return (
                      <div
                        key={job.id}
                        style={{
                          background: 'var(--bg-inset)',
                          border: '1px solid var(--border-glass)',
                          borderRadius: 'var(--radius-md)',
                          padding: 18,
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          gap: 12,
                          transition: 'all 0.2s ease',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                            <h4 style={{
                              fontSize: '1rem', fontWeight: 700, color: '#ffffff',
                              lineHeight: 1.35, fontFamily: 'var(--font-heading)'
                            }}>
                              {job.title}
                            </h4>
                            {isAlreadyApplied ? (
                              <span className={`status-pill status-${existingApp?.status || 'APPLIED'}`} style={{ fontSize: '0.68rem', flexShrink: 0 }}>
                                <Check size={11} /> {existingApp?.status || 'Applied'}
                              </span>
                            ) : (
                              <span style={{
                                fontSize: '0.68rem', fontWeight: 700, color: '#34d399',
                                background: 'rgba(52, 211, 153, 0.12)', border: '1px solid rgba(52, 211, 153, 0.3)',
                                borderRadius: 99, padding: '2px 8px', flexShrink: 0
                              }}>
                                Open
                              </span>
                            )}
                          </div>

                          {job.location && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                              <MapPin size={12} color="var(--text-dim)" />
                              <span>{job.location}</span>
                            </div>
                          )}

                          {job.description && (
                            <p style={{
                              fontSize: '0.8rem', color: 'var(--text-dim)', lineHeight: 1.45,
                              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'
                            }}>
                              {job.description}
                            </p>
                          )}
                        </div>

                        {/* Action Footer */}
                        <div style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                          paddingTop: 12, borderTop: '1px solid rgba(255, 255, 255, 0.05)'
                        }}>
                          {job.job_url ? (
                            <a
                              href={job.job_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-secondary"
                              style={{ padding: '6px 12px', fontSize: '0.78rem' }}
                            >
                              Apply Directly <ArrowUpRight size={13} color="#38bdf8" />
                            </a>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>No URL attached</span>
                          )}

                          {isAlreadyApplied ? (
                            <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                              Already in Tracker
                            </span>
                          ) : (
                            <button
                              className="btn btn-primary"
                              disabled={trackingJobId === job.id}
                              onClick={() => handleTrack(job, company)}
                              style={{ padding: '6px 14px', fontSize: '0.78rem' }}
                            >
                              <Plus size={14} /> Track Application
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Footer Controls */}
      {companyBlocks.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginTop: 32, paddingTop: 20, borderTop: '1px solid var(--border-glass)'
        }}>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Showing page <strong>{currentPage}</strong> of <strong>{totalPages}</strong> ({companyBlocks.length} total companies)
          </span>

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              className="btn btn-secondary"
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              style={{ padding: '6px 16px', fontSize: '0.82rem' }}
            >
              Previous
            </button>
            <button
              className="btn btn-secondary"
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage(p => p + 1)}
              style={{ padding: '6px 16px', fontSize: '0.82rem' }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
