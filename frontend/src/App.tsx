import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { KanbanBoard } from './components/KanbanBoard';
import { ScraperModal } from './components/ScraperModal';
import { ManualAddModal } from './components/ManualAddModal';
import { AuthModal } from './components/AuthModal';
import { AnalyticsDashboard } from './components/AnalyticsDashboard';
import { SecurityPanel } from './components/SecurityPanel';
import { ExploreJobs } from './components/ExploreJobs';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastContainer } from './components/Toast';
import type { ToastMessage } from './components/Toast';
import { DEMO_APPLICATIONS } from './data/demoData';
import {
  getMe,
  getMyApplications,
  getMyJobs,
  getMyCompanies,
  getJobs,
  getCompanies,
  createManualApplication,
  getStoredToken,
  clearStoredToken,
  setUnauthorizedHandler,
} from './api/client';
import type { User, EnrichedApplication, Job, Company } from './api/client';
import { Sparkles, Lock, LogIn, ArrowRight, Compass } from 'lucide-react';

type Tab = 'board' | 'explore' | 'scraper' | 'analytics' | 'security';

const App: React.FC = () => {
  const [tab, setTab] = useState<Tab>('board');
  const [user, setUser] = useState<User | null>(null);
  const [applications, setApplications] = useState<EnrichedApplication[]>([]);
  const [demoApps, setDemoApps] = useState<EnrichedApplication[]>(DEMO_APPLICATIONS);
  const [publicJobs, setPublicJobs] = useState<Job[]>([]);
  const [publicCompanies, setPublicCompanies] = useState<Company[]>([]);
  const [isDemoMode, setIsDemoMode] = useState<boolean>(true);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [isScraperOpen, setIsScraperOpen] = useState(false);
  const [isManualOpen, setIsManualOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [loading, setLoading] = useState(false);

  const addToast = useCallback((type: 'success' | 'error', message: string) => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts(prev => [...prev, { id, type, message }]);
  }, []);

  const removeToast = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const [apps, jobs, companies] = await Promise.all([
        getMyApplications(),
        getMyJobs().catch(() => [] as Awaited<ReturnType<typeof getMyJobs>>),
        getMyCompanies().catch(() => [] as Awaited<ReturnType<typeof getMyCompanies>>),
      ]);

      const jobMap: Record<number, (typeof jobs)[number]> = Object.fromEntries(jobs.map(j => [j.id, j]));
      const companyMap: Record<number, (typeof companies)[number]> = Object.fromEntries(companies.map(c => [c.id, c]));

      const enriched: EnrichedApplication[] = apps.map(app => {
        const job = jobMap[app.job_id];
        const company = job ? companyMap[job.company_id] : undefined;
        return { ...app, job, company };
      });

      setApplications(enriched);
    } catch (err: any) {
      addToast('error', err.message || 'Failed to load applications.');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  const fetchPublicDirectory = useCallback(async () => {
    try {
      const [jobsData, companiesData] = await Promise.all([
        getJobs().catch(() => []),
        getCompanies().catch(() => []),
      ]);
      setPublicJobs(jobsData);
      setPublicCompanies(companiesData);
    } catch (e) {
      console.warn('Could not fetch public directory:', e);
    }
  }, []);

  // On mount: check token and restore session
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setApplications([]);
      setIsDemoMode(true);
      addToast('error', 'Session expired. Switched to Demo Mode.');
    });

    fetchPublicDirectory();

    const token = getStoredToken();
    if (token) {
      getMe()
        .then(u => {
          setUser(u);
          setIsDemoMode(false);
          fetchApplications();
        })
        .catch(() => {
          clearStoredToken();
          setIsDemoMode(true);
        });
    } else {
      setIsDemoMode(true);
    }
  }, [addToast, fetchApplications, fetchPublicDirectory]);

  const handleLogout = () => {
    clearStoredToken();
    setUser(null);
    setApplications([]);
    setIsDemoMode(true);
    addToast('success', 'Signed out. Switched to Demo Mode.');
  };

  const handleAuthSuccess = (u: User) => {
    setUser(u);
    setIsDemoMode(false);
    setIsAuthOpen(false);
    fetchApplications();
    fetchPublicDirectory();
    addToast('success', `Welcome back, ${u.username}! Loaded your applications.`);
  };

  // Track a job from Explore Jobs directory
  const handleTrackJob = async (job: Job, company?: Company) => {
    if (isDemoMode) {
      const newDemoApp: EnrichedApplication = {
        id: Math.floor(Math.random() * 1000) + 500,
        user_id: 999,
        job_id: job.id,
        status: 'APPLIED',
        applied_at: new Date().toISOString(),
        notes: 'Added from Explore Jobs directory',
        job: job,
        company: company || { id: job.company_id, name: `Company #${job.company_id}`, website: null, industry: null, location: null, description: null },
      };
      setDemoApps(prev => [newDemoApp, ...prev]);
      addToast('success', `Added "${job.title}" to your Kanban board (Demo Mode)!`);
      return;
    }

    try {
      await createManualApplication({
        company_name: company?.name || 'Company',
        title: job.title,
        location: job.location,
        description: job.description,
        job_url: job.job_url,
        status: 'APPLIED',
        notes: 'Added from Explore Jobs directory',
      });
      await fetchApplications();
      addToast('success', `Tracked "${job.title}"! Added to your Board.`);
    } catch (e: any) {
      addToast('error', e.message || 'Failed to track application.');
    }
  };

  // Demo mode local state mutators
  const handleUpdateDemoApp = (id: number, updates: Partial<EnrichedApplication>) => {
    setDemoApps(prev => prev.map(a => a.id === id ? { ...a, ...updates } : a));
  };

  const handleDeleteDemoApp = (id: number) => {
    setDemoApps(prev => prev.filter(a => a.id !== id));
  };

  // Demo mode is ONLY for unauthenticated outsiders
  const isEffectiveDemoMode = isDemoMode && !user;
  const currentApps = user ? applications : (isEffectiveDemoMode ? demoApps : []);

  // Fallback demo dataset for public jobs/companies if backend returns empty or in demo mode
  const effectivePublicJobs = publicJobs.length > 0 ? publicJobs : (isEffectiveDemoMode ? demoApps.map(a => a.job!).filter(Boolean) : []);
  const effectivePublicCompanies = publicCompanies.length > 0 ? publicCompanies : (isEffectiveDemoMode ? demoApps.map(a => a.company!).filter(Boolean) : []);

  return (
    <ErrorBoundary>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Navbar
          activeTab={tab}
          setActiveTab={setTab}
          user={user}
          isDemoMode={isEffectiveDemoMode}
          onToggleDemoMode={() => {
            if (user) return;
            const nextMode = !isDemoMode;
            setIsDemoMode(nextMode);
            addToast('success', nextMode ? 'Switched to Demo Mode (Sample Data).' : 'Switched to Live Data Mode.');
          }}
          onOpenAuth={() => setIsAuthOpen(true)}
          onLogout={handleLogout}
        />

        {/* Demo Mode Banner (ONLY for unauthenticated outsiders) */}
        {isEffectiveDemoMode && (
          <div style={{
            background: 'linear-gradient(90deg, rgba(251, 191, 36, 0.15) 0%, rgba(99, 102, 241, 0.15) 100%)',
            borderBottom: '1px solid rgba(251, 191, 36, 0.3)',
            padding: '10px 24px',
            fontSize: '0.83rem',
            color: '#fbbf24',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Sparkles size={14} color="#fbbf24" />
              <span><strong>Demo Mode Active:</strong> You are exploring with sample data. Sign in to save real applications.</span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                className="btn btn-primary"
                onClick={() => setIsAuthOpen(true)}
                style={{ padding: '3px 12px', fontSize: '0.78rem', height: 26 }}
              >
                Sign In / Register <ArrowRight size={12} />
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setIsDemoMode(false)}
                style={{ padding: '3px 10px', fontSize: '0.78rem', height: 26 }}
              >
                Exit Demo
              </button>
            </div>
          </div>
        )}

        <main style={{ flex: 1, maxWidth: 1300, width: '100%', margin: '0 auto', padding: '0 24px' }}>
          
          {/* BOARD TAB */}
          {tab === 'board' && (
            !isDemoMode && !user ? (
              <div style={{
                textAlign: 'center', padding: '80px 24px',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
              }}>
                <div style={{
                  width: 56, height: 56, borderRadius: '50%', background: 'rgba(99, 102, 241, 0.1)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(99, 102, 241, 0.3)'
                }}>
                  <LogIn size={24} color="#6366f1" />
                </div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Sign in to track your job applications</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', maxWidth: 460 }}>
                  Log in to manage your private application pipeline, or toggle Demo Mode to explore sample features.
                </p>
                <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                  <button className="btn btn-primary" onClick={() => setIsAuthOpen(true)} style={{ padding: '10px 24px' }}>
                    Sign in / Register
                  </button>
                  <button className="btn btn-secondary" onClick={() => setIsDemoMode(true)} style={{ padding: '10px 20px' }}>
                    <Sparkles size={15} color="#fbbf24" /> Launch Demo Mode
                  </button>
                </div>
              </div>
            ) : (
              <div>
                {loading && !isDemoMode && (
                  <div style={{ padding: '12px 0', fontSize: '0.82rem', color: 'var(--text-dim)', textAlign: 'center' }}>
                    Loading your applications from backend...
                  </div>
                )}
                <KanbanBoard
                  applications={currentApps}
                  onRefresh={fetchApplications}
                  onOpenScraper={() => setIsScraperOpen(true)}
                  onOpenManual={() => setIsManualOpen(true)}
                  addToast={addToast}
                  isDemoMode={isDemoMode}
                  onUpdateDemoApp={handleUpdateDemoApp}
                  onDeleteDemoApp={handleDeleteDemoApp}
                />
              </div>
            )
          )}

          {/* EXPLORE JOBS TAB (AUTH GATED / DEMO ALLOWED) */}
          {tab === 'explore' && (
            !user && !isDemoMode ? (
              <div style={{
                maxWidth: 520, margin: '60px auto', padding: '40px 32px', textAlign: 'center',
                background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: 'var(--radius-lg)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              }}>
                <div style={{
                  width: 60, height: 60, borderRadius: '50%',
                  background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#38bdf8',
                }}>
                  <Compass size={28} />
                </div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ffffff' }}>
                  Explore Open Jobs & Company Directory
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', lineHeight: 1.6 }}>
                  Sign in or register to browse open roles across top tech companies, view direct application URLs, and track jobs onto your Kanban board.
                </p>
                <div style={{ display: 'flex', gap: 12, width: '100%', marginTop: 8 }}>
                  <button className="btn btn-primary" onClick={() => setIsAuthOpen(true)} style={{ flex: 1, justifyContent: 'center' }}>
                    <LogIn size={16} /> Sign In to Explore Jobs
                  </button>
                  <button className="btn btn-secondary" onClick={() => setIsDemoMode(true)}>
                    <Sparkles size={15} color="#fbbf24" /> Try Demo Directory
                  </button>
                </div>
              </div>
            ) : (
              <ExploreJobs
                jobs={effectivePublicJobs}
                companies={effectivePublicCompanies}
                userApplications={currentApps}
                onTrackJob={handleTrackJob}
                addToast={addToast}
                isDemoMode={isDemoMode}
              />
            )
          )}

          {/* ANALYTICS TAB */}
          {tab === 'analytics' && (
            !isDemoMode && !user ? (
              <div style={{ textAlign: 'center', padding: '80px 24px' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: 8 }}>Analytics Access</h3>
                <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>Sign in to view your application metrics, or view demo analytics.</p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
                  <button className="btn btn-primary" onClick={() => setIsAuthOpen(true)}>Sign in</button>
                  <button className="btn btn-secondary" onClick={() => setIsDemoMode(true)}>
                    <Sparkles size={15} color="#fbbf24" /> Demo Analytics
                  </button>
                </div>
              </div>
            ) : (
              <AnalyticsDashboard applications={currentApps} />
            )
          )}

          {/* URL SCRAPER TAB */}
          {tab === 'scraper' && (
            !user && !isDemoMode ? (
              <div style={{ textAlign: 'center', padding: '80px 24px' }}>
                <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>Sign in to use the URL scraper.</p>
                <button className="btn btn-primary" onClick={() => setIsAuthOpen(true)}>Sign in</button>
              </div>
            ) : (
              <ScraperModal
                onClose={() => setTab('board')}
                onSuccess={fetchApplications}
                addToast={addToast}
              />
            )
          )}

          {/* SECURITY TAB - STRICTLY AUTH GATED */}
          {tab === 'security' && (
            !user ? (
              <div style={{
                maxWidth: 520, margin: '60px auto', padding: '40px 32px', textAlign: 'center',
                background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: 'var(--radius-lg)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              }}>
                <div style={{
                  width: 60, height: 60, borderRadius: '50%',
                  background: 'rgba(251, 113, 133, 0.12)', border: '1px solid rgba(251, 113, 133, 0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fb7185',
                }}>
                  <Lock size={28} />
                </div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#ffffff' }}>
                  Authentication Required
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', lineHeight: 1.6 }}>
                  The Security Dashboard displays confidential system integrity diagnostics, live rate limit thresholds, and XSS sanitizer configurations. Access is restricted to authenticated user sessions.
                </p>
                <button
                  className="btn btn-primary"
                  onClick={() => setIsAuthOpen(true)}
                  style={{ marginTop: 8, padding: '10px 28px', width: '100%', justifyContent: 'center' }}
                >
                  <LogIn size={16} /> Sign In to Access Security Panel
                </button>
              </div>
            ) : (
              <SecurityPanel />
            )
          )}
        </main>

        {/* Modals */}
        {isAuthOpen && (
          <AuthModal
            onClose={() => setIsAuthOpen(false)}
            onSuccess={handleAuthSuccess}
            addToast={addToast}
          />
        )}
        {isScraperOpen && (user || isDemoMode) && tab === 'board' && (
          <ScraperModal
            onClose={() => setIsScraperOpen(false)}
            onSuccess={() => {
              if (isDemoMode) {
                addToast('success', 'Job scraped (Demo Mode simulation).');
              } else {
                fetchApplications();
              }
              setIsScraperOpen(false);
            }}
            addToast={addToast}
          />
        )}
        {isManualOpen && (user || isDemoMode) && (
          <ManualAddModal
            onClose={() => setIsManualOpen(false)}
            onSuccess={() => {
              if (isDemoMode) {
                addToast('success', 'Manual entry created (Demo Mode simulation).');
              } else {
                fetchApplications();
              }
              setIsManualOpen(false);
            }}
            addToast={addToast}
          />
        )}

        <ToastContainer toasts={toasts} onDismiss={removeToast} />

        {/* Footer */}
        <footer style={{
          borderTop: '1px solid var(--border-glass)',
          padding: '16px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: '0.78rem', color: 'var(--text-dim)',
          marginTop: 40,
        }}>
          <span>JobPilot · Company Directory & Application Tracker</span>
          <span>Public Endpoints: GET /jobs, GET /companies | Auth-Gated User Pipeline</span>
        </footer>
      </div>
    </ErrorBoundary>
  );
};

export default App;
