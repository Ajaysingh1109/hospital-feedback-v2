from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...core.config import get_settings
from ...core.security import decode_access_token, hash_password
from ...db.database import get_db
from ...models import (
    AuditLog,
    Consultant,
    Department,
    DepartmentSubcategory,
    Feedback,
    FeedbackAIAnalysis,
    FeedbackAudio,
    FeedbackCorrection,
    FeedbackTranscript,
    HODMapping,
    RoleEnum,
    Scheme,
    SystemSetting,
    User,
)
from ...schemas import (
    AdminResetPasswordRequest,
    AnalyticsSummary,
    AuditLogListOut,
    AuditLogOut,
    BulkDeleteRequest,
    ConsultantCreate,
    ConsultantOut,
    DepartmentCreate,
    DepartmentOut,
    FeedbackCorrectionRequest,
    FeedbackListOut,
    FeedbackOut,
    HODMappingCreate,
    HODMappingOut,
    HODMappingUpdate,
    SchemeCreate,
    SchemeOut,
    SystemSettingOut,
    SystemSettingUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from ...services.audit_service import log_audit
from ...services.excel_service import generate_feedback_excel
from ...services.hod_service import get_deterministic_hod
from ...services.retention_service import (
    purge_bulk_feedbacks,
    purge_single_feedback,
    run_automatic_retention_purge,
)
from ..deps import require_admin
from .feedback import format_feedback_out

router = APIRouter(prefix="/admin", tags=["Admin Portal"])
settings = get_settings()


# ============================================================================
# DASHBOARD ANALYTICS
# ============================================================================

@router.get("/analytics", response_model=AnalyticsSummary)
def get_analytics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    base_query = db.query(Feedback).filter(Feedback.is_deleted == False)

    total_count = base_query.count()
    today_count = base_query.filter(Feedback.date_str == today_str).count()
    this_week_count = base_query.filter(Feedback.date_str >= week_ago).count()
    this_month_count = base_query.filter(Feedback.date_str >= month_ago).count()

    # Department counts (supports single and multi-department records)
    dept_rows = (
        db.query(Feedback.department)
        .filter(Feedback.is_deleted == False)
        .all()
    )
    dept_counts: dict = {}
    for (d,) in dept_rows:
        if d:
            for sub_d in [x.strip() for x in d.split(",") if x.strip()]:
                dept_counts[sub_d] = dept_counts.get(sub_d, 0) + 1

    # HOD counts
    hod_rows = (
        db.query(Feedback.hod_name, func.count(Feedback.id))
        .filter(Feedback.is_deleted == False)
        .group_by(Feedback.hod_name)
        .all()
    )
    hod_counts = {r[0]: r[1] for r in hod_rows}

    # Complaint type counts
    type_rows = (
        db.query(FeedbackAIAnalysis.complaint_type, func.count(FeedbackAIAnalysis.id))
        .join(Feedback, Feedback.id == FeedbackAIAnalysis.feedback_id)
        .filter(Feedback.is_deleted == False)
        .group_by(FeedbackAIAnalysis.complaint_type)
        .all()
    )
    complaint_type_counts = {r[0] or "General": r[1] for r in type_rows}

    # Priority counts
    priority_rows = (
        db.query(FeedbackAIAnalysis.priority, func.count(FeedbackAIAnalysis.id))
        .join(Feedback, Feedback.id == FeedbackAIAnalysis.feedback_id)
        .filter(Feedback.is_deleted == False)
        .group_by(FeedbackAIAnalysis.priority)
        .all()
    )
    priority_counts = {r[0] or "Not Specified": r[1] for r in priority_rows}

    # Sentiment / Positive vs Negative stats
    pos_count = (
        db.query(FeedbackAIAnalysis)
        .join(Feedback, Feedback.id == FeedbackAIAnalysis.feedback_id)
        .filter(
            Feedback.is_deleted == False,
            FeedbackAIAnalysis.positive_feedback != "Not Provided",
            FeedbackAIAnalysis.positive_feedback != "",
        )
        .count()
    )
    neg_count = (
        db.query(FeedbackAIAnalysis)
        .join(Feedback, Feedback.id == FeedbackAIAnalysis.feedback_id)
        .filter(
            Feedback.is_deleted == False,
            FeedbackAIAnalysis.negative_feedback != "Not Provided",
            FeedbackAIAnalysis.negative_feedback != "",
        )
        .count()
    )
    sentiment_counts = {
        "Positive Feedback": pos_count,
        "Negative / Complaints": neg_count,
    }

    # Daily trend (last 7 days)
    daily_rows = (
        db.query(Feedback.date_str, func.count(Feedback.id))
        .filter(Feedback.is_deleted == False, Feedback.date_str >= week_ago)
        .group_by(Feedback.date_str)
        .order_by(Feedback.date_str)
        .all()
    )
    daily_trend = [{"date": r[0], "count": r[1]} for r in daily_rows]

    return AnalyticsSummary(
        total_feedback=total_count,
        today_count=today_count,
        this_week_count=this_week_count,
        this_month_count=this_month_count,
        pending_processing=0,
        pending_sync=0,
        department_counts=dept_counts,
        hod_counts=hod_counts,
        complaint_type_counts=complaint_type_counts,
        priority_counts=priority_counts,
        sentiment_counts=sentiment_counts,
        daily_trend=daily_trend,
    )


# ============================================================================
# FEEDBACK TABLE, SEARCH & FILTER
# ============================================================================

@router.get("/feedback", response_model=FeedbackListOut)
def list_feedback(
    search: Optional[str] = Query(None, description="Search UHID, name, ID, consultant, keywords"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    hod: Optional[str] = Query(None),
    staff: Optional[str] = Query(None),
    scheme: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = Query(None),
    complaint_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Feedback)
        .outerjoin(Feedback.ai_analysis)
        .outerjoin(Feedback.transcript)
        .filter(Feedback.is_deleted == False)
    )

    # Multi-field search
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Feedback.uhid.ilike(term),
                Feedback.patient_name.ilike(term),
                Feedback.feedback_id.ilike(term),
                Feedback.consultant.ilike(term),
                Feedback.staff_name.ilike(term),
                Feedback.department.ilike(term),
                Feedback.hod_name.ilike(term),
                FeedbackAIAnalysis.complaint_summary.ilike(term),
                FeedbackTranscript.original_transcript.ilike(term),
                FeedbackTranscript.english_translation.ilike(term),
            )
        )

    # Filters
    if start_date:
        query = query.filter(Feedback.date_str >= start_date)
    if end_date:
        query = query.filter(Feedback.date_str <= end_date)
    if department:
        query = query.filter(Feedback.department.ilike(f"%{department}%"))
    if hod:
        query = query.filter(Feedback.hod_name.ilike(hod))
    if staff:
        query = query.filter(Feedback.staff_name.ilike(f"%{staff}%"))
    if scheme:
        query = query.filter(Feedback.scheme.ilike(scheme))
    if status_filter:
        query = query.filter(Feedback.status == status_filter)
    if priority:
        query = query.filter(FeedbackAIAnalysis.priority == priority)
    if complaint_type:
        query = query.filter(FeedbackAIAnalysis.complaint_type == complaint_type)

    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(desc(Feedback.created_at)).offset(offset).limit(page_size).all()
    total_pages = max(1, (total + page_size - 1) // page_size)

    return FeedbackListOut(
        items=[format_feedback_out(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/feedback/{feedback_id}", response_model=FeedbackOut)
def get_feedback_detail(
    feedback_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    fb = db.scalar(
        select(Feedback)
        .where(
            or_(Feedback.id == feedback_id, Feedback.feedback_id == feedback_id),
            Feedback.is_deleted == False,
        )
    )
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback record not found.")
    return format_feedback_out(fb)


@router.patch("/feedback/{feedback_id}", response_model=FeedbackOut)
def correct_feedback(
    feedback_id: str,
    corrections: FeedbackCorrectionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Controlled correction system:
    Stores original AI value, corrected value, editor, and timestamp.
    If department is modified, deterministically re-maps HOD!
    """
    fb = db.scalar(
        select(Feedback).where(
            or_(Feedback.id == feedback_id, Feedback.feedback_id == feedback_id),
            Feedback.is_deleted == False,
        )
    )
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    corr_dict = corrections.model_dump(exclude_unset=True)

    for field, new_val in corr_dict.items():
        if new_val is None:
            continue

        orig_val = None
        if field == "department":
            orig_val = fb.department
            if orig_val != new_val:
                fb.department = new_val.strip()
                # DETERMINISTIC RE-MAPPING
                new_hod = get_deterministic_hod(new_val.strip(), db=db)
                fb.hod_name = new_hod

        elif field == "subcategory":
            orig_val = fb.subcategory
            fb.subcategory = new_val.strip()
        elif field == "location":
            orig_val = fb.location
            fb.location = new_val.strip()
        elif field == "consultant":
            orig_val = fb.consultant
            fb.consultant = new_val.strip()
        elif field == "scheme":
            orig_val = fb.scheme
            fb.scheme = new_val.strip()
        elif field == "complaint":
            orig_val = getattr(fb, "complaint", None)
            fb.complaint = new_val.strip()
        elif field == "original_transcript":
            if fb.transcript:
                orig_val = fb.transcript.original_transcript
                fb.transcript.original_transcript = new_val.strip()
            else:
                fb.transcript = FeedbackTranscript(
                    feedback_id=fb.id,
                    original_transcript=new_val.strip(),
                    english_translation=new_val.strip(),
                )
        elif field == "english_translation":
            if fb.transcript:
                orig_val = fb.transcript.english_translation
                fb.transcript.english_translation = new_val.strip()
            else:
                fb.transcript = FeedbackTranscript(
                    feedback_id=fb.id,
                    original_transcript="",
                    english_translation=new_val.strip(),
                )
        elif field == "complaint_type":
            if fb.ai_analysis:
                orig_val = fb.ai_analysis.complaint_type
                fb.ai_analysis.complaint_type = new_val.strip()
            else:
                fb.ai_analysis = FeedbackAIAnalysis(
                    feedback_id=fb.id,
                    complaint_type=new_val.strip(),
                )
        elif fb.ai_analysis:
            # AI fields
            if hasattr(fb.ai_analysis, field):
                orig_val = getattr(fb.ai_analysis, field)
                setattr(fb.ai_analysis, field, new_val.strip())

        # Save correction record
        correction_entry = FeedbackCorrection(
            feedback_id=fb.id,
            field_name=field,
            original_value=str(orig_val) if orig_val is not None else None,
            corrected_value=str(new_val).strip(),
            corrected_by_id=current_user.id,
            corrected_by_name=current_user.display_name,
        )
        db.add(correction_entry)

    db.commit()
    db.refresh(fb)

    log_audit(
        db=db,
        action="ADMIN_CORRECTION",
        entity_type="Feedback",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=fb.feedback_id,
        details={"fields_corrected": list(corr_dict.keys())},
    )

    return format_feedback_out(fb)


@router.delete("/feedback/{feedback_id}")
def delete_feedback(
    feedback_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Permanent manual deletion of a single feedback complaint:
    Purges feedback record, transcript, AI analysis, and associated audio file.
    Admin/Master only.
    """
    fb = db.scalar(
        select(Feedback).where(
            or_(Feedback.id == feedback_id, Feedback.feedback_id == feedback_id)
        )
    )
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    target_fid = fb.feedback_id
    success = purge_single_feedback(fb, db=db, actor=current_user, reason="MANUAL_DELETE")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to purge feedback record.")

    return {
        "message": f"Feedback {target_fid} and associated audio have been permanently deleted.",
        "feedback_id": target_fid,
    }


@router.post("/feedback/bulk-delete")
def bulk_delete_feedback(
    body: BulkDeleteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Bulk permanent deletion of multiple selected feedback complaints:
    Purges feedback records, transcripts, AI analysis, and associated audio files.
    Admin/Master only.
    """
    if not body.feedback_ids:
        raise HTTPException(status_code=400, detail="No feedback IDs provided for bulk deletion.")

    count = purge_bulk_feedbacks(body.feedback_ids, db=db, actor=current_user)
    return {
        "message": f"Successfully permanently deleted {count} feedback records and associated audio.",
        "purged_count": count,
    }


@router.post("/retention/purge-now")
def trigger_retention_purge(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Manually triggers the automatic 12-hour retention purge job.
    Admin/Master only.
    """
    result = run_automatic_retention_purge(db=db, retention_hours=12)
    return result


@router.post("/retention/cron-trigger")
def cron_trigger_retention_purge(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Secure Webhook endpoint for Cloud Schedulers (AWS EventBridge, GCP Cloud Scheduler, Render Cron, K8s CronJob).
    Can be authenticated by Header 'X-Cron-Key: <CRON_SECRET>' or Bearer Admin token.
    """
    cron_key = request.headers.get("X-Cron-Key")
    auth_header = request.headers.get("Authorization")

    is_authorized = False
    if cron_key and cron_key == settings.CRON_SECRET:
        is_authorized = True
    elif auth_header:
        try:
            token = auth_header.replace("Bearer ", "").strip()
            payload = decode_access_token(token)
            if payload and payload.get("role") in ["ADMIN", "MASTER"]:
                is_authorized = True
        except Exception:
            pass

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: valid X-Cron-Key or Admin Bearer token required.",
        )

    result = run_automatic_retention_purge(db=db, retention_hours=12)
    return result


# ============================================================================
# EXCEL EXPORT
# ============================================================================

@router.get("/export-excel")
def export_excel(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    hod: Optional[str] = Query(None),
    staff: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Production-grade Excel Export (.xlsx)
    - One row per feedback
    - English headers
    - Frozen header row
    - Wrap long text
    - Preserves UHID as text with leading zeros
    """
    query = (
        db.query(Feedback)
        .filter(Feedback.is_deleted == False)
        .options(
            selectinload(Feedback.transcript),
            selectinload(Feedback.audio),
            selectinload(Feedback.ai_analysis),
        )
    )

    if start_date:
        query = query.filter(Feedback.date_str >= start_date)
    if end_date:
        query = query.filter(Feedback.date_str <= end_date)
    if department:
        query = query.filter(Feedback.department.ilike(f"%{department}%"))
    if hod:
        query = query.filter(Feedback.hod_name.ilike(hod))
    if staff:
        query = query.filter(Feedback.staff_name.ilike(f"%{staff}%"))

    feedbacks = query.order_by(desc(Feedback.created_at)).all()

    excel_bytes = generate_feedback_excel(feedbacks)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"Hospital_Feedback_{today_str}.xlsx"

    log_audit(
        db=db,
        action="EXCEL_EXPORT",
        entity_type="Report",
        actor_username=current_user.username,
        actor_id=current_user.id,
        details={"rows_exported": len(feedbacks), "filename": filename},
    )

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# USER MANAGEMENT (3 STAFF + 1 ADMIN)
# ============================================================================

@router.get("/users", response_model=List[UserOut])
def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.role, User.username).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clean_username = body.username.strip().lower()
    existing = db.scalar(select(User).where(User.username == clean_username))
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    new_user = User(
        username=clean_username,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        role=RoleEnum[body.role.upper()] if body.role.upper() in RoleEnum.__members__ else RoleEnum.STAFF,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit(
        db=db,
        action="USER_CREATED",
        entity_type="User",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=new_user.id,
        details={"username": new_user.username, "role": new_user.role.value},
    )
    return new_user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.role is not None and body.role.upper() in RoleEnum.__members__:
        user.role = RoleEnum[body.role.upper()]
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)

    log_audit(
        db=db,
        action="USER_UPDATED",
        entity_type="User",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=user.id,
        details={"is_active": user.is_active, "role": user.role.value},
    )
    return user


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if len(body.new_password.strip()) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    db.commit()

    log_audit(
        db=db,
        action="USER_PASSWORD_RESET_BY_ADMIN",
        entity_type="User",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=user.id,
        details={"target_username": user.username},
    )
    return {"message": f"Password reset successfully for {user.username}. User will be required to change password on next login."}



# ============================================================================
# MASTER DATA: DEPARTMENTS, HOD MAPPINGS, SCHEMES, CONSULTANTS
# ============================================================================

@router.get("/departments", response_model=List[DepartmentOut])
def list_departments(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Department).options(selectinload(Department.subcategories)).all()


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    body: DepartmentCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clean_name = body.name.strip()
    existing = db.scalar(select(Department).where(Department.name.ilike(clean_name)))
    if existing:
        raise HTTPException(status_code=400, detail="Department already exists.")

    dept = Department(name=clean_name, is_active=True)
    db.add(dept)
    db.flush()

    for sub in body.subcategories:
        if sub.strip():
            db.add(DepartmentSubcategory(department_id=dept.id, name=sub.strip(), is_active=True))

    db.commit()
    db.refresh(dept)
    return dept


@router.get("/hod-mappings", response_model=List[HODMappingOut])
def list_hod_mappings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(HODMapping).order_by(HODMapping.department_name).all()


@router.put("/hod-mappings/{mapping_id}", response_model=HODMappingOut)
def update_hod_mapping(
    mapping_id: int,
    body: HODMappingUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    mapping = db.scalar(select(HODMapping).where(HODMapping.id == mapping_id))
    if not mapping:
        raise HTTPException(status_code=404, detail="HOD mapping entry not found.")

    old_hod = mapping.hod_name
    mapping.hod_name = body.hod_name.strip()
    if body.is_active is not None:
        mapping.is_active = body.is_active

    db.commit()
    db.refresh(mapping)

    log_audit(
        db=db,
        action="HOD_MAPPING_CHANGE",
        entity_type="HODMapping",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=str(mapping.id),
        details={
            "department": mapping.department_name,
            "old_hod": old_hod,
            "new_hod": mapping.hod_name,
        },
    )
    return mapping


@router.post("/hod-mappings", response_model=HODMappingOut, status_code=status.HTTP_201_CREATED)
def create_hod_mapping(
    body: HODMappingCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clean_dept = body.department_name.strip()
    clean_hod = body.hod_name.strip()
    if not clean_dept or not clean_hod:
        raise HTTPException(status_code=400, detail="Department name and HOD name are required.")

    existing = db.scalar(select(HODMapping).where(func.lower(HODMapping.department_name) == clean_dept.lower()))
    if existing:
        existing.hod_name = clean_hod
        existing.is_active = body.is_active if body.is_active is not None else True
        db.commit()
        db.refresh(existing)
        return existing

    mapping = HODMapping(
        department_name=clean_dept,
        hod_name=clean_hod,
        is_active=body.is_active if body.is_active is not None else True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    log_audit(
        db=db,
        action="HOD_MAPPING_CREATE",
        entity_type="HODMapping",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=str(mapping.id),
        details={"department": clean_dept, "hod": clean_hod},
    )
    return mapping


@router.post("/hod-mappings/restore-defaults", response_model=List[HODMappingOut])
def restore_default_hod_mappings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from ...services.hod_service import STANDARD_HOD_BY_DEPT
    for dept_name, hod_name in STANDARD_HOD_BY_DEPT.items():
        mapping = db.scalar(select(HODMapping).where(func.lower(HODMapping.department_name) == dept_name.lower()))
        if mapping:
            mapping.hod_name = hod_name
            mapping.is_active = True
        else:
            db.add(HODMapping(department_name=dept_name, hod_name=hod_name, is_active=True))
    db.commit()

    log_audit(
        db=db,
        action="HOD_MAPPINGS_RESTORE_DEFAULTS",
        entity_type="HODMapping",
        actor_username=current_user.username,
        actor_id=current_user.id,
    )
    return db.query(HODMapping).order_by(HODMapping.department_name).all()


@router.get("/schemes", response_model=List[SchemeOut])
def list_schemes(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Scheme).order_by(Scheme.name).all()


@router.post("/schemes", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(
    body: SchemeCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clean_name = body.name.strip()
    existing = db.scalar(select(Scheme).where(Scheme.name.ilike(clean_name)))
    if existing:
        raise HTTPException(status_code=400, detail="Scheme already exists.")

    scheme = Scheme(name=clean_name, is_active=True)
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return scheme


@router.get("/consultants", response_model=List[ConsultantOut])
def list_consultants(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Consultant).order_by(Consultant.department, Consultant.name).all()


@router.post("/consultants", response_model=ConsultantOut, status_code=status.HTTP_201_CREATED)
def create_consultant(
    body: ConsultantCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    consultant = Consultant(name=body.name.strip(), department=body.department.strip(), is_active=True)
    db.add(consultant)
    db.commit()
    db.refresh(consultant)
    return consultant


# ============================================================================
# SETTINGS & AUDIT LOGS
# ============================================================================

@router.get("/settings", response_model=List[SystemSettingOut])
def list_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(SystemSetting).all()


@router.put("/settings/{key}", response_model=SystemSettingOut)
def update_setting(
    key: str,
    body: SystemSettingUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not setting:
        setting = SystemSetting(key=key, value=body.value, description=f"Setting for {key}")
        db.add(setting)
    else:
        setting.value = body.value

    db.commit()
    db.refresh(setting)

    log_audit(
        db=db,
        action="SYSTEM_SETTING_CHANGE",
        entity_type="SystemSetting",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=key,
        details={"value": body.value},
    )
    return setting


@router.get("/audit-logs", response_model=List[AuditLogOut])
def list_audit_logs(
    limit: int = Query(100, le=500),
    action: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.order_by(desc(AuditLog.created_at)).limit(limit).all()
