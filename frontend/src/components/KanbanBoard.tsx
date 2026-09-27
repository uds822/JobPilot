import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Globe, Building2, MapPin, Calendar, ExternalLink, Trash2, Pencil, Check, X, Search,
  Briefcase, ChevronRight, ArrowUpRight, Loader2, RefreshCw
} from 'lucide-react';
import type { ApplicationStatus, EnrichedApplication, Job, Company } from '../api/client';
import {
  getKanbanBoard,
  getApplicationsPaginated,
  updateApplication,
  deleteApplication,
  deleteApplicationsBulk,
  getMyJobs,
  getMyCompanies,
  extractErrorMessage
} from '../api/client';
import { sanitizeInput } from '../security/sanitizer';

const COLUMNS: { id: ApplicationStatus; label: string; accent: string; glow: string }[] = [
  { id: 'APPLIED', label: 'Applied', accent: '#38bdf8', glow: 'rgba(56, 189, 248, 0.25)' },
  { id: 'INTERVIEWING', label: 'Interviewing', accent: '#fbbf24', glow: 'rgba(251, 191, 36, 0.25)' },
  { id: 'OFFERED', label: 'Offered', accent: '#34d399', glow: 'rgba(52, 211, 153, 0.25)' },
  { id: 'REJECTED', label: 'Rejected', accent: '#fb7185', glow: 'rgba(251, 113, 133, 0.25)' },
  { id: 'WITHDRAWN', label: 'Withdrawn', accent: '#c084fc', glow: 'rgba(192, 132, 252, 0.25)' },
];

const STATUS_THEMES: Record<ApplicationStatus, { text: string; bg: string; border: string; accent: string }> = {
  APPLIED: { text: '#38bdf8', bg: 'rgba(56, 189, 248, 0.12)', border: 'rgba(56, 189, 248, 0.3)', accent: '#38bdf8' },
  INTERVIEWING: { text: '#fbbf24', bg: 'rgba(251, 191, 36, 0.12)', border: 'rgba(251, 191, 36, 0.3)', accent: '#fbbf24' },
  OFFERED: { text: '#34d399', bg: 'rgba(52, 211, 153, 0.12)', border: 'rgba(52, 211, 153, 0.3)', accent: '#34d399' },
  REJECTED: { text: '#fb7185', bg: 'rgba(251, 113, 133, 0.12)', border: 'rgba(251, 113, 133, 0.3)', accent: '#fb7185' },
  WITHDRAWN: { text: '#c084fc', bg: 'rgba(192, 132, 252, 0.12)', border: 'rgba(192, 132, 252, 0.3)', accent: '#c084fc' },
};

function getCompanyInitials(name?: string | null): string {
  if (!name) return 'JP';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

interface ColumnDataState {
  items: EnrichedApplication[];
  total: number;
  offset: number;
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
}

type KanbanColumnsState = Record<ApplicationStatus, ColumnDataState>;

interface KanbanBoardProps {
  applications: EnrichedApplication[];
  onRefresh: () => void;
  onOpenScraper: () => void;
  onOpenManual: () => void;
  addToast: (type: 'success' | 'error', msg: string) => void;
  isDemoMode?: boolean;
  onUpdateDemoApp?: (id: number, updates: Partial<EnrichedApplication>) => void;
  onDeleteDemoApp?: (id: number) => void;
}

const initialColumnState = (): ColumnDataState => ({
  items: [],
  total: 0,
  offset: 0,
  hasMore: false,
  loading: true,
  loadingMore: false,
  error: null,
});

export const KanbanBoard: React.FC<KanbanBoardProps> = ({
  applications, onRefresh, onOpenScraper, onOpenManual, addToast,
  isDemoMode, onUpdateDemoApp, onDeleteDemoApp,
}) => {
  const [search, setSearch] = useState('');
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectedApp, setSelectedApp] = useState<EnrichedApplication | null>(null);
  const [editingNotesInModal, setEditingNotesInModal] = useState(false);
  const [modalNotesText, setModalNotesText] = useState('');

  // Per-column paginated state
  const [columnsState, setColumnsState] = useState<KanbanColumnsState>({
    APPLIED: initialColumnState(),
    INTERVIEWING: initialColumnState(),
    OFFERED: initialColumnState(),
    REJECTED: initialColumnState(),
    WITHDRAWN: initialColumnState(),
  });

  // Cached jobs/companies maps for enriching paginated records
  const [jobMapState, setJobMapState] = useState<Record<number, Job>>({});
  const [companyMapState, setCompanyMapState] = useState<Record<number, Company>>({});

  // Helper to enrich applications with job & company details
  const enrichItems = useCallback(
    (items: any[], jobMap: Record<number, Job>, companyMap: Record<number, Company>): EnrichedApplication[] => {
      return items.map(app => {
        const job = jobMap[app.job_id];
        const company = job ? companyMap[job.company_id] : undefined;
        return { ...app, job, company };
      });
    },
    []
  );

  // Load live kanban board data from backend
  const fetchLiveKanbanBoard = useCallback(async () => {
    if (isDemoMode) return;

    // Set loading for all columns
    setColumnsState(prev => {
      const next = { ...prev };
      COLUMNS.forEach(c => {
        next[c.id] = { ...next[c.id], loading: true, error: null };
      });
      return next;
    });

    try {
      const [boardData, jobs, companies] = await Promise.all([
        getKanbanBoard(20),
        getMyJobs().catch(() => [] as Job[]),
        getMyCompanies().catch(() => [] as Company[]),
      ]);

      const jMap: Record<number, Job> = Object.fromEntries(jobs.map(j => [j.id, j]));
      const cMap: Record<number, Company> = Object.fromEntries(companies.map(c => [c.id, c]));
      setJobMapState(jMap);
      setCompanyMapState(cMap);

      const updatedColumns: KanbanColumnsState = {
        APPLIED: {
          items: enrichItems(boardData.applied.items, jMap, cMap),
          total: boardData.applied.total,
          offset: boardData.applied.offset,
          hasMore: boardData.applied.has_more,
          loading: false,
          loadingMore: false,
          error: null,
        },
        INTERVIEWING: {
          items: enrichItems(boardData.interviewing.items, jMap, cMap),
          total: boardData.interviewing.total,
          offset: boardData.interviewing.offset,
          hasMore: boardData.interviewing.has_more,
          loading: false,
          loadingMore: false,
          error: null,
        },
        OFFERED: {
          items: enrichItems(boardData.offered.items, jMap, cMap),
          total: boardData.offered.total,
          offset: boardData.offered.offset,
          hasMore: boardData.offered.has_more,
          loading: false,
          loadingMore: false,
          error: null,
        },
        REJECTED: {
          items: enrichItems(boardData.rejected.items, jMap, cMap),
          total: boardData.rejected.total,
          offset: boardData.rejected.offset,
          hasMore: boardData.rejected.has_more,
          loading: false,
          loadingMore: false,
          error: null,
        },
        WITHDRAWN: {
          items: enrichItems(boardData.withdrawn.items, jMap, cMap),
          total: boardData.withdrawn.total,
          offset: boardData.withdrawn.offset,
          hasMore: boardData.withdrawn.has_more,
          loading: false,
          loadingMore: false,
          error: null,
        },
      };

      setColumnsState(updatedColumns);
    } catch (err: any) {
      const errMsg = extractErrorMessage(err, 'Failed to load applications');
      setColumnsState(prev => {
        const next = { ...prev };
        COLUMNS.forEach(c => {
          next[c.id] = { ...next[c.id], loading: false, error: errMsg };
        });
        return next;
      });
    }
  }, [isDemoMode, enrichItems]);

  // Sync state when props change or component mounts
  useEffect(() => {
    if (isDemoMode) {
      // In demo mode, derive column state directly from applications prop
      const demoState: KanbanColumnsState = {
        APPLIED: initialColumnState(),
        INTERVIEWING: initialColumnState(),
        OFFERED: initialColumnState(),
        REJECTED: initialColumnState(),
        WITHDRAWN: initialColumnState(),
      };

      COLUMNS.forEach(col => {
        const colApps = applications.filter(a => a.status === col.id);
        demoState[col.id] = {
          items: colApps,
          total: colApps.length,
          offset: 0,
          hasMore: false,
          loading: false,
          loadingMore: false,
          error: null,
        };
      });

      setColumnsState(demoState);
    } else {
      fetchLiveKanbanBoard();
    }
  }, [isDemoMode, applications, fetchLiveKanbanBoard]);

  // Load next page of applications for a specific column
  const handleLoadMoreColumn = async (status: ApplicationStatus) => {
    const colState = columnsState[status];
    if (colState.loadingMore || !colState.hasMore) return;

    setColumnsState(prev => ({
      ...prev,
      [status]: { ...prev[status], loadingMore: true, error: null },
    }));

    try {
      const nextOffset = colState.items.length;
      const res = await getApplicationsPaginated(status, nextOffset, 20);
      const newEnriched = enrichItems(res.items, jobMapState, companyMapState);

      setColumnsState(prev => {
        const existing = prev[status];
        // Filter out duplicate IDs if any
        const existingIds = new Set(existing.items.map(i => i.id));
        const filteredNew = newEnriched.filter(i => !existingIds.has(i.id));

        return {
          ...prev,
          [status]: {
            ...existing,
            items: [...existing.items, ...filteredNew],
            total: res.total,
            offset: res.offset,
            hasMore: res.has_more,
            loadingMore: false,
          },
        };
      });
    } catch (err: any) {
      const errMsg = extractErrorMessage(err, `Failed to load more ${status.toLowerCase()} applications.`);
      setColumnsState(prev => ({
        ...prev,
        [status]: { ...prev[status], loadingMore: false, error: errMsg },
      }));
      addToast('error', errMsg);
    }
  };

  // Optimistic status update with error rollback
  const handleStatusChange = async (id: number, targetStatus: ApplicationStatus, currentStatus: ApplicationStatus) => {
    if (targetStatus === currentStatus) return;

    // Locate app object
    const sourceCol = columnsState[currentStatus];
    const appToMove = sourceCol.items.find(a => a.id === id);
    if (!appToMove) return;

    const updatedApp: EnrichedApplication = { ...appToMove, status: targetStatus };

    // Optimistic UI update
    setColumnsState(prev => {
      const sourceItems = prev[currentStatus].items.filter(a => a.id !== id);
      const targetItems = [updatedApp, ...prev[targetStatus].items];

      return {
        ...prev,
        [currentStatus]: {
          ...prev[currentStatus],
          items: sourceItems,
          total: Math.max(0, prev[currentStatus].total - 1),
        },
        [targetStatus]: {
          ...prev[targetStatus],
          items: targetItems,
          total: prev[targetStatus].total + 1,
        },
      };
    });

    if (selectedApp && selectedApp.id === id) {
      setSelectedApp(updatedApp);
    }

    if (isDemoMode && onUpdateDemoApp) {
      onUpdateDemoApp(id, { status: targetStatus });
      addToast('success', `Moved to ${targetStatus} (Demo Mode).`);
      return;
    }

    setLoadingId(id);
    try {
      await updateApplication(id, { status: targetStatus });
      addToast('success', `Moved application to ${targetStatus}.`);
    } catch (e: any) {
      // Rollback optimistic update
      setColumnsState(prev => {
        const revertedSourceItems = [appToMove, ...prev[currentStatus].items.filter(a => a.id !== id)];
        const revertedTargetItems = prev[targetStatus].items.filter(a => a.id !== id);

        return {
          ...prev,
          [currentStatus]: {
            ...prev[currentStatus],
            items: revertedSourceItems,
            total: prev[currentStatus].total + 1,
          },
          [targetStatus]: {
            ...prev[targetStatus],
            items: revertedTargetItems,
            total: Math.max(0, prev[targetStatus].total - 1),
          },
        };
      });

      if (selectedApp && selectedApp.id === id) {
        setSelectedApp(appToMove);
      }

      addToast('error', extractErrorMessage(e, 'Failed to update status.'));
    } finally {
      setLoadingId(null);
    }
  };

  const handleSaveModalNotes = async (id: number) => {
    const cleanNotes = sanitizeInput(modalNotesText) || null;
    if (isDemoMode && onUpdateDemoApp) {
      onUpdateDemoApp(id, { notes: cleanNotes });
      setSelectedApp(prev => prev ? { ...prev, notes: cleanNotes } : null);
      setEditingNotesInModal(false);
      addToast('success', 'Notes saved (Demo Mode).');
      return;
    }

    setLoadingId(id);
    try {
      await updateApplication(id, { notes: cleanNotes });
      setSelectedApp(prev => prev ? { ...prev, notes: cleanNotes } : null);

      // Update notes in local columnsState
      setColumnsState(prev => {
        const next = { ...prev };
        COLUMNS.forEach(col => {
          next[col.id] = {
            ...next[col.id],
            items: next[col.id].items.map(a => a.id === id ? { ...a, notes: cleanNotes } : a),
          };
        });
        return next;
      });

      setEditingNotesInModal(false);
      addToast('success', 'Notes saved.');
    } catch (e: any) {
      addToast('error', extractErrorMessage(e, 'Failed to save notes.'));
    } finally {
      setLoadingId(null);
    }
  };

  const handleDelete = async (id: number, currentStatus: ApplicationStatus, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!confirm('Delete this application entry?')) return;

    // Optimistically remove from state
    setColumnsState(prev => {
      const col = prev[currentStatus];
      return {
        ...prev,
        [currentStatus]: {
          ...col,
          items: col.items.filter(a => a.id !== id),
          total: Math.max(0, col.total - 1),
        },
      };
    });

    if (selectedApp?.id === id) setSelectedApp(null);
    setSelectedIds(previous => {
      const next = new Set(previous);
      next.delete(id);
      return next;
    });

    if (isDemoMode && onDeleteDemoApp) {
      onDeleteDemoApp(id);
      addToast('success', 'Deleted entry (Demo Mode).');
      return;
    }

    setLoadingId(id);
    try {
      await deleteApplication(id);
      addToast('success', 'Deleted application entry.');
      onRefresh();
    } catch (e: any) {
      addToast('error', extractErrorMessage(e, 'Failed to delete entry.'));
      fetchLiveKanbanBoard(); // reload to restore consistency
    } finally {
      setLoadingId(null);
    }
  };

  const loadedApplicationIds = COLUMNS.flatMap(column =>
    columnsState[column.id].items.map(application => application.id)
  );

  const allLoadedSelected = loadedApplicationIds.length > 0 &&
    loadedApplicationIds.every(id => selectedIds.has(id));

  const toggleApplicationSelection = (id: number) => {
    setSelectedIds(previous => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAllLoaded = () => {
    setSelectedIds(previous => {
      const next = new Set(previous);
      if (allLoadedSelected) {
        loadedApplicationIds.forEach(id => next.delete(id));
      } else {
        loadedApplicationIds.forEach(id => next.add(id));
      }
      return next;
    });
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0 || isBulkDeleting) return;

    if (!confirm(`Delete ${ids.length} selected application${ids.length === 1 ? '' : 's'}?`)) {
      return;
    }

    if (isDemoMode && onDeleteDemoApp) {
      ids.forEach(id => onDeleteDemoApp(id));
      setSelectedIds(new Set());
      setSelectedApp(null);
      addToast('success', 'Selected applications deleted (Demo Mode).');
      return;
    }

    setIsBulkDeleting(true);
    try {
      await deleteApplicationsBulk(ids);
      setSelectedIds(new Set());
      setSelectedApp(null);
      addToast('success', 'Selected applications deleted.');
      await fetchLiveKanbanBoard();
      onRefresh();
    } catch (e: any) {
      addToast('error', extractErrorMessage(e, 'Failed to delete selected applications.'));
    } finally {
      setIsBulkDeleting(false);
    }
  };

  return (
    <div style={{ padding: '20px 0 40px' }}>
      {/* Action Toolbar */}
      <div style={{
        display: 'flex', gap: 14, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between',
        background: 'rgba(15, 22, 41, 0.65)', backdropFilter: 'blur(16px)',
        padding: '12px 20px', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-glass)'
      }}>
        <div style={{ position: 'relative', flexGrow: 1, maxWidth: 400 }}>
          <input
            className="input"
            placeholder="Filter loaded applications by role, company, location..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ paddingLeft: 38 }}
          />
          <Search size={15} color="var(--text-dim)" style={{ position: 'absolute', left: 13, top: 12 }} />
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--text-body)', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
            <input
              type="checkbox"
              checked={allLoadedSelected}
              onChange={toggleSelectAllLoaded}
              disabled={loadedApplicationIds.length === 0 || isBulkDeleting}
            />
            Select all loaded
          </label>
          {selectedIds.size > 0 && (
            <button className="btn btn-danger" onClick={handleBulkDelete} disabled={isBulkDeleting}>
              {isBulkDeleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
              Delete selected ({selectedIds.size})
            </button>
          )}
          <button className="btn btn-secondary" onClick={onOpenScraper}>
            <Globe size={15} color="#38bdf8" /> Add via URL
          </button>
          <button className="btn btn-primary" onClick={onOpenManual}>
            <Plus size={15} /> Manual Application
          </button>
        </div>
      </div>

      {/* Kanban Board Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 18,
        alignItems: 'start',
        overflowX: 'auto',
        paddingBottom: 16,
      }}>
        {COLUMNS.map(col => {
          const colState = columnsState[col.id];
          const theme = STATUS_THEMES[col.id];
          const query = search.trim().toLowerCase();

          const colApps = colState.items.filter(app => {
            if (!query) return true;
            return (
              (app.job?.title || '').toLowerCase().includes(query) ||
              (app.company?.name || '').toLowerCase().includes(query) ||
              (app.job?.location || '').toLowerCase().includes(query)
            );
          });

          return (
            <div key={col.id} style={{ minWidth: 240 }}>
              {/* Column Header */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: 14, padding: '10px 14px',
                background: 'rgba(15, 22, 41, 0.75)',
                backdropFilter: 'blur(12px)',
                border: `1px solid ${theme.border}`,
                borderRadius: 'var(--radius-md)',
                boxShadow: `0 4px 16px ${col.glow}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%', background: theme.accent,
                    boxShadow: `0 0 10px ${theme.accent}`,
                  }} />
                  <span style={{
                    fontSize: '0.82rem', fontWeight: 800, color: '#ffffff',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                    fontFamily: 'var(--font-heading)'
                  }}>
                    {col.label}
                  </span>
                </div>
                <span style={{
                  fontSize: '0.74rem', fontWeight: 800, color: theme.text,
                  background: theme.bg, border: `1px solid ${theme.border}`,
                  borderRadius: 99, padding: '2px 9px',
                }}>
                  {colState.total}
                </span>
              </div>

              {/* Controlled Column Scroll Container (Max Height: 720px) */}
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                maxHeight: 720,
                overflowY: 'auto',
                paddingRight: 4,
              }}>
                {colState.loading ? (
                  /* Initial Loading Skeleton State */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12, textAlign: 'center', color: 'var(--text-dim)' }}>
                    <div style={{ height: 120, background: 'rgba(255, 255, 255, 0.03)', borderRadius: 8, border: '1px solid var(--border-glass)' }} />
                    <div style={{ height: 120, background: 'rgba(255, 255, 255, 0.02)', borderRadius: 8, border: '1px solid var(--border-glass)' }} />
                  </div>
                ) : colApps.length === 0 ? (
                  /* Empty State */
                  <div style={{
                    height: 130, border: '1px dashed var(--border-glass)', borderRadius: 'var(--radius-md)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    gap: 6, fontSize: '0.78rem', color: 'var(--text-dim)', background: 'rgba(8, 12, 24, 0.4)'
                  }}>
                    <Briefcase size={22} opacity={0.35} />
                    <span>{query ? 'No matching apps' : 'No applications'}</span>
                  </div>
                ) : colApps.map(app => {
                  const companyInitials = getCompanyInitials(app.company?.name);

                  return (
                    /* STRICT Uniform Card (245px Height) — Midnight Acrylic Style */
                    <div
                      key={app.id}
                      className="acrylic-card acrylic-card-hover"
                      onClick={() => {
                        setSelectedApp(app);
                        setModalNotesText(app.notes || '');
                        setEditingNotesInModal(false);
                      }}
                      style={{
                        height: 245,
                        width: '100%',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        opacity: loadingId === app.id ? 0.5 : 1,
                        cursor: 'pointer',
                        position: 'relative',
                        boxSizing: 'border-box',
                        borderLeft: `4px solid ${theme.accent}`,
                        flexShrink: 0,
                      }}
                    >
                      {/* Top Row: Company Avatar + Name + Status Pill */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                          <input
                            type="checkbox"
                            checked={selectedIds.has(app.id)}
                            onChange={() => toggleApplicationSelection(app.id)}
                            onClick={e => e.stopPropagation()}
                            aria-label={`Select ${app.job?.title || 'application'}`}
                          />
                          <div style={{
                            width: 32, height: 32, borderRadius: '50%',
                            background: `linear-gradient(135deg, ${theme.bg} 0%, rgba(255, 255, 255, 0.05) 100%)`,
                            border: `1px solid ${theme.border}`,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.75rem', fontWeight: 800, color: theme.text,
                            flexShrink: 0,
                            boxShadow: `0 0 10px ${col.glow}`,
                          }}>
                            {companyInitials}
                          </div>
                          <span style={{
                            fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-body)',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {app.company?.name || 'Company'}
                          </span>
                        </div>

                        {/* Status Select Badge */}
                        <select
                          className="input"
                          value={app.status}
                          onClick={e => e.stopPropagation()}
                          onChange={e => handleStatusChange(app.id, e.target.value as ApplicationStatus, app.status)}
                          style={{
                            width: 'auto', padding: '3px 6px', fontSize: '0.7rem', fontWeight: 700, height: 24,
                            background: theme.bg, color: theme.text, border: `1px solid ${theme.border}`,
                            borderRadius: 99, flexShrink: 0
                          }}
                        >
                          {COLUMNS.map(c => (
                            <option key={c.id} value={c.id} style={{ background: '#0b0f19', color: '#fff' }}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Middle: Job Title (Clean 2-line clamp) */}
                      <div>
                        <h4 style={{
                          fontSize: '0.94rem', fontWeight: 700, color: '#ffffff',
                          lineHeight: 1.35,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          margin: '6px 0 4px 0',
                          fontFamily: 'var(--font-heading)'
                        }}>
                          {app.job?.title || `Job #${app.job_id}`}
                        </h4>

                        {app.job?.location && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                            <MapPin size={11} color="var(--text-muted)" />
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {app.job.location}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Notes Inset Container */}
                      <div style={{
                        background: 'var(--bg-inset)',
                        backdropFilter: 'blur(10px)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '7px 10px',
                        fontSize: '0.76rem',
                        color: app.notes ? 'var(--text-body)' : 'var(--text-dim)',
                        height: 48,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        border: '1px solid rgba(255, 255, 255, 0.05)',
                      }}>
                        <span style={{
                          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                          overflow: 'hidden', fontStyle: app.notes ? 'normal' : 'italic', flex: 1,
                          lineHeight: 1.35
                        }}>
                          {app.notes || 'No notes added yet'}
                        </span>
                        <ChevronRight size={14} color="var(--text-dim)" style={{ flexShrink: 0, marginLeft: 4 }} />
                      </div>

                      {/* Bottom Footer: Date & Actions */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          <Calendar size={11} />
                          {new Date(app.applied_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          {app.job?.job_url && (
                            <a
                              href={app.job.job_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              style={{ color: 'var(--applied-color)', padding: 4 }}
                              title="View job post"
                            >
                              <ArrowUpRight size={14} />
                            </a>
                          )}
                          <button
                            className="btn btn-ghost"
                            title="Delete entry"
                            onClick={(e) => handleDelete(app.id, app.status, e)}
                            style={{ padding: 4 }}
                          >
                            <Trash2 size={13} color="var(--text-dim)" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Per-Column Pagination UI Footer */}
                {colState.loadingMore && (
                  <div style={{
                    padding: '10px 0',
                    textAlign: 'center',
                    color: theme.text,
                    fontSize: '0.78rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6
                  }}>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Loading more...</span>
                  </div>
                )}

                {!isDemoMode && colState.hasMore && !colState.loadingMore && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleLoadMoreColumn(col.id)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      borderRadius: 'var(--radius-md)',
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: `1px dashed ${theme.border}`,
                      color: theme.text,
                      cursor: 'pointer',
                      marginTop: 4,
                      transition: 'all 0.2s ease',
                    }}
                  >
                    Load More ({colState.items.length} of {colState.total})
                  </button>
                )}

                {!isDemoMode && !colState.hasMore && colState.items.length > 0 && colState.total > 20 && (
                  <div style={{
                    padding: '8px 0',
                    textAlign: 'center',
                    color: 'var(--text-dim)',
                    fontSize: '0.74rem',
                    fontStyle: 'italic'
                  }}>
                    All {colState.total} applications loaded
                  </div>
                )}

                {colState.error && (
                  <div style={{
                    padding: '8px 12px',
                    textAlign: 'center',
                    background: 'rgba(251, 113, 133, 0.1)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid rgba(251, 113, 133, 0.3)',
                    marginTop: 4
                  }}>
                    <div style={{ fontSize: '0.75rem', color: '#fb7185', marginBottom: 6 }}>{colState.error}</div>
                    <button
                      className="btn btn-ghost"
                      onClick={() => handleLoadMoreColumn(col.id)}
                      style={{ fontSize: '0.72rem', color: '#ffffff', padding: '2px 8px' }}
                    >
                      <RefreshCw size={12} style={{ marginRight: 4 }} /> Retry
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── CARD DETAILS MODAL (Midnight Glass Overlay) ── */}
      {selectedApp && (
        <div className="overlay" onClick={() => setSelectedApp(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 580 }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span className={`status-pill status-${selectedApp.status}`}>
                    {selectedApp.status}
                  </span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                    Entry ID #{selectedApp.id}
                  </span>
                </div>
                <h2 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#ffffff' }}>
                  {selectedApp.job?.title || 'Job Application'}
                </h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#38bdf8', fontWeight: 700, fontSize: '0.95rem', marginTop: 4 }}>
                  <Building2 size={16} />
                  <span>{selectedApp.company?.name || 'Company N/A'}</span>
                  {selectedApp.company?.website && (
                    <a href={selectedApp.company.website} target="_blank" rel="noopener noreferrer" style={{ color: '#c084fc' }}>
                      <Globe size={14} />
                    </a>
                  )}
                </div>
              </div>
              <button className="btn btn-ghost" onClick={() => setSelectedApp(null)}>
                <X size={20} />
              </button>
            </div>

            {/* Info Grid */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20,
              background: 'var(--bg-inset)', padding: 16, borderRadius: 'var(--radius-md)', border: '1px solid var(--border-glass)'
            }}>
              <div>
                <span className="label">Location</span>
                <span style={{ fontSize: '0.88rem', color: '#ffffff', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MapPin size={14} color="var(--text-muted)" />
                  {selectedApp.job?.location || 'Not specified'}
                </span>
              </div>
              <div>
                <span className="label">Applied Date</span>
                <span style={{ fontSize: '0.88rem', color: '#ffffff', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Calendar size={14} color="var(--text-muted)" />
                  {new Date(selectedApp.applied_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                </span>
              </div>
              {selectedApp.job?.employment_type && (
                <div>
                  <span className="label">Employment Type</span>
                  <span style={{ fontSize: '0.88rem', color: '#ffffff' }}>{selectedApp.job.employment_type}</span>
                </div>
              )}
              {selectedApp.job?.job_url && (
                <div>
                  <span className="label">Job Link</span>
                  <a
                    href={selectedApp.job.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '0.85rem', color: '#38bdf8', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                  >
                    View Original Posting <ExternalLink size={13} />
                  </a>
                </div>
              )}
            </div>

            {/* Job Description (if available) */}
            {selectedApp.job?.description && (
              <div style={{ marginBottom: 20 }}>
                <span className="label">Job Description / Details</span>
                <div style={{
                  background: 'var(--bg-inset)', padding: '12px 14px', borderRadius: 'var(--radius-sm)',
                  fontSize: '0.84rem', color: 'var(--text-body)', lineHeight: 1.5, maxHeight: 120, overflowY: 'auto'
                }}>
                  {selectedApp.job.description}
                </div>
              </div>
            )}

            {/* Notes Section */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="label">Application Notes</span>
                {!editingNotesInModal && (
                  <button
                    className="btn btn-ghost"
                    onClick={() => { setEditingNotesInModal(true); setModalNotesText(selectedApp.notes || ''); }}
                    style={{ fontSize: '0.78rem', color: '#38bdf8' }}
                  >
                    <Pencil size={12} /> Edit Notes
                  </button>
                )}
              </div>

              {editingNotesInModal ? (
                <div>
                  <textarea
                    className="input"
                    rows={4}
                    value={modalNotesText}
                    onChange={e => setModalNotesText(e.target.value)}
                    placeholder="Add interview notes, recruiter contacts, offer details..."
                    style={{ marginBottom: 10 }}
                  />
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary" onClick={() => setEditingNotesInModal(false)}>Cancel</button>
                    <button className="btn btn-primary" onClick={() => handleSaveModalNotes(selectedApp.id)}>
                      <Check size={14} /> Save Notes
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{
                  background: 'var(--bg-inset)', padding: '12px 14px', borderRadius: 'var(--radius-sm)',
                  fontSize: '0.86rem', color: selectedApp.notes ? '#ffffff' : 'var(--text-dim)',
                  minHeight: 60, lineHeight: 1.5, fontStyle: selectedApp.notes ? 'normal' : 'italic',
                  border: '1px solid var(--border-glass)'
                }}>
                  {selectedApp.notes || 'No notes added yet. Click Edit Notes to record interview updates.'}
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 16, borderTop: '1px solid var(--border-glass)' }}>
              <button className="btn btn-danger" onClick={() => handleDelete(selectedApp.id, selectedApp.status)}>
                <Trash2 size={14} /> Delete Entry
              </button>

              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Status:</span>
                <select
                  className="input"
                  value={selectedApp.status}
                  onChange={e => handleStatusChange(selectedApp.id, e.target.value as ApplicationStatus, selectedApp.status)}
                  style={{ width: 140, padding: '6px 10px', fontSize: '0.82rem' }}
                >
                  {COLUMNS.map(c => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

