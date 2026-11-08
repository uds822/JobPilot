import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Upload, 
  RefreshCw, 
  ExternalLink, 
  Briefcase, 
  Building2, 
  MapPin, 
  DollarSign, 
  CheckCircle2, 
  AlertCircle, 
  Bookmark, 
  X, 
  SlidersHorizontal,
  Zap,
  FileText,
  Search,
  ArrowUpDown,
  UserCheck,
  Globe2,
  Coins,
  LayoutDashboard,
  Trash2
} from 'lucide-react';
import { 
  uploadResume, 
  getAIProfile, 
  updateAIPreferences, 
  triggerAISearch, 
  triggerAICompanySearch,
  getAISearchCompanies,
  getAISearchRunStatus, 
  getAIFoundJobs, 
  updateAIMatchAction,
  deleteAIFoundJobs
} from '../api/client';
import type {
  AIJobMatchCard,
  AISearchRunStatus,
  AIProfileResponse,
  AISearchCompany,
} from '../api/client';

interface AIFoundJobsProps {
  onToast: (message: string, type: 'success' | 'error' | 'info') => void;
  onApplicationCreated?: () => void | Promise<void>;
  onOpenBoard?: () => void;
}

type JobView = 'new' | 'top_matches' | 'all_unapplied' | 'saved' | 'company';
const PAGE_SIZE = 20;
const JOB_LIMIT_OPTIONS = [5, 10, 20, 50] as const;
const JOB_VIEWS: Array<{ id: JobView; label: string }> = [
  { id: 'new', label: 'Newly Fetched' },
  { id: 'top_matches', label: 'Top Matches' },
  { id: 'all_unapplied', label: 'All Unapplied' },
  { id: 'saved', label: 'Saved' },
  { id: 'company', label: 'Company Jobs' },
];
const EMPTY_VIEW_LABELS: Record<JobView, string> = {
  new: 'No newly fetched jobs',
  top_matches: 'No strong matches yet',
  all_unapplied: 'No unapplied jobs',
  saved: 'No saved jobs',
  company: 'No company jobs found',
};

const INDUSTRY_OPTIONS = ['Any', 'Software', 'AI/ML', 'FinTech', 'Healthcare', 'Semiconductor', 'E-commerce', 'Cybersecurity'];
const COMPANY_TYPE_OPTIONS = ['Any', 'startup', 'product', 'services', 'consulting', 'enterprise'];

const LOCATION_OPTIONS = [
  { id: 'bengaluru', label: 'Bengaluru (Bangalore)', region: 'India' },
  { id: 'hyderabad', label: 'Hyderabad', region: 'India' },
  { id: 'pune', label: 'Pune', region: 'India' },
  { id: 'chennai', label: 'Chennai', region: 'India' },
  { id: 'mumbai', label: 'Mumbai', region: 'India' },
  { id: 'delhi', label: 'Delhi', region: 'India' },
  { id: 'noida', label: 'Noida', region: 'India' },
  { id: 'gurugram', label: 'Gurugram (Gurgaon)', region: 'India' },
  { id: 'kolkata', label: 'Kolkata', region: 'India' },
  { id: 'indore', label: 'Indore', region: 'India' },
  { id: 'ahmedabad', label: 'Ahmedabad', region: 'India' },
  { id: 'jaipur', label: 'Jaipur', region: 'India' },
  { id: 'kochi', label: 'Kochi', region: 'India' },
  { id: 'chandigarh', label: 'Chandigarh', region: 'India' },
];

const INDIA_LOCATION_LABELS = new Set(LOCATION_OPTIONS.map(option => option.label));

const USD_TO_INR_RATE = 85.0; // 1 USD ≈ ₹85 INR

const formatFreshness = (value?: string) => {
  if (!value) return 'Freshness unavailable';
  const ageMs = Math.max(0, Date.now() - new Date(value).getTime());
  const ageMinutes = Math.floor(ageMs / 60000);
  if (ageMinutes < 1) return 'Checked just now';
  if (ageMinutes < 60) return `Checked ${ageMinutes}m ago`;
  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) return `Checked ${ageHours}h ago`;
  return `Checked ${Math.floor(ageHours / 24)}d ago`;
};

export const AIFoundJobs: React.FC<AIFoundJobsProps> = ({ onToast, onApplicationCreated, onOpenBoard }) => {
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [profileData, setProfileData] = useState<AIProfileResponse | null>(null);
  const [jobs, setJobs] = useState<AIJobMatchCard[]>([]);
  const [currentRun, setCurrentRun] = useState<AISearchRunStatus | null>(null);
  const [activeSearchLocations, setActiveSearchLocations] = useState<string[]>([]);
  const [activeView, setActiveView] = useState<JobView>('new');
  const [newJobsLimit, setNewJobsLimit] = useState<number>(20);
  const [topMatchesLimit, setTopMatchesLimit] = useState<number>(20);
  const [hasMoreJobs, setHasMoreJobs] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingJobIds, setPendingJobIds] = useState<Set<number>>(new Set());
  const [selectedJobIds, setSelectedJobIds] = useState<Set<number>>(new Set());
  const [deletePrompt, setDeletePrompt] = useState<'selected' | 'all' | null>(null);
  const [deletingJobs, setDeletingJobs] = useState(false);

  // Currency Mode: 'USD' ($ / yr) | 'INR' (₹ LPA)
  const [currencyMode, setCurrencyMode] = useState<'USD' | 'INR'>('USD');

  // Filter & Search States
  const [companyNameQuery, setCompanyNameQuery] = useState<string>('');
  const [searchCompanies, setSearchCompanies] = useState<AISearchCompany[]>([]);
  const [searchedCompany, setSearchedCompany] = useState<AISearchCompany | null>(null);
  const [companyQualifiedOnly, setCompanyQualifiedOnly] = useState(false);
  const [selectedIndustry, setSelectedIndustry] = useState<string>('Any');
  const [selectedCompanyType, setSelectedCompanyType] = useState<string>('Any');
  const [selectedLocations, setSelectedLocations] = useState<string[]>([]);
  const [remoteOnly] = useState<boolean>(false);
  const [minSalaryFilter, setMinSalaryFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('relevance');
  const [minScore] = useState<number>(60);
  const [showPreferencesModal, setShowPreferencesModal] = useState<boolean>(false);

  // Preference edit fields
  const [experienceMinInput, setExperienceMinInput] = useState<string>('');
  const [experienceMaxInput, setExperienceMaxInput] = useState<string>('');
  const [targetMinSalary, setTargetMinSalary] = useState<string>('');
  const [targetMaxSalary, setTargetMaxSalary] = useState<string>('');

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);
  const pendingJobIdsRef = useRef(new Set<number>());
  const activeViewRef = useRef<JobView>(activeView);
  const companyIdRef = useRef<number | null>(null);
  const companyQualifiedRef = useRef(false);
  const jobStateOverridesRef = useRef(new Map<number, Pick<AIJobMatchCard, 'status' | 'is_saved' | 'application_id'>>());

  useEffect(() => {
    loadProfileAndJobs();
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      requestIdRef.current += 1;
    };
  }, []);

  const loadProfileAndJobs = async () => {
    setLoading(true);
    try {
      const prof = await getAIProfile();
      getAISearchCompanies().then(setSearchCompanies).catch(() => {
        onToast('Company list is unavailable. Try refreshing this page.', 'error');
      });
      setProfileData(prof);
      const storedNewLimit = Number(prof.user_preferences?.new_jobs_limit);
      const storedTopLimit = Number(prof.user_preferences?.top_matches_limit);
      const nextNewLimit = JOB_LIMIT_OPTIONS.includes(storedNewLimit as typeof JOB_LIMIT_OPTIONS[number]) ? storedNewLimit : 20;
      const nextTopLimit = JOB_LIMIT_OPTIONS.includes(storedTopLimit as typeof JOB_LIMIT_OPTIONS[number]) ? storedTopLimit : 20;
      setNewJobsLimit(nextNewLimit);
      setTopMatchesLimit(nextTopLimit);
      if (prof.parsed_profile) {
        // Preserve legacy single-value preferences by treating them as a point range.
        const hasSavedExperienceRange = prof.user_preferences
          && ('experience_min_years' in prof.user_preferences || 'experience_max_years' in prof.user_preferences);
        const legacyExp = prof.user_preferences?.years_experience ?? prof.parsed_profile.years_experience;
        const expMin = hasSavedExperienceRange
          ? prof.user_preferences?.experience_min_years
          : legacyExp;
        const expMax = hasSavedExperienceRange
          ? prof.user_preferences?.experience_max_years
          : legacyExp;
        setExperienceMinInput(expMin == null ? '' : String(expMin));
        setExperienceMaxInput(expMax == null ? '' : String(expMax));

        // Salary: prefer user_preferences (what user last saved), fallback to parsed_profile
        // All salary values in DB are stored in USD. Convert back to LPA for display.
        const minUSDRaw = prof.user_preferences?.salary_expectation_min ?? prof.parsed_profile.salary_expectation_min;
        const maxUSDRaw = prof.user_preferences?.salary_expectation_max ?? prof.parsed_profile.salary_expectation_max;

        if (minUSDRaw) {
          const minUSD = parseFloat(String(minUSDRaw));
          const minLPA = (minUSD * USD_TO_INR_RATE) / 100000;
          setTargetMinSalary(minLPA > 0.1 ? String(Math.round(minLPA * 10) / 10) : '');
        } else {
          setTargetMinSalary('');
        }
        if (maxUSDRaw) {
          const maxUSD = parseFloat(String(maxUSDRaw));
          const maxLPA = (maxUSD * USD_TO_INR_RATE) / 100000;
          setTargetMaxSalary(maxLPA > 0.1 ? String(Math.round(maxLPA * 10) / 10) : '');
        } else {
          setTargetMaxSalary('');
        }

        // Locations: prefer user_preferences
        const locs = prof.user_preferences?.preferred_locations ?? prof.parsed_profile.preferred_locations;
        const indiaLocations = Array.isArray(locs)
          ? locs.filter((location: string) => INDIA_LOCATION_LABELS.has(location))
          : [];
        setSelectedLocations(indiaLocations);
        setActiveSearchLocations(indiaLocations);
      }
      
      await fetchJobsList(
        companyNameQuery,
        selectedIndustry,
        selectedCompanyType,
        remoteOnly,
        minScore,
        minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
        sortBy,
        activeViewRef.current,
        0,
        false,
        activeViewRef.current === 'new' ? nextNewLimit : activeViewRef.current === 'top_matches' ? nextTopLimit : PAGE_SIZE,
      );
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchJobsList = async (
    compName?: string,
    ind?: string,
    cType?: string,
    remote?: boolean,
    score?: number,
    minSal?: number,
    sort?: string,
    view: JobView = activeViewRef.current,
    offset = 0,
    append = false,
    limitOverride?: number,
  ) => {
    const requestId = ++requestIdRef.current;
    if (view === 'company' && companyIdRef.current === null) {
      setJobs([]);
      return;
    }
    if (!append) {
      setLoading(true);
      setSelectedJobIds(new Set());
    }
    try {
      // Calculate effective min salary in USD if entered in INR
      let effectiveMinSalUSD = minSal;
      if (minSal && currencyMode === 'INR') {
        // minSal is in LPA (Lakhs Per Annum) -> convert to USD
        effectiveMinSalUSD = (minSal * 100000) / USD_TO_INR_RATE;
      }

      const pageSize = limitOverride ?? (view === 'new' ? newJobsLimit : view === 'top_matches' ? topMatchesLimit : PAGE_SIZE);
      const foundJobs = await getAIFoundJobs({
        view,
        company_name: view === 'company' ? undefined : compName || undefined,
        company_id: view === 'company' ? companyIdRef.current ?? undefined : undefined,
        qualified_only: view === 'company' ? companyQualifiedRef.current : undefined,
        industry: ind,
        company_type: cType,
        min_score: view === 'top_matches' || (view === 'company' && companyQualifiedRef.current) ? 80 : (score ?? minScore),
        min_salary: effectiveMinSalUSD,
        remote_only: remote,
        sort_by: sort || sortBy,
        offset,
        limit: pageSize,
      });
      if (requestId !== requestIdRef.current) return;
      // Preserve confirmed actions if this response started before a state change.
      const visibleJobs = foundJobs
        .map(job => ({ ...job, ...jobStateOverridesRef.current.get(job.job_id) }))
        .filter(job => job.status !== 'applied' && job.status !== 'dismissed'
          && (view !== 'saved' || job.is_saved || job.status === 'saved'));
      setJobs(previous => append ? [...previous, ...visibleJobs] : visibleJobs);
      setHasMoreJobs(view !== 'top_matches' && foundJobs.length === pageSize);
    } catch (err: any) {
      if (requestId === requestIdRef.current) {
        onToast(err.message || 'Error loading matched jobs', 'error');
      }
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  const handleResultLimitChange = async (view: 'new' | 'top_matches', value: number) => {
    if (view === 'new') setNewJobsLimit(value);
    else setTopMatchesLimit(value);
    try {
      await updateAIPreferences(view === 'new' ? { new_jobs_limit: value } : { top_matches_limit: value });
      if (activeView === view) {
        await fetchJobsList(
          companyNameQuery, selectedIndustry, selectedCompanyType, remoteOnly,
          minScore, minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
          sortBy, view, 0, false, value,
        );
      }
    } catch (err: any) {
      onToast(err.message || 'Failed to save result count', 'error');
    }
  };

  const handleViewChange = async (view: JobView) => {
    activeViewRef.current = view;
    setActiveView(view);
    if (view === 'company' && companyIdRef.current === null) {
      setJobs([]);
      return;
    }
    await fetchJobsList(
      companyNameQuery,
      selectedIndustry,
      selectedCompanyType,
      remoteOnly,
      minScore,
      minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
      sortBy,
      view,
    );
  };

  const handleLoadMore = async () => {
    setLoadingMore(true);
    await fetchJobsList(
      companyNameQuery,
      selectedIndustry,
      selectedCompanyType,
      remoteOnly,
      minScore,
      minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
      sortBy,
      activeView,
      jobs.length,
      true,
    );
    setLoadingMore(false);
  };

  const toggleLocationSelection = (locLabel: string) => {
    setSelectedLocations(prev => 
      prev.includes(locLabel)
        ? prev.filter(l => l !== locLabel)
        : [...prev, locLabel]
    );
  };

  const formatSalaryText = (salMin?: number, salMax?: number) => {
    if (!salMin && !salMax) return 'Salary: Competitive / Est.';

    const minUSD = salMin || 120000;
    const maxUSD = salMax || 160000;

    if (currencyMode === 'INR') {
      const minLPA = (minUSD * USD_TO_INR_RATE / 100000).toFixed(1);
      const maxLPA = (maxUSD * USD_TO_INR_RATE / 100000).toFixed(1);
      return `₹${minLPA} - ₹${maxLPA} LPA`;
    }

    return `$${minUSD.toLocaleString()} - $${maxUSD.toLocaleString()} /yr`;
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await uploadResume(file);
      onToast('Resume uploaded & parsed successfully!', 'success');
      await loadProfileAndJobs();
    } catch (err: any) {
      onToast(err.message || 'Failed to upload resume', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleTriggerSearch = async () => {
    if (!profileData?.has_profile) {
      onToast('Please upload your resume before searching.', 'error');
      fileInputRef.current?.click();
      return;
    }

    try {
      // The search worker reads persisted preferences, so save the current pills
      // before creating the run instead of relying on a previous modal save.
      const preferenceResult = await updateAIPreferences({
        preferred_locations: selectedLocations
      });
      const persistedLocations = preferenceResult.user_preferences?.preferred_locations;
      setActiveSearchLocations(
        Array.isArray(persistedLocations) ? persistedLocations : [...selectedLocations]
      );
      const runStatus = await triggerAISearch();
      setCurrentRun(runStatus);
      onToast('AI job discovery pipeline initiated...', 'info');

      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(async () => {
        try {
          const updatedRun = await getAISearchRunStatus(runStatus.id);
          setCurrentRun(updatedRun);

          if (updatedRun.status === 'completed') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            onToast(`Job discovery completed: ${updatedRun.jobs_fetched} listings fetched`, 'success');
            setCompanyNameQuery('');
            setActiveView('new');
            activeViewRef.current = 'new';
            await fetchJobsList(undefined, selectedIndustry, selectedCompanyType, remoteOnly, minScore,
              minSalaryFilter ? parseFloat(minSalaryFilter) : undefined, sortBy, 'new');
          } else if (updatedRun.status === 'failed') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            onToast(updatedRun.error_message || 'Pipeline encountered an issue.', 'error');
          }
        } catch (pollErr) {
          if (pollingRef.current) clearInterval(pollingRef.current);
        }
      }, 1500);

    } catch (err: any) {
      onToast(err.message || 'Failed to trigger search', 'error');
    }
  };

  const handleCompanySearch = async () => {
    const company = searchCompanies.find(item => item.name.toLowerCase() === companyNameQuery.trim().toLowerCase());
    if (!company) {
      onToast('Choose a registered company from the suggestions.', 'error');
      return;
    }
    if (!company.fetchable && !company.directory_available) {
      onToast(`${company.name}: ${company.status.replace(/_/g, ' ')}. No job source is available yet.`, 'info');
      return;
    }
    if (!profileData?.has_profile) {
      onToast('Upload your resume before searching company jobs.', 'error');
      return;
    }
    try {
      const preferenceResult = await updateAIPreferences({ preferred_locations: selectedLocations });
      setActiveSearchLocations(preferenceResult.user_preferences?.preferred_locations ?? selectedLocations);
      const run = await triggerAICompanySearch(company.id);
      companyIdRef.current = company.id;
      setSearchedCompany(company);
      setCurrentRun(run);
      const showResults = async () => {
        activeViewRef.current = 'company';
        setActiveView('company');
        await fetchJobsList(undefined, selectedIndustry, selectedCompanyType, remoteOnly, minScore,
          minSalaryFilter ? parseFloat(minSalaryFilter) : undefined, sortBy, 'company');
      };
      if (run.status === 'completed') {
        await showResults();
        return;
      }
      onToast(company.fetchable ? `Checking ${company.name} jobs...` : `Searching third-party listings for ${company.name}...`, 'info');
      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(async () => {
        try {
          const updated = await getAISearchRunStatus(run.id);
          setCurrentRun(updated);
          if (updated.status === 'completed') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            await showResults();
            onToast(`${company.name}: ${updated.jobs_after_validity} listings found in your selected locations`, 'success');
          } else if (updated.status === 'failed') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            onToast(updated.error_message || 'Company search failed.', 'error');
          }
        } catch (err: any) {
          if (pollingRef.current) clearInterval(pollingRef.current);
          onToast(err.message || 'Could not check company search status.', 'error');
        }
      }, 1500);
    } catch (err: any) {
      onToast(err.response?.data?.detail || err.message || 'Could not search this company.', 'error');
    }
  };

  const handleAction = async (matchId: number, action: 'save' | 'unsave' | 'dismiss' | 'apply') => {
    if (pendingJobIdsRef.current.has(matchId)) return;
    pendingJobIdsRef.current.add(matchId);
    setPendingJobIds(new Set(pendingJobIdsRef.current));
    try {
      const updated = await updateAIMatchAction(matchId, action);
      jobStateOverridesRef.current.set(updated.job_id, {
        status: updated.status,
        is_saved: updated.is_saved,
        application_id: updated.application_id,
      });
      if (action === 'dismiss') {
        setJobs(prev => prev.filter(j => j.job_id !== updated.job_id));
        setSelectedJobIds(prev => {
          const next = new Set(prev);
          next.delete(updated.job_id);
          return next;
        });
        onToast('Job match dismissed', 'info');
      } else if (action === 'save') {
        setJobs(prev => activeViewRef.current === 'new' || activeViewRef.current === 'top_matches'
          ? prev.filter(j => j.job_id !== updated.job_id)
          : prev.map(j => j.job_id === updated.job_id ? { ...j, status: updated.status, is_saved: updated.is_saved } : j));
        onToast('Job saved to short-list!', 'success');
      } else if (action === 'unsave') {
        setJobs(prev => activeViewRef.current === 'saved'
          ? prev.filter(j => j.job_id !== updated.job_id)
          : prev.map(j => j.job_id === updated.job_id ? { ...j, status: updated.status, is_saved: updated.is_saved } : j));
        onToast('Job removed from Saved', 'info');
      } else if (action === 'apply') {
        setJobs(prev => prev.filter(j => j.job_id !== updated.job_id));
        setSelectedJobIds(prev => {
          const next = new Set(prev);
          next.delete(updated.job_id);
          return next;
        });
        await onApplicationCreated?.();
        onToast('Application added to your tracking board', 'success');
      }
    } catch (err: any) {
      onToast(err.message || 'Failed to update job state', 'error');
    } finally {
      pendingJobIdsRef.current.delete(matchId);
      setPendingJobIds(new Set(pendingJobIdsRef.current));
    }
  };

  const toggleJobSelection = (jobId: number) => {
    setSelectedJobIds(previous => {
      const next = new Set(previous);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };

  const toggleVisibleSelection = () => {
    const visibleIds = jobs.map(job => job.job_id);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedJobIds.has(id));
    setSelectedJobIds(previous => {
      const next = new Set(previous);
      visibleIds.forEach(id => allVisibleSelected ? next.delete(id) : next.add(id));
      return next;
    });
  };

  const handleDeleteJobs = async () => {
    if (!deletePrompt || deletingJobs) return;
    setDeletingJobs(true);
    try {
      const result = deletePrompt === 'all'
        ? await deleteAIFoundJobs({ delete_all: true })
        : await deleteAIFoundJobs({ job_ids: [...selectedJobIds] });
      const deletedIds = new Set(selectedJobIds);
      setJobs(previous => deletePrompt === 'all'
        ? []
        : previous.filter(job => !deletedIds.has(job.job_id)));
      setSelectedJobIds(new Set());
      setDeletePrompt(null);
      onToast(
        `${result.deleted_jobs} job records deleted; ${result.deleted_matches} matches removed${result.retained_shared_jobs ? `, ${result.retained_shared_jobs} shared jobs kept for other users` : ''}.`,
        'success'
      );
      await fetchJobsList(
        companyNameQuery, selectedIndustry, selectedCompanyType, remoteOnly,
        minScore, minSalaryFilter ? parseFloat(minSalaryFilter) : undefined, sortBy,
      );
    } catch (err: any) {
      onToast(err.message || 'Failed to delete jobs', 'error');
    } finally {
      setDeletingJobs(false);
    }
  };

  const handleSavePreferences = async () => {
    try {
      let minSalUSD = targetMinSalary ? parseFloat(targetMinSalary) : undefined;
      let maxSalUSD = targetMaxSalary ? parseFloat(targetMaxSalary) : undefined;

      if (currencyMode === 'INR') {
        if (minSalUSD) minSalUSD = (minSalUSD * 100000) / USD_TO_INR_RATE;
        if (maxSalUSD) maxSalUSD = (maxSalUSD * 100000) / USD_TO_INR_RATE;
      }

      await updateAIPreferences({
        experience_min_years: experienceMinInput ? parseFloat(experienceMinInput) : null,
        experience_max_years: experienceMaxInput ? parseFloat(experienceMaxInput) : null,
        preferred_locations: selectedLocations,
        salary_expectation_min: minSalUSD,
        salary_expectation_max: maxSalUSD,
        remote_preference: remoteOnly ? 'remote' : 'any'
      });
      setShowPreferencesModal(false);
      onToast('Profile & Preferences updated!', 'success');
      loadProfileAndJobs();
    } catch (err: any) {
      onToast(err.message || 'Failed to save preferences', 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '24px 0' }}>
      {/* Hidden File Input */}
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileUpload} 
        accept=".pdf,.docx,.doc" 
        style={{ display: 'none' }} 
      />

      {/* Header Acrylic Card */}
      <div className="acrylic-card" style={{ padding: '28px 32px', position: 'relative', overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', top: -100, right: -100, width: 250, height: 250,
          borderRadius: '50%', background: 'rgba(99, 102, 241, 0.12)', filter: 'blur(50px)', pointerEvents: 'none'
        }} />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ maxWidth: 650 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '4px 12px', borderRadius: 99,
              background: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.3)',
              color: '#a5b4fc', fontSize: '0.75rem', fontWeight: 600, marginBottom: 12
            }}>
              <Sparkles size={14} color="#818cf8" />
              <span>AI Job Search Engine • Phase 1 MVP</span>
            </div>

            <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: '#ffffff', marginBottom: 8 }}>
              AI Found Jobs
            </h1>

            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', lineHeight: 1.5 }}>
              Upload your resume to find and rank relevant jobs across India. Select cities to narrow the search, or leave every city unselected to search all of India.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            {onOpenBoard && (
              <button className="btn btn-secondary" onClick={onOpenBoard}>
                <LayoutDashboard size={16} /> Board
              </button>
            )}
            <button
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              style={{ padding: '10px 18px' }}
            >
              {uploading ? <RefreshCw size={16} className="spin" /> : <Upload size={16} color="#818cf8" />}
              <span>{profileData?.has_profile ? 'Re-upload Resume' : 'Upload Resume'}</span>
            </button>

            <button
              className="btn btn-primary"
              onClick={handleTriggerSearch}
              disabled={currentRun?.status === 'running' || currentRun?.status === 'queued'}
              style={{ padding: '10px 22px' }}
            >
              <Zap size={16} />
              <span>{currentRun?.status === 'running' ? 'Scanning Jobs...' : 'Find Jobs / Refresh'}</span>
            </button>
          </div>
        </div>

        {/* Candidate Resume Profile Summary & Editable Experience */}
        {profileData?.has_profile && profileData.parsed_profile && (
          <div style={{
            marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-glass)',
            display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: '0.82rem'
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, color: '#a5b4fc' }}>
              <FileText size={15} /> Resume Profile:
            </span>

            <span style={{ padding: '3px 10px', borderRadius: 6, background: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#fff', display: 'flex', alignItems: 'center', gap: 4 }}>
              <UserCheck size={13} color="#818cf8" />
              Exp: <strong>{profileData.parsed_profile.years_experience} yrs</strong>
            </span>

            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {profileData.parsed_profile.skills.slice(0, 5).map((skill, i) => (
                <span key={i} style={{
                  padding: '2px 8px', borderRadius: 4, background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--border-glass)', color: '#c7d2fe', fontSize: '0.78rem'
                }}>
                  {skill}
                </span>
              ))}
            </div>

            {profileData.parsed_profile.target_roles && profileData.parsed_profile.target_roles.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <strong style={{ color: 'var(--text-muted)', fontSize: '0.76rem' }}>Target roles:</strong>
                {profileData.parsed_profile.target_roles.map(role => (
                  <span key={role} style={{ padding: '2px 8px', borderRadius: 4, background: 'rgba(52, 211, 153, 0.12)', border: '1px solid rgba(52, 211, 153, 0.28)', color: '#a7f3d0', fontSize: '0.76rem' }}>{role}</span>
                ))}
              </div>
            )}

            <button
              onClick={() => setShowPreferencesModal(true)}
              className="btn btn-ghost"
              style={{ marginLeft: 'auto', color: '#818cf8', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <SlidersHorizontal size={14} /> Edit Experience & Locations
            </button>
          </div>
        )}
      </div>

      {/* Server-confirmed search context */}
      <div
        className="acrylic-card"
        style={{
          padding: '14px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
          <MapPin size={16} color="#38bdf8" style={{ marginTop: 2, flexShrink: 0 }} />
          <strong style={{ color: '#e2e8f0', fontSize: '0.82rem' }}>
            {currentRun?.status === 'running' || currentRun?.status === 'queued'
              ? 'Fetching locations:'
              : 'Last fetch locations:'}
          </strong>
          <span style={{ color: '#bae6fd', fontSize: '0.82rem' }}>
            {activeSearchLocations.length > 0
              ? activeSearchLocations.join(' / ')
              : 'All India'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <SlidersHorizontal size={16} color="#a78bfa" style={{ marginTop: 2, flexShrink: 0 }} />
          <strong style={{ color: '#e2e8f0', fontSize: '0.82rem' }}>Selected constraints:</strong>
        </div>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))',
          gap: '10px 18px',
          paddingLeft: 26
        }}>
          {[
            ['Region', selectedLocations.length > 0 ? selectedLocations.join(' / ') : 'All India'],
            ['Minimum match', activeView === 'top_matches' ? '80% (strong)' : 'Any score'],
            ['Your experience', experienceMinInput || experienceMaxInput
              ? `${experienceMinInput || '0'}-${experienceMaxInput || 'open'} years`
              : 'Not set'],
            ['Work mode', remoteOnly ? 'Remote only' : 'Any'],
            ['Industry', selectedIndustry],
            ['Company type', selectedCompanyType],
            ['Minimum salary', minSalaryFilter ? `${minSalaryFilter} ${currencyMode === 'INR' ? 'LPA' : 'USD/year'}` : 'No minimum'],
          ].map(([label, value]) => (
            <div key={label} style={{ minWidth: 0 }}>
              <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', marginBottom: 2 }}>{label}</div>
              <div style={{ color: '#cbd5e1', fontSize: '0.8rem', overflowWrap: 'anywhere' }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Progress Card during background run */}
      {currentRun && (currentRun.status === 'running' || currentRun.status === 'queued') && (
        <div className="acrylic-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, fontSize: '0.88rem' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#a5b4fc', fontWeight: 600 }}>
              <RefreshCw size={16} className="spin" color="#818cf8" />
              AI Discovery Pipeline Executing...
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'capitalize' }}>
              Status: {currentRun.status}
            </span>
          </div>

          <div style={{ height: 6, background: 'rgba(255, 255, 255, 0.08)', borderRadius: 99, overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ width: '65%', height: '100%', background: 'linear-gradient(90deg, #6366f1, #ec4899)', borderRadius: 99 }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 12, textAlign: 'center' }}>
            <div style={{ padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Fetched</div>
              <strong style={{ fontSize: '0.95rem', color: '#fff' }}>{currentRun.jobs_fetched}</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Deduplicated</div>
              <strong style={{ fontSize: '0.95rem', color: '#fff' }}>{currentRun.jobs_after_dedupe}</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Valid</div>
              <strong style={{ fontSize: '0.95rem', color: '#fff' }}>{currentRun.jobs_after_validity}</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Hard Filtered</div>
              <strong style={{ fontSize: '0.95rem', color: '#fff' }}>{currentRun.jobs_after_hard_filters}</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Scored</div>
              <strong style={{ fontSize: '0.95rem', color: '#818cf8' }}>{currentRun.jobs_scored}</strong>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div
          role="tablist"
          aria-label="Job views"
          style={{
          display: 'flex',
          gap: 4,
          padding: 4,
          width: 'fit-content',
          maxWidth: '100%',
          overflowX: 'auto',
          background: 'rgba(0, 0, 0, 0.28)',
          border: '1px solid var(--border-glass)',
          borderRadius: 8,
          }}
        >
          {JOB_VIEWS.map(view => (
          <button
            key={view.id}
            type="button"
            role="tab"
            aria-selected={activeView === view.id}
            onClick={() => handleViewChange(view.id)}
            style={{
              minWidth: 92,
              flexShrink: 0,
              height: 34,
              padding: '0 12px',
              border: activeView === view.id ? '1px solid rgba(129, 140, 248, 0.55)' : '1px solid transparent',
              borderRadius: 6,
              background: activeView === view.id ? 'rgba(99, 102, 241, 0.22)' : 'transparent',
              color: activeView === view.id ? '#ffffff' : 'var(--text-muted)',
              fontSize: '0.8rem',
              fontWeight: 700,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {view.label}
          </button>
          ))}
        </div>
        {(activeView === 'new' || activeView === 'top_matches') && (
          <div role="group" aria-label={`Number of ${activeView === 'new' ? 'newly fetched jobs' : 'top matches'} to show`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Show</span>
            <div style={{ display: 'flex', gap: 3, padding: 3, border: '1px solid var(--border-glass)', borderRadius: 8, background: 'rgba(0, 0, 0, 0.22)' }}>
              {JOB_LIMIT_OPTIONS.map(limit => {
                const selected = (activeView === 'new' ? newJobsLimit : topMatchesLimit) === limit;
                return (
                  <button key={limit} type="button" aria-pressed={selected}
                    onClick={() => handleResultLimitChange(activeView, limit)}
                    style={{ minWidth: 36, height: 30, border: selected ? '1px solid rgba(129, 140, 248, 0.55)' : '1px solid transparent', borderRadius: 5, background: selected ? 'rgba(99, 102, 241, 0.22)' : 'transparent', color: selected ? '#fff' : 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}>
                    {limit}
                  </button>
                );
              })}
            </div>
          </div>
        )}
        {activeView === 'company' && searchedCompany && (
          <div role="group" aria-label="Company job results" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>{searchedCompany.name}</span>
            {([false, true] as const).map(qualified => (
              <button key={String(qualified)} type="button" className="btn btn-secondary"
                aria-pressed={companyQualifiedOnly === qualified}
                onClick={() => {
                  companyQualifiedRef.current = qualified;
                  setCompanyQualifiedOnly(qualified);
                  fetchJobsList(undefined, selectedIndustry, selectedCompanyType, remoteOnly, minScore,
                    minSalaryFilter ? parseFloat(minSalaryFilter) : undefined, sortBy, 'company');
                }}
                style={{ padding: '6px 10px', background: companyQualifiedOnly === qualified ? 'rgba(99, 102, 241, 0.22)' : undefined }}>
                {qualified ? 'Strong fits' : 'All found'}
              </button>
            ))}
          </div>
        )}
        {activeView === 'company' && searchedCompany && !searchedCompany.fetchable && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', width: '100%' }}>
            Third-party listings may be incomplete; {searchedCompany.name} has no verified job feed.
            {(searchedCompany.careers_url || searchedCompany.website_url) && (
              <> <a href={searchedCompany.careers_url || searchedCompany.website_url || '#'} target="_blank" rel="noopener noreferrer">{searchedCompany.careers_url ? 'Official careers page' : 'Company website'} <ExternalLink size={12} style={{ verticalAlign: 'middle' }} /></a></>
            )}
          </div>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setDeletePrompt('all')}
          disabled={deletingJobs}
          title="Delete all AI job matches and states for this account"
          style={{ color: '#fca5a5', borderColor: 'rgba(248, 113, 113, 0.35)' }}
        >
          <Trash2 size={15} />
          Delete all jobs
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className="acrylic-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Company Search Input */}
          <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
            <Search size={15} color="var(--text-dim)" style={{ position: 'absolute', left: 12, top: 11 }} />
            <input
              type="text"
              className="input"
              value={companyNameQuery}
              list="ai-job-company-options"
              onKeyDown={(e) => { if (e.key === 'Enter') handleCompanySearch(); }}
              onChange={(e) => {
                setCompanyNameQuery(e.target.value);
                fetchJobsList(
                  e.target.value,
                  selectedIndustry,
                  selectedCompanyType,
                  remoteOnly,
                  minScore,
                  minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
                  sortBy
                );
              }}
              placeholder="Search company (Stripe, GitHub, Netflix)..."
              style={{ paddingLeft: 36 }}
            />
            <datalist id="ai-job-company-options">
              {searchCompanies.map(company => <option key={company.id} value={company.name} />)}
            </datalist>
          </div>
          <button type="button" className="btn btn-secondary" onClick={handleCompanySearch}
            disabled={currentRun?.status === 'running' || currentRun?.status === 'queued'}
            title="Fetch and match jobs from this registered company">
            <Search size={15} /> Find company jobs
          </button>

          {/* Industry Filter */}
          <select
            className="input"
            value={selectedIndustry}
            onChange={(e) => {
              setSelectedIndustry(e.target.value);
              fetchJobsList(
                companyNameQuery,
                e.target.value,
                selectedCompanyType,
                remoteOnly,
                minScore,
                minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
                sortBy
              );
            }}
            style={{ width: 'auto', padding: '8px 12px', fontSize: '0.82rem' }}
          >
            {INDUSTRY_OPTIONS.map(ind => (
              <option key={ind} value={ind}>Industry: {ind}</option>
            ))}
          </select>

          {/* Company Type Filter */}
          <select
            className="input"
            value={selectedCompanyType}
            onChange={(e) => {
              setSelectedCompanyType(e.target.value);
              fetchJobsList(
                companyNameQuery,
                selectedIndustry,
                e.target.value,
                remoteOnly,
                minScore,
                minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
                sortBy
              );
            }}
            style={{ width: 'auto', padding: '8px 12px', fontSize: '0.82rem', textTransform: 'capitalize' }}
          >
            {COMPANY_TYPE_OPTIONS.map(ct => (
              <option key={ct} value={ct}>Company Type: {ct}</option>
            ))}
          </select>

          {/* Currency Mode Toggle ($ USD vs ₹ INR LPA) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(0,0,0,0.3)', padding: 3, borderRadius: 8, border: '1px solid var(--border-glass)' }}>
            <button
              onClick={() => setCurrencyMode('USD')}
              style={{
                padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontSize: '0.78rem', fontWeight: 700, transition: 'all 0.15s',
                background: currencyMode === 'USD' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
                color: currencyMode === 'USD' ? '#fff' : 'var(--text-muted)'
              }}
            >
              $ USD
            </button>
            <button
              onClick={() => setCurrencyMode('INR')}
              style={{
                padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontSize: '0.78rem', fontWeight: 700, transition: 'all 0.15s',
                background: currencyMode === 'INR' ? 'rgba(52, 211, 153, 0.25)' : 'transparent',
                color: currencyMode === 'INR' ? '#34d399' : 'var(--text-muted)'
              }}
            >
              ₹ INR (LPA)
            </button>
          </div>

          {/* Min Salary Input */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Min Sal:</span>
            <input
              type="number"
              className="input"
              value={minSalaryFilter}
              onChange={(e) => {
                setMinSalaryFilter(e.target.value);
                fetchJobsList(
                  companyNameQuery,
                  selectedIndustry,
                  selectedCompanyType,
                  remoteOnly,
                  minScore,
                  e.target.value ? parseFloat(e.target.value) : undefined,
                  sortBy
                );
              }}
              placeholder={currencyMode === 'INR' ? '₹ LPA' : '$ / yr'}
              style={{ width: 90, padding: '8px 10px', fontSize: '0.82rem' }}
            />
          </div>

          {/* Sorting Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ArrowUpDown size={14} color="#818cf8" />
            <select
              className="input"
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                fetchJobsList(
                  companyNameQuery,
                  selectedIndustry,
                  selectedCompanyType,
                  remoteOnly,
                  minScore,
                  minSalaryFilter ? parseFloat(minSalaryFilter) : undefined,
                  e.target.value
                );
              }}
              style={{ width: 'auto', padding: '8px 12px', fontSize: '0.82rem' }}
            >
              <option value="relevance">Sort: Most Relevance</option>
              <option value="salary_high">Sort: Salary (High to Low)</option>
              <option value="salary_low">Sort: Salary (Low to High)</option>
              <option value="freshness">Sort: Freshness (Newest)</option>
            </select>
          </div>
        </div>

          {/* Optional India city constraints; no selection means all India. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 8, borderTop: '1px solid var(--border-glass)' }}>
          <span style={{ fontSize: '0.78rem', color: '#a5b4fc', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Globe2 size={13} /> Target Locations:
          </span>

          {LOCATION_OPTIONS.map(loc => {
            const isSelected = selectedLocations.includes(loc.label);
            return (
              <button
                key={loc.id}
                onClick={() => toggleLocationSelection(loc.label)}
                style={{
                  padding: '3px 10px', borderRadius: 99, fontSize: '0.75rem', fontWeight: 600,
                  cursor: 'pointer', transition: 'all 0.15s ease',
                  background: isSelected ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.04)',
                  border: isSelected ? '1px solid #6366f1' : '1px solid var(--border-glass)',
                  color: isSelected ? '#fff' : 'var(--text-muted)'
                }}
              >
                {loc.label} {isSelected && '✓'}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Jobs Cards Grid */}
      {!loading && jobs.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', padding: '10px 14px', border: '1px solid var(--border-glass)', borderRadius: 8, background: 'rgba(0, 0, 0, 0.2)' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-body)', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={jobs.every(job => selectedJobIds.has(job.job_id))}
              onChange={toggleVisibleSelection}
              aria-label="Select all shown jobs"
            />
            Select all shown ({jobs.length})
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{selectedJobIds.size} selected</span>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setDeletePrompt('selected')}
              disabled={selectedJobIds.size === 0 || deletingJobs}
              style={{ color: '#fca5a5', borderColor: 'rgba(248, 113, 113, 0.35)' }}
            >
              <Trash2 size={15} />
              Delete selected
            </button>
          </div>
        </div>
      )}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <RefreshCw size={32} className="spin" color="#818cf8" style={{ marginBottom: 12 }} />
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Loading AI matched opportunities...</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="acrylic-card" style={{ padding: '60px 24px', textAlign: 'center' }}>
          <div style={{
            width: 54, height: 54, borderRadius: '50%', background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid var(--border-glass)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px auto', color: 'var(--text-muted)'
          }}>
            <Briefcase size={26} />
          </div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', marginBottom: 6 }}>
            {EMPTY_VIEW_LABELS[activeView]}
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: 450, margin: '0 auto 20px auto' }}>
            {profileData?.has_profile 
              ? activeView === 'company'
                ? searchedCompany ? `No ${companyQualifiedOnly ? 'strong-fit ' : ''}jobs from ${searchedCompany.name} in your selected locations. Try All found or another location.` : 'Choose a registered company and search its jobs.'
                : "Try adjusting your company search, location filters, or click 'Find Jobs / Refresh' to scan live listings."
              : "Please upload your resume to start matching with jobs."}
          </p>
          {!profileData?.has_profile && (
            <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()} style={{ padding: '10px 24px' }}>
              Upload Resume Now
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 400px), 1fr))', gap: 20 }}>
          {jobs.map((job) => {
            const isStrong = job.match_score >= 80;
            const isSaved = job.is_saved || job.status === 'saved';
            const isPending = pendingJobIds.has(job.id);
            return (
              <div 
                key={job.id}
                className="acrylic-card acrylic-card-hover"
                style={{ padding: 24, borderRadius: 8, minWidth: 0, overflowWrap: 'anywhere', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 16 }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, width: 'fit-content', color: 'var(--text-muted)', fontSize: '0.78rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={selectedJobIds.has(job.job_id)}
                      onChange={() => toggleJobSelection(job.job_id)}
                      aria-label={`Select ${job.title} at ${job.company}`}
                    />
                    Select job
                  </label>
                  {/* Card Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
                    <div style={{ minWidth: 0, flex: '1 1 200px' }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#818cf8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                        {job.discovery_channel} • {job.source} • {job.industry}
                      </div>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#ffffff', lineHeight: 1.3, marginBottom: 6 }}>
                        {job.title}
                      </h3>
                      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10, fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#e2e8f0', fontWeight: 600 }}>
                          <Building2 size={14} color="var(--text-muted)" /> {job.company}
                        </span>
                        <span>•</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <MapPin size={14} color="var(--text-muted)" /> {job.location}
                        </span>
                      </div>
                    </div>

                    {/* Match Score Badge */}
                    <div style={{
                      padding: '6px 12px', borderRadius: 12, fontSize: '0.78rem', fontWeight: 800,
                      background: isStrong ? 'rgba(52, 211, 153, 0.15)' : 'rgba(99, 102, 241, 0.15)',
                      border: isStrong ? '1px solid rgba(52, 211, 153, 0.3)' : '1px solid rgba(99, 102, 241, 0.3)',
                      color: isStrong ? '#34d399' : '#a5b4fc',
                      display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0
                    }}>
                      <Sparkles size={14} />
                      <span>{job.match_score}% {job.match_level}</span>
                    </div>
                  </div>

                  {/* Details Line with Dual Currency Formatting (USD / INR LPA) */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingTop: 10, borderTop: '1px solid var(--border-glass)', fontSize: '0.8rem' }}>
                    <span
                      title={job.experience_evidence || job.experience_reason || 'Experience requirement not available'}
                      style={{
                        padding: '3px 8px', borderRadius: 6,
                        background: job.experience_status === 'matched' ? 'rgba(52,211,153,0.12)' : job.experience_status === 'mismatched' ? 'rgba(248,113,113,0.12)' : 'rgba(251,191,36,0.12)',
                        color: job.experience_status === 'matched' ? '#a7f3d0' : job.experience_status === 'mismatched' ? '#fca5a5' : '#fde68a',
                        border: '1px solid currentColor',
                      }}
                    >
                      {job.experience_status === 'matched'
                        ? `Experience fit${job.required_experience_min == null ? '' : `: ${job.required_experience_min}${job.required_experience_max == null ? '+' : `-${job.required_experience_max}`} yrs`}`
                        : job.experience_status === 'mismatched'
                          ? job.experience_reason || 'Experience mismatch'
                          : job.seniority_conflict ? 'Experience unknown (senior title)' : 'Experience unknown'}
                    </span>
                    {(job.salary_min || job.salary_max) ? (
                      <span style={{
                        display: 'flex', alignItems: 'center', gap: 4, fontWeight: 700,
                        color: currencyMode === 'INR' ? '#34d399' : '#38bdf8',
                        background: currencyMode === 'INR' ? 'rgba(52, 211, 153, 0.1)' : 'rgba(56, 189, 248, 0.1)',
                        padding: '3px 8px', borderRadius: 6,
                        border: currencyMode === 'INR' ? '1px solid rgba(52, 211, 153, 0.25)' : '1px solid rgba(56, 189, 248, 0.25)'
                      }}>
                        {currencyMode === 'INR' ? <Coins size={14} /> : <DollarSign size={14} />}
                        {formatSalaryText(job.salary_min, job.salary_max)}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Salary: Competitive</span>
                    )}

                    <span style={{ padding: '2px 8px', borderRadius: 6, background: 'rgba(255,255,255,0.06)', color: 'var(--text-body)', textTransform: 'capitalize' }}>
                      {job.company_type}
                    </span>

                    {job.remote && (
                      <span style={{ padding: '2px 8px', borderRadius: 6, background: 'rgba(99, 102, 241, 0.15)', color: '#c7d2fe', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                        100% Remote
                      </span>
                    )}
                    {job.is_expired && (
                      <span style={{ padding: '2px 8px', borderRadius: 6, background: 'rgba(248,113,113,0.12)', color: '#fca5a5', border: '1px solid rgba(248,113,113,0.3)' }}>
                        No longer active
                      </span>
                    )}
                    <span style={{ color: 'var(--text-dim)' }}>
                      {formatFreshness(job.last_seen_at)}
                    </span>
                  </div>

                  {/* Strengths & Gaps Rationale */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.8rem' }}>
                    {job.strengths && job.strengths.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {job.strengths.map((str, idx) => (
                          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, color: '#cbd5e1' }}>
                            <CheckCircle2 size={14} color="#34d399" style={{ flexShrink: 0, marginTop: 2 }} />
                            <span>{str}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {job.gaps && job.gaps.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {job.gaps.map((gap, idx) => (
                          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, color: '#fde68a' }}>
                            <AlertCircle size={14} color="#fbbf24" style={{ flexShrink: 0, marginTop: 2 }} />
                            <span>{gap}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Action Buttons */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', paddingTop: 14, borderTop: '1px solid var(--border-glass)' }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {job.status !== 'applied' && (
                      <button
                        onClick={() => handleAction(job.id, isSaved ? 'unsave' : 'save')}
                        disabled={isPending}
                        className="btn btn-secondary"
                        style={{ padding: '6px 12px', background: isSaved ? 'rgba(251, 191, 36, 0.2)' : undefined, color: isSaved ? '#fbbf24' : undefined }}
                        title={isSaved ? 'Remove from Saved' : 'Save Job'}
                        aria-label={isSaved ? 'Remove from Saved' : 'Save Job'}
                        aria-pressed={isSaved}
                      >
                        <Bookmark size={15} />
                      </button>
                    )}
                    {activeView !== 'saved' && (
                      <button
                        onClick={() => handleAction(job.id, 'dismiss')}
                        disabled={isPending}
                        className="btn btn-secondary"
                        style={{ padding: '6px 12px' }}
                        title="Dismiss Job"
                        aria-label="Dismiss Job"
                      >
                        <X size={15} />
                      </button>
                    )}
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <button
                      onClick={() => handleAction(job.id, 'apply')}
                      disabled={isPending}
                      className="btn btn-secondary"
                      title="Mark as applied and add to tracking board"
                      style={{ padding: '8px 12px', fontSize: '0.82rem' }}
                    >
                      {isPending ? <RefreshCw size={15} className="spin" /> : <UserCheck size={15} />}
                      Mark as Applied
                    </button>
                    <button
                      onClick={() => window.open(job.apply_url, '_blank', 'noopener,noreferrer')}
                      className="btn btn-primary"
                      disabled={job.is_expired}
                      style={{ padding: '8px 18px', fontSize: '0.82rem' }}
                    >
                      <span>{job.is_expired ? 'Closed' : 'Apply Now'}</span>
                      <ExternalLink size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && hasMoreJobs && (
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleLoadMore}
            disabled={loadingMore}
            style={{ minWidth: 140, justifyContent: 'center' }}
          >
            {loadingMore ? <RefreshCw size={15} className="spin" /> : null}
            {loadingMore ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}

      {deletePrompt && (
        <div className="overlay" role="presentation">
          <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-jobs-title" style={{ maxWidth: 480 }}>
            <h2 id="delete-jobs-title" style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 8, color: '#fff' }}>
              {deletePrompt === 'all' ? 'Delete all AI-found jobs?' : `Delete ${selectedJobIds.size} selected jobs?`}
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', lineHeight: 1.55, marginBottom: 20 }}>
              {deletePrompt === 'all'
                ? 'This removes all AI job matches and saved states for your account from the database. Canonical job records are permanently deleted only when no other account references them. Applications already on your tracking board are kept.'
                : 'This removes the selected AI job matches and saved states for your account. A canonical job record is permanently deleted only when no other account references it.'}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" className="btn btn-secondary" onClick={() => setDeletePrompt(null)} disabled={deletingJobs}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" onClick={handleDeleteJobs} disabled={deletingJobs} style={{ background: '#b91c1c', borderColor: '#b91c1c' }}>
                {deletingJobs ? <RefreshCw size={15} className="spin" /> : <Trash2 size={15} />}
                {deletingJobs ? 'Deleting...' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Preferences & Experience Modal */}
      {showPreferencesModal && (
        <div className="overlay">
          <div className="modal" style={{ maxWidth: 520 }}>
            <button className="btn btn-ghost" onClick={() => setShowPreferencesModal(false)} style={{ position: 'absolute', top: 16, right: 16 }}>
              <X size={18} />
            </button>

            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8, color: '#fff' }}>
              <SlidersHorizontal size={18} color="#818cf8" /> Candidate Experience & Target Hubs
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 20 }}>
              Specify your experience and optional Indian target cities. Leave all cities unselected to search across India.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
              <div>
                <label className="label">Your work experience range (years)</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="40"
                    className="input"
                    aria-label="Minimum years of your experience"
                    value={experienceMinInput}
                    onChange={(e) => setExperienceMinInput(e.target.value)}
                    placeholder="Minimum"
                  />
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="40"
                    className="input"
                    aria-label="Maximum years of your experience"
                    value={experienceMaxInput}
                    onChange={(e) => setExperienceMaxInput(e.target.value)}
                    placeholder="Maximum"
                  />
                </div>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginTop: 6 }}>
                  Jobs with clear experience requirements outside this range are filtered out. Unspecified requirements remain visible.
                </p>
              </div>

              {/* Multi-Location Selection */}
              <div>
                <label className="label" style={{ marginBottom: 8 }}>Target Regions & Tech Hubs (Select Multiple)</label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', maxHeight: 180, overflowY: 'auto', padding: 10, background: 'rgba(0,0,0,0.2)', borderRadius: 8, border: '1px solid var(--border-glass)' }}>
                  {LOCATION_OPTIONS.map(loc => {
                    const isSelected = selectedLocations.includes(loc.label);
                    return (
                      <button
                        key={loc.id}
                        type="button"
                        onClick={() => toggleLocationSelection(loc.label)}
                        style={{
                          padding: '4px 12px', borderRadius: 99, fontSize: '0.78rem', fontWeight: 600,
                          cursor: 'pointer', transition: 'all 0.15s ease',
                          background: isSelected ? 'rgba(99, 102, 241, 0.3)' : 'rgba(255, 255, 255, 0.05)',
                          border: isSelected ? '1px solid #6366f1' : '1px solid var(--border-glass)',
                          color: isSelected ? '#fff' : 'var(--text-muted)'
                        }}
                      >
                        {loc.label} {isSelected && '✓'}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Salary Expectation with Currency mode */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label className="label">Target Min Salary ({currencyMode === 'INR' ? '₹ LPA' : '$ / yr'})</label>
                  <input
                    type="number"
                    className="input"
                    value={targetMinSalary}
                    onChange={(e) => setTargetMinSalary(e.target.value)}
                    placeholder={currencyMode === 'INR' ? 'e.g. 15.5' : 'e.g. 120000'}
                  />
                </div>
                <div>
                  <label className="label">Target Max Salary ({currencyMode === 'INR' ? '₹ LPA' : '$ / yr'})</label>
                  <input
                    type="number"
                    className="input"
                    value={targetMaxSalary}
                    onChange={(e) => setTargetMaxSalary(e.target.value)}
                    placeholder={currencyMode === 'INR' ? 'e.g. 25.0' : 'e.g. 170000'}
                  />
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setShowPreferencesModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleSavePreferences}>
                Save Preferences
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
