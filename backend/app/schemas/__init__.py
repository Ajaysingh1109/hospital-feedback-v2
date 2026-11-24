from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# AUTH & USER SCHEMAS
# ============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    username: str
    display_name: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class AdminResetPasswordRequest(BaseModel):
    new_password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "STAFF"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


# ============================================================================
# MASTER DATA SCHEMAS
# ============================================================================

class SubcategoryOut(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class DepartmentOut(BaseModel):
    id: int
    name: str
    is_active: bool
    subcategories: List[SubcategoryOut] = []

    class Config:
        from_attributes = True


class DepartmentCreate(BaseModel):
    name: str
    subcategories: List[str] = []


class HODMappingOut(BaseModel):
    id: int
    department_name: str
    hod_name: str
    is_active: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class HODMappingCreate(BaseModel):
    department_name: str
    hod_name: str
    is_active: Optional[bool] = True


class HODMappingUpdate(BaseModel):
    hod_name: str
    is_active: Optional[bool] = True


class SchemeOut(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class SchemeCreate(BaseModel):
    name: str


class ConsultantOut(BaseModel):
    id: int
    name: str
    department: str
    is_active: bool

    class Config:
        from_attributes = True


class ConsultantCreate(BaseModel):
    name: str
    department: str


# ============================================================================
# AUDIO & AI EXTRACTION SCHEMAS
# ============================================================================

class AudioQualityReport(BaseModel):
    is_low_quality: bool
    message: Optional[str] = None
    duration_seconds: float
    file_size_bytes: int


class ProcessAudioResponse(BaseModel):
    success: bool
    audio_file_id: Optional[str] = None
    duration_seconds: float = 0.0
    quality_warning: Optional[str] = None
    original_language: str = "Hindi/English"
    original_transcript: str = ""
    english_translation: str = ""
    complaint: str = "Not Provided"
    complaint_type: str = "General Feedback"
    complaint_summary: str = "Not Provided"
    detailed_feedback: str = "Not Provided"
    positive_feedback: str = "Not Provided"
    negative_feedback: str = "Not Provided"
    specific_complaint: str = "Not Provided"
    suggested_action: str = "Not Provided"
    suggested_department: Optional[str] = None
    suggested_subcategory: Optional[str] = None
    suggested_location: Optional[str] = None
    priority: str = "Not Specified"
    confidence_score: float = 1.0
    field_provenance: Optional[Dict[str, str]] = None
    diagnostics: Optional[Dict[str, Any]] = None


class ProcessTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw speech or verbatim text input")
    client_uuid: Optional[str] = None
    language_hint: Optional[str] = None



# ============================================================================
# FEEDBACK CREATION & REVIEW SCHEMAS
# ============================================================================

class FeedbackCreate(BaseModel):
    client_uuid: str = Field(..., description="Client-side unique UUID for idempotency")
    feedback_id: Optional[str] = Field(None, description="Client or server assigned ID like FB-2026-000123")

    # MANDATORY FIELDS
    uhid: str = Field(..., min_length=1, description="UHID treated as TEXT, preserving leading zeros")
    patient_name: str = Field(..., min_length=1, description="Full patient name")
    department: str = Field(..., min_length=1, description="Selected department")

    # OPTIONAL PATIENT FIELDS
    location: Optional[str] = None
    consultant: Optional[str] = None
    scheme: Optional[str] = None
    attendant_name: Optional[str] = None

    # CLASSIFICATION & STRUCTURED FEEDBACK
    subcategory: Optional[str] = None
    complaint: Optional[str] = "Not Provided"
    complaint_type: Optional[str] = "Complaint"
    complaint_summary: Optional[str] = "Not Provided"
    detailed_feedback: Optional[str] = "Not Provided"
    positive_feedback: Optional[str] = "Not Provided"
    negative_feedback: Optional[str] = "Not Provided"
    specific_complaint: Optional[str] = "Not Provided"
    suggested_action: Optional[str] = "Not Provided"
    priority: Optional[str] = "Not Specified"

    # TRANSCRIPTS
    original_language: Optional[str] = "Hindi/English"
    original_transcript: Optional[str] = ""
    english_translation: Optional[str] = ""
    duration_seconds: Optional[float] = 0.0

    # AUDIO REFERENCE & CONSENT (SECTION 19)
    audio_file_id: Optional[str] = None
    ai_suggested_department: Optional[str] = None
    suggested_location: Optional[str] = None
    consent_status: Optional[str] = "CONSENT_OBTAINED"
    consent_timestamp: Optional[datetime] = None
    field_provenance: Optional[Dict[str, str]] = None

    @field_validator("uhid")
    @classmethod
    def validate_uhid(cls, v: str) -> str:
        clean = str(v).strip()
        if not clean:
            raise ValueError("UHID is required.")
        return clean

    @field_validator("patient_name")
    @classmethod
    def validate_patient_name(cls, v: str) -> str:
        clean = str(v).strip()
        if not clean:
            raise ValueError("Patient Name is required.")
        return clean

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str) -> str:
        clean = str(v).strip()
        if not clean:
            raise ValueError("Department is required.")
        depts = [d.strip() for d in clean.split(",") if d.strip()]
        if len(depts) > 4:
            raise ValueError("Maximum 4 departments can be selected.")
        return ", ".join(depts)


class FeedbackCorrectionOut(BaseModel):
    id: str
    field_name: str
    original_value: Optional[str]
    corrected_value: Optional[str]
    corrected_by_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackOut(BaseModel):
    id: str
    feedback_id: str
    client_uuid: str
    date_str: str
    time_str: str
    staff_id: str
    staff_name: str

    # Patient info
    uhid: str
    patient_name: str
    location: Optional[str]
    consultant: Optional[str]
    scheme: Optional[str]
    attendant_name: Optional[str]

    # Department & deterministic HOD
    department: str
    subcategory: Optional[str]
    hod_name: str
    complaint: str = "Not Provided"

    # Structured details
    complaint_type: str
    complaint_summary: str
    detailed_feedback: str
    positive_feedback: str
    negative_feedback: str
    specific_complaint: str
    suggested_action: str
    priority: str

    # Transcript info
    original_language: str
    original_transcript: str
    english_translation: str
    duration_seconds: float
    has_audio: bool
    audio_file_id: Optional[str] = None

    # AI tracking & status
    ai_suggested_department: Optional[str]
    consent_status: str = "CONSENT_OBTAINED"
    consent_timestamp: Optional[datetime] = None
    status: str
    processing_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    retention_expires_at: Optional[datetime] = None
    retention_expiry_str: Optional[str] = None
    audio_expires_at: Optional[datetime] = None
    audio_expiry_str: Optional[str] = None
    is_audio_expired: bool = False
    corrections: List[FeedbackCorrectionOut] = []
    field_provenance: Optional[Dict[str, str]] = None

    class Config:
        from_attributes = True


class AsyncFeedbackOut(BaseModel):
    success: bool
    feedback_id: str
    client_uuid: str
    status: str
    message: str = "Saved — Processing in Background"
    feedback: Optional[FeedbackOut] = None



class BulkDeleteRequest(BaseModel):
    feedback_ids: List[str]


class FeedbackListOut(BaseModel):
    items: List[FeedbackOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class FeedbackCorrectionRequest(BaseModel):
    department: Optional[str] = None
    hod_name: Optional[str] = None
    subcategory: Optional[str] = None
    complaint: Optional[str] = None
    complaint_type: Optional[str] = None
    complaint_summary: Optional[str] = None
    detailed_feedback: Optional[str] = None
    positive_feedback: Optional[str] = None
    negative_feedback: Optional[str] = None
    suggested_action: Optional[str] = None
    priority: Optional[str] = None
    location: Optional[str] = None
    consultant: Optional[str] = None
    scheme: Optional[str] = None
    original_transcript: Optional[str] = None
    english_translation: Optional[str] = None


# ============================================================================
# ADMIN ANALYTICS & AUDIT SCHEMAS
# ============================================================================

class AnalyticsSummary(BaseModel):
    total_feedback: int
    today_count: int
    this_week_count: int
    this_month_count: int
    pending_processing: int
    pending_sync: int

    department_counts: Dict[str, int]
    hod_counts: Dict[str, int]
    complaint_type_counts: Dict[str, int]
    priority_counts: Dict[str, int]
    sentiment_counts: Dict[str, int]
    daily_trend: List[Dict[str, Any]]


class AuditLogOut(BaseModel):
    id: str
    actor_id: Optional[str]
    actor_username: str
    action: str
    entity_type: str
    entity_id: Optional[str]
    details_json: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListOut(BaseModel):
    items: List[AuditLogOut]
    total: int



class SystemSettingOut(BaseModel):
    key: str
    value: str
    description: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemSettingUpdate(BaseModel):
    value: str
