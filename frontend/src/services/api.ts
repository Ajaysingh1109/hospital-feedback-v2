import {
  AnalyticsSummary,
  AsyncFeedbackOut,
  AuthResponse,
  FeedbackListResponse,
  FeedbackRecord,
  MasterData,
  ProcessAudioResult,
  QueueStatusResponse,
  User,
} from "../types";

// Dynamic Cloud API Base URL configuration:
// Empty string in development allows Vite proxy (/api -> http://localhost:8001).
// In production or mobile standalone PWA, VITE_API_BASE_URL specifies the HTTPS cloud API domain.
const ENV_API_URL = import.meta.env.VITE_API_BASE_URL;
const IS_NATIVE =
  typeof window !== "undefined" &&
  Boolean((window as any).Capacitor?.isNativePlatform?.());

export const API_BASE = ENV_API_URL
  ? `${ENV_API_URL.replace(/\/+$/, "")}/api/v1`
  : IS_NATIVE
  ? "https://hospital-feedback-v2-2.onrender.com/api/v1"
  : "/api/v1";

function getToken(): string | null {
  return localStorage.getItem("hospital_auth_token");
}

export function setToken(token: string) {
  localStorage.setItem("hospital_auth_token", token);
}

export function clearToken() {
  localStorage.removeItem("hospital_auth_token");
  localStorage.removeItem("hospital_current_user");
}

export function setCurrentUserLocal(user: any | null) {
  if (user) {
    localStorage.setItem("hospital_current_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("hospital_current_user");
  }
}

export function getCurrentUserLocal(): any | null {
  const data = localStorage.getItem("hospital_current_user");
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch (_) {
    return null;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });
  } catch (_netErr) {
    throw new Error("Unable to connect. Please check your internet connection.");
  }

  if (res.status === 401) {
    if (endpoint !== "/auth/login") {
      clearToken();
      sessionStorage.setItem("auth_notice", "Your session has expired. Please sign in again.");
      window.dispatchEvent(new Event("auth:logout"));
      throw new Error("Session expired. Please log in again.");
    }
  }

  if (!res.ok) {
    let errMessage = `Request failed (${res.status})`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        if (Array.isArray(errJson.detail)) {
          errMessage = errJson.detail.join(" ");
        } else {
          errMessage = errJson.detail;
        }
      }
    } catch (_) {}
    throw new Error(errMessage);
  }

  return res.json() as Promise<T>;
}

// ============================================================================
// AUTH API
// ============================================================================

export async function login(
  username: string,
  password: string
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setToken(data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    sessionStorage.removeItem("auth_notice");
    await request("/auth/logout", { method: "POST" });
  } finally {
    clearToken();
    sessionStorage.removeItem("auth_notice");
  }
}

export async function getMe(): Promise<User> {
  return request<User>("/auth/me");
}

export async function changePassword(old_password: string, new_password: string): Promise<any> {
  return request<any>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ old_password, new_password }),
  });
}

// ============================================================================
// FEEDBACK & AUDIO API
// ============================================================================

export async function fetchMasterData(): Promise<MasterData> {
  return request<MasterData>("/feedback/master-data");
}

export async function processAudio(
  audioBlob: Blob,
  clientUuid?: string
): Promise<ProcessAudioResult> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "recording.webm");
  if (clientUuid) {
    formData.append("client_uuid", clientUuid);
  }

  return request<ProcessAudioResult>("/feedback/process-audio", {
    method: "POST",
    body: formData,
  });
}

export async function processText(
  text: string,
  clientUuid?: string
): Promise<ProcessAudioResult> {
  return request<ProcessAudioResult>("/feedback/process-text", {
    method: "POST",
    body: JSON.stringify({ text, client_uuid: clientUuid }),
  });
}


export async function submitFeedback(payload: any): Promise<FeedbackRecord> {
  return request<FeedbackRecord>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function submitAsyncFeedback(formData: FormData): Promise<AsyncFeedbackOut> {
  return request<AsyncFeedbackOut>("/feedback/async", {
    method: "POST",
    body: formData,
  });
}

export async function fetchQueueStatus(): Promise<QueueStatusResponse> {
  return request<QueueStatusResponse>("/feedback/queue-status");
}

export async function fetchMySubmissions(): Promise<FeedbackRecord[]> {
  return request<FeedbackRecord[]>("/feedback/my");
}

// ============================================================================
// ADMIN API
// ============================================================================

export async function fetchAdminAnalytics(): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>("/admin/analytics");
}

export interface AdminFeedbackFilters {
  search?: string;
  start_date?: string;
  end_date?: string;
  department?: string;
  hod?: string;
  staff?: string;
  scheme?: string;
  status?: string;
  priority?: string;
  complaint_type?: string;
  page?: number;
  page_size?: number;
}

export async function fetchAdminFeedback(
  filters: AdminFeedbackFilters = {}
): Promise<FeedbackListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      params.append(k, String(v));
    }
  });
  return request<FeedbackListResponse>(`/admin/feedback?${params.toString()}`);
}

export async function getFeedbackDetail(
  id: string
): Promise<FeedbackRecord> {
  return request<FeedbackRecord>(`/admin/feedback/${id}`);
}

export async function correctFeedback(
  id: string,
  corrections: any
): Promise<FeedbackRecord> {
  return request<FeedbackRecord>(`/admin/feedback/${id}`, {
    method: "PATCH",
    body: JSON.stringify(corrections),
  });
}

export async function deleteFeedback(id: string): Promise<void> {
  await request(`/admin/feedback/${id}`, { method: "DELETE" });
}

export async function bulkDeleteFeedback(feedbackIds: string[]): Promise<{ message: string; purged_count: number }> {
  return request<{ message: string; purged_count: number }>("/admin/feedback/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ feedback_ids: feedbackIds }),
  });
}

export async function triggerRetentionPurge(): Promise<any> {
  return request<any>("/admin/retention/purge-now", {
    method: "POST",
  });
}

export async function fetchAudioBlob(audioId: string): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}/audio/${encodeURIComponent(audioId)}`, {
    headers,
  });
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("Audio recording has expired and been permanently deleted per 12-hour hospital retention policy.");
    }
    if (res.status === 403) {
      throw new Error("Unauthorized: You do not have permission to listen to this recording.");
    }
    throw new Error(`Failed to load audio (${res.status})`);
  }
  return res.blob();
}

export async function downloadExcel(filters: {
  start_date?: string;
  end_date?: string;
  department?: string;
  hod?: string;
  staff?: string;
} = {}): Promise<void> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.append(k, String(v));
  });

  const token = getToken();
  const res = await fetch(`${API_BASE}/admin/export-excel?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    throw new Error("Excel export failed");
  }

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const today = new Date().toISOString().split("T")[0];
  a.download = `Hospital_Feedback_${today}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// User Management
export async function fetchUsers(): Promise<User[]> {
  return request<User[]>("/admin/users");
}

export async function createUser(data: any): Promise<User> {
  return request<User>("/admin/users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateUser(id: string, data: any): Promise<User> {
  return request<User>(`/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<any> {
  return request<any>(`/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

// Settings & Audit
export async function fetchAuditLogs(limit: number = 100): Promise<any[]> {
  return request<any[]>(`/admin/audit-logs?limit=${limit}`);
}

export async function fetchSettings(): Promise<any[]> {
  return request<any[]>("/admin/settings");
}

export async function updateSetting(key: string, value: string): Promise<any> {
  return request<any>(`/admin/settings/${key}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export async function fetchHODMappings(): Promise<any[]> {
  return request<any[]>("/admin/hod-mappings");
}

export async function updateHODMapping(id: number, hod_name: string): Promise<any> {
  return request<any>(`/admin/hod-mappings/${id}`, {
    method: "PUT",
    body: JSON.stringify({ hod_name }),
  });
}

export async function createHODMapping(department_name: string, hod_name: string): Promise<any> {
  return request<any>("/admin/hod-mappings", {
    method: "POST",
    body: JSON.stringify({ department_name, hod_name }),
  });
}

export async function restoreDefaultHODMappings(): Promise<any[]> {
  return request<any[]>("/admin/hod-mappings/restore-defaults", {
    method: "POST",
  });
}
