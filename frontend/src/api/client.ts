import axios from 'axios';
import { sanitizeInput } from '../security/sanitizer';

const API_BASE_URL = 'http://localhost:8000';

// ─── Types matching backend schemas exactly ───────────────────────────────────

export type ApplicationStatus = 'APPLIED' | 'INTERVIEWING' | 'OFFERED' | 'REJECTED' | 'WITHDRAWN';

export interface User {
  id: number;
  username: string;
  email: string;
}

export interface Company {
  id: number;
  name: string | null;
  website: string | null;
  industry: string | null;
  location: string | null;
  description: string | null;
}

export interface Job {
  id: number;
  title: string;
  company_id: number;
  location: string | null;
  job_url: string | null;
  description: string | null;
  employment_type: string | null;
  status: string;
}

export interface Application {
  id: number;
  user_id: number;
  job_id: number;
  status: ApplicationStatus;
  applied_at: string;
  notes: string | null;
}

// Enriched view: Application + joined Job + Company (fetched by frontend)
export interface EnrichedApplication extends Application {
  job?: Job;
  company?: Company;
}

export interface KanbanColumnData {
  items: Application[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface KanbanBoardResponse {
  applied: KanbanColumnData;
  interviewing: KanbanColumnData;
  offered: KanbanColumnData;
  rejected: KanbanColumnData;
  withdrawn: KanbanColumnData;
}

export interface ApplicationPaginatedResponse {
  items: Application[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ScrapePreview {
  job_url: string;
  company_name: string | null;
  title: string | null;
  location: string | null;
  description: string | null;
  notes: string | null;
  status: ApplicationStatus;
}

// ─── Token Management ─────────────────────────────────────────────────────────
const TOKEN_KEY = 'jobpilot_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ─── Axios Instance ───────────────────────────────────────────────────────────
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let onUnauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorizedHandler = handler;
}

export function extractErrorMessage(error: any, fallback = 'An error occurred'): string {
  if (!error) return fallback;
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) => {
        if (typeof d === 'string') return d;
        if (!d) return null;
        // Format FastAPI / Pydantic validation errors nicely with field context
        const field = Array.isArray(d.loc) && d.loc.length > 0 ? d.loc[d.loc.length - 1] : null;
        const fieldName = field && typeof field === 'string' ? field.charAt(0).toUpperCase() + field.slice(1) : null;
        
        if (fieldName && d.type === 'string_too_short' && d.ctx?.min_length) {
          return `${fieldName} must be at least ${d.ctx.min_length} characters long.`;
        }
        if (fieldName && d.type === 'string_too_long' && d.ctx?.max_length) {
          return `${fieldName} cannot exceed ${d.ctx.max_length} characters.`;
        }
        if (fieldName && (d.type?.includes('email') || field.toLowerCase() === 'email')) {
          return `Please enter a valid email address.`;
        }
        if (fieldName && d.msg) {
          return `${fieldName}: ${d.msg}`;
        }
        return d.msg || d.detail || JSON.stringify(d);
      })
      .filter(Boolean);
    if (msgs.length > 0) return msgs.join('; ');
  }
  if (detail && typeof detail === 'object') {
    if (detail.msg) return String(detail.msg);
    if (detail.message) return String(detail.message);
  }
  if (error.response?.data?.message && typeof error.response.data.message === 'string') {
    return error.response.data.message;
  }
  if (error.message && typeof error.message === 'string' && !error.message.startsWith('Request failed with status code')) {
    return error.message;
  }
  if (error.response?.status) {
    if (error.response.status === 401) return 'Unauthorized or invalid credentials.';
    if (error.response.status === 403) return 'Access forbidden.';
    if (error.response.status === 404) return 'Resource not found.';
    if (error.response.status === 409) return 'Data conflict occurred.';
    if (error.response.status === 422) return 'Validation failed. Please check your input.';
    if (error.response.status === 429) return 'Rate limit exceeded. Please wait before trying again.';
    if (error.response.status >= 500) return 'Server error. Please try again later.';
  }
  return fallback;
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginEndpoint = error.config?.url?.includes('/auth/login');
    if (error.response?.status === 401 && !isLoginEndpoint) {
      clearStoredToken();
      onUnauthorizedHandler?.();
    }
    const message = extractErrorMessage(error);
    return Promise.reject(new Error(message));
  }
);

// ─── Auth ─────────────────────────────────────────────────────────────────────
export async function loginUser(username: string, password: string): Promise<{ access_token: string }> {
  const formData = new URLSearchParams();
  formData.append('username', username.trim());
  formData.append('password', password);
  const res = await apiClient.post('/auth/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return res.data;
}

export async function registerUser(username: string, email: string, password: string): Promise<User> {
  const res = await apiClient.post('/users/register', {
    username: username.trim(),
    email: email.trim(),
    password,
  });
  return res.data;
}

export async function getMe(): Promise<User> {
  const res = await apiClient.get('/users/me');
  return res.data;
}

// ─── Applications ─────────────────────────────────────────────────────────────
export async function getKanbanBoard(limit_per_status = 20): Promise<KanbanBoardResponse> {
  const res = await apiClient.get('/applications/kanban', { params: { limit_per_status } });
  return res.data;
}

export async function getApplicationsPaginated(
  status?: ApplicationStatus,
  offset = 0,
  limit = 20
): Promise<ApplicationPaginatedResponse> {
  const params: Record<string, any> = { offset, limit };
  if (status) params.status = status;
  const res = await apiClient.get('/applications', { params });
  return res.data;
}

export async function getMyApplications(skip = 0, limit = 100): Promise<Application[]> {
  const res = await apiClient.get('/applications', { params: { skip, limit } });
  return res.data.items || res.data;
}

export async function previewJobUrl(job_url: string): Promise<ScrapePreview> {
  const res = await apiClient.post('/applications/url/preview', { job_url });
  return res.data;
}

export async function confirmJobUrl(data: {
  job_url: string;
  company_name: string;
  title: string;
  location?: string | null;
  description?: string | null;
  notes?: string | null;
  status?: ApplicationStatus;
}): Promise<Application> {
  const res = await apiClient.post('/applications/url/confirm', {
    ...data,
    company_name: sanitizeInput(data.company_name),
    title: sanitizeInput(data.title),
    location: data.location ? sanitizeInput(data.location) : null,
    notes: data.notes ? sanitizeInput(data.notes) : null,
  });
  return res.data;
}

export async function createManualApplication(data: {
  company_name: string;
  title: string;
  location?: string | null;
  description?: string | null;
  job_url?: string | null;
  notes?: string | null;
  status?: ApplicationStatus;
}): Promise<Application> {
  const res = await apiClient.post('/applications/manual', {
    ...data,
    company_name: sanitizeInput(data.company_name),
    title: sanitizeInput(data.title),
    location: data.location ? sanitizeInput(data.location) : null,
    notes: data.notes ? sanitizeInput(data.notes) : null,
  });
  return res.data;
}

export async function updateApplication(
  id: number,
  data: { status?: ApplicationStatus; notes?: string | null }
): Promise<Application> {
  const res = await apiClient.patch(`/applications/${id}`, {
    ...data,
    notes: data.notes ? sanitizeInput(data.notes) : data.notes,
  });
  return res.data;
}

export async function deleteApplication(id: number): Promise<void> {
  await apiClient.delete(`/applications/${id}`);
}

export async function deleteApplicationsBulk(ids: number[]): Promise<{ message: string }> {
  const res = await apiClient.post('/applications/bulk-delete', { ids });
  return res.data;
}

// ─── Jobs ─────────────────────────────────────────────────────────────────────
export async function getJobs(skip = 0, limit = 100): Promise<Job[]> {
  const res = await apiClient.get('/jobs', { params: { skip, limit } });
  return res.data;
}

export async function getMyJobs(skip = 0, limit = 100): Promise<Job[]> {
  const res = await apiClient.get('/jobs/my', { params: { skip, limit } });
  return res.data;
}

export async function getJob(id: number): Promise<Job> {
  const res = await apiClient.get(`/jobs/${id}`);
  return res.data;
}

// ─── Companies ────────────────────────────────────────────────────────────────
export async function getCompanies(skip = 0, limit = 100): Promise<Company[]> {
  const res = await apiClient.get('/companies/', { params: { skip, limit } });
  return res.data;
}

export async function getMyCompanies(skip = 0, limit = 100): Promise<Company[]> {
  const res = await apiClient.get('/companies/my', { params: { skip, limit } });
  return res.data;
}

export async function getCompany(id: number): Promise<Company> {
  const res = await apiClient.get(`/companies/${id}`);
  return res.data;
}
