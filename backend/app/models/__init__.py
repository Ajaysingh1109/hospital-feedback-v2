import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    MASTER = "MASTER"
    STAFF = "STAFF"


class SyncStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"


class PriorityEnum(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"
    NOT_SPECIFIED = "Not Specified"


class ComplaintTypeEnum(str, enum.Enum):
    COMPLAINT = "Complaint"
    SUGGESTION = "Suggestion"
    APPRECIATION = "Appreciation"
    QUERY = "Query"
    GENERAL_FEEDBACK = "General Feedback"


# ============================================================================
# USER & ROLE
# ============================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.STAFF, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ============================================================================
# MASTER DATA: DEPARTMENTS, SUBCATEGORIES, HOD MAPPINGS, SCHEMES, CONSULTANTS
# ============================================================================

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subcategories: Mapped[List["DepartmentSubcategory"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )


class DepartmentSubcategory(Base):
    __tablename__ = "department_subcategories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped[Department] = relationship(back_populates="subcategories")


class HODMapping(Base):
    """
    Critical business rule:
    Deterministic mapping from department -> fixed HOD.
    Managed by backend and admin master data.
    """
    __tablename__ = "hod_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hod_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Scheme(Base):
    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Consultant(Base):
    __tablename__ = "consultants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ============================================================================
# FEEDBACK CORE & SUB-TABLES (NORMALIZED)
# ============================================================================

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    feedback_id: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    client_uuid: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Date and Time
    date_str: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    time_str: Mapped[str] = mapped_column(String(10), nullable=False)  # HH:MM:SS

    # Staff attribution
    staff_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    staff_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Patient Details (UHID IS TEXT! Preserves leading zeroes)
    uhid: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    patient_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    consultant: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scheme: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attendant_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Classification & Fixed Deterministic HOD Mapping
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hod_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    complaint: Mapped[str] = mapped_column(Text, default="Not Provided")

    # Submission metadata & Recording Consent (Section 19)
    consent_status: Mapped[str] = mapped_column(String(50), default="CONSENT_OBTAINED", nullable=False)
    consent_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SUBMITTED", index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    staff: Mapped[User] = relationship(foreign_keys=[staff_id])
    transcript: Mapped[Optional["FeedbackTranscript"]] = relationship(
        back_populates="feedback", uselist=False, cascade="all, delete-orphan"
    )
    audio: Mapped[Optional["FeedbackAudio"]] = relationship(
        back_populates="feedback", uselist=False, cascade="all, delete-orphan"
    )
    ai_analysis: Mapped[Optional["FeedbackAIAnalysis"]] = relationship(
        back_populates="feedback", uselist=False, cascade="all, delete-orphan"
    )
    corrections: Mapped[List["FeedbackCorrection"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan"
    )


class FeedbackTranscript(Base):
    __tablename__ = "feedback_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), unique=True, nullable=False)
    original_language: Mapped[str] = mapped_column(String(50), default="Hindi/English")
    original_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    english_translation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feedback: Mapped[Feedback] = relationship(back_populates="transcript")


class FeedbackAudio(Base):
    __tablename__ = "feedback_audio"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), unique=True, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    mime_type: Mapped[str] = mapped_column(String(50), default="audio/webm")
    retention_status: Mapped[str] = mapped_column(String(30), default="KEPT")  # 'KEPT' or 'DELETED_AFTER_PROCESSING'
    sha256_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feedback: Mapped[Feedback] = relationship(back_populates="audio")


class FeedbackAIAnalysis(Base):
    __tablename__ = "feedback_ai_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), unique=True, nullable=False)

    complaint_type: Mapped[str] = mapped_column(String(50), default="General Feedback")
    complaint_summary: Mapped[str] = mapped_column(Text, default="Not Provided")
    detailed_feedback: Mapped[str] = mapped_column(Text, default="Not Provided")
    positive_feedback: Mapped[str] = mapped_column(Text, default="Not Provided")
    negative_feedback: Mapped[str] = mapped_column(Text, default="Not Provided")
    specific_complaint: Mapped[str] = mapped_column(Text, default="Not Provided")
    suggested_action: Mapped[str] = mapped_column(Text, default="Not Provided")
    suggested_department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suggested_subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="Not Specified")

    provider_used: Mapped[str] = mapped_column(String(50), default="mock")
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    raw_response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feedback: Mapped[Feedback] = relationship(back_populates="ai_analysis")


class FeedbackCorrection(Base):
    """
    Tracking system for admin/staff manual corrections.
    Preserves original AI output without erasing it.
    """
    __tablename__ = "feedback_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    original_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    corrected_by_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    feedback: Mapped[Feedback] = relationship(back_populates="corrections")


# ============================================================================
# SYNC QUEUE, AUDIT LOG & SYSTEM SETTINGS
# ============================================================================

class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    client_uuid: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    feedback_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    sync_status: Mapped[SyncStatusEnum] = mapped_column(Enum(SyncStatusEnum), default=SyncStatusEnum.DRAFT)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    actor_username: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
