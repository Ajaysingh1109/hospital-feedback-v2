export type Role = "ADMIN" | "MASTER" | "STAFF";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  role: Role;
  user_id: string;
  username: string;
  display_name: string;
  must_change_password?: boolean;
}

export interface DepartmentInfo {
  id: number;
  name: string;
  subcategories: string[];
}

export interface MasterData {
  departments: DepartmentInfo[];
  schemes: string[];
  consultants: { name: string; department: string }[];
  consent_notice_text: string;
}

export interface ProcessAudioResult {
  success: boolean;
  audio_file_id?: string;
  duration_seconds: number;
  quality_warning?: string;
  original_language: string;
  original_transcript: string;
  english_translation: string;
  complaint?: string;
  complaint_type: string;
  complaint_summary: string;
  detailed_feedback: string;
  positive_feedback: string;
  negative_feedback: string;
  specific_complaint: string;
  suggested_action: string;
  suggested_department?: string;
  suggested_subcategory?: string;
  priority: string;
  confidence_score: number;
}

export interface FeedbackCorrection {
  id: string;
  field_name: string;
  original_value?: string;
  corrected_value?: string;
  corrected_by_name: string;
  created_at: string;
}

export interface FeedbackRecord {
  id: string;
  feedback_id: string;
  client_uuid: string;
  date_str: string;
  time_str: string;
  staff_id: string;
  staff_name: string;

  // Patient info (UHID is string!)
  uhid: string;
  patient_name: string;
  location?: string;
  consultant?: string;
  scheme?: string;
  attendant_name?: string;

  // Department & HOD
  department: string;
  subcategory?: string;
  hod_name: string;
  complaint: string;

  // Analysis
  complaint_type: string;
  complaint_summary: string;
  detailed_feedback: string;
  positive_feedback: string;
  negative_feedback: string;
  specific_complaint: string;
  suggested_action: string;
  priority: string;

  // Transcripts
  original_language: string;
  original_transcript: string;
  english_translation: string;
  duration_seconds: number;
  has_audio: boolean;
  audio_file_id?: string;

  // Metadata
  ai_suggested_department?: string;
  status: string;
  retention_expires_at?: string;
  retention_expiry_str?: string;
  created_at: string;
  updated_at: string;
  corrections: FeedbackCorrection[];
}

export interface FeedbackListResponse {
  items: FeedbackRecord[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnalyticsSummary {
  total_feedback: number;
  today_count: number;
  this_week_count: number;
  this_month_count: number;
  pending_processing: number;
  pending_sync: number;
  department_counts: Record<string, number>;
  hod_counts: Record<string, number>;
  complaint_type_counts: Record<string, number>;
  priority_counts: Record<string, number>;
  sentiment_counts: Record<string, number>;
  daily_trend: { date: string; count: number }[];
}

export interface OfflineFeedbackItem {
  client_uuid: string;
  created_at: string;
  payload: {
    client_uuid: string;
    uhid: string;
    patient_name: string;
    department: string;
    location?: string;
    consultant?: string;
    scheme?: string;
    attendant_name?: string;
    subcategory?: string;
    complaint?: string;
    complaint_type?: string;
    complaint_summary?: string;
    detailed_feedback?: string;
    positive_feedback?: string;
    negative_feedback?: string;
    specific_complaint?: string;
    suggested_action?: string;
    priority?: string;
    original_language?: string;
    original_transcript?: string;
    english_translation?: string;
    duration_seconds?: number;
    audio_file_id?: string;
    ai_suggested_department?: string;
  };
  audio_blob?: Blob;
  status: "DRAFT" | "READY" | "SYNCING" | "SYNCED" | "FAILED";
  retry_count: number;
  last_error?: string;
}

export interface SessionDraft {
  session_id: string;
  started_at: string;
  step: "record" | "details" | "review";
  audio_blob?: Blob;
  audio_url?: string;
  duration_seconds: number;
  process_result?: ProcessAudioResult;
  form_data: {
    uhid: string;
    patient_name: string;
    department: string;
    location: string;
    consultant: string;
    scheme: string;
    attendant_name: string;
    subcategory: string;
    complaint: string;
    complaint_type: string;
    complaint_summary: string;
    detailed_feedback: string;
    positive_feedback: string;
    negative_feedback: string;
    specific_complaint: string;
    suggested_action: string;
    priority: string;
  };
}
