import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from ...core.config import get_settings
from ...db.database import get_db
from ...models import (
    Consultant,
    Department,
    DepartmentSubcategory,
    Feedback,
    FeedbackAIAnalysis,
    FeedbackAudio,
    FeedbackTranscript,
    HODMapping,
    Scheme,
    SystemSetting,
    User,
)
from ...schemas import (
    ConsultantOut,
    DepartmentOut,
    FeedbackCreate,
    FeedbackOut,
    ProcessAudioResponse,
    SchemeOut,
    SubcategoryOut,
)
from ...services.ai.factory import get_ai_providers
from ...services.audio_service import (
    check_audio_quality,
    delete_audio_file_if_policy,
    save_audio_file,
)
from ...services.audit_service import log_audit
from ...services.hod_service import get_deterministic_hod
from ..deps import get_current_user, require_staff_or_admin

router = APIRouter(prefix="/feedback", tags=["Patient Feedback"])
settings = get_settings()


def format_feedback_out(fb: Feedback) -> FeedbackOut:
    has_audio = False
    audio_id = None
    duration = 0.0
    if fb.audio:
        has_audio = fb.audio.file_path is not None
        audio_id = fb.audio.id
        duration = fb.audio.duration_seconds

    orig_lang = "Hindi/English"
    orig_transcript = ""
    eng_trans = ""
    if fb.transcript:
        orig_lang = fb.transcript.original_language
        orig_transcript = fb.transcript.original_transcript
        eng_trans = fb.transcript.english_translation

    complaint_type = "General Feedback"
    complaint_summary = "Not Provided"
    detailed = "Not Provided"
    pos_fb = "Not Provided"
    neg_fb = "Not Provided"
    spec_complaint = "Not Provided"
    sugg_action = "Not Provided"
    priority = "Not Specified"
    ai_dept = None

    if fb.ai_analysis:
        complaint_type = fb.ai_analysis.complaint_type
        complaint_summary = fb.ai_analysis.complaint_summary
        detailed = fb.ai_analysis.detailed_feedback
        pos_fb = fb.ai_analysis.positive_feedback
        neg_fb = fb.ai_analysis.negative_feedback
        spec_complaint = fb.ai_analysis.specific_complaint
        sugg_action = fb.ai_analysis.suggested_action
        priority = fb.ai_analysis.priority
        ai_dept = fb.ai_analysis.suggested_department

    corrections_out = []
    if fb.corrections:
        for c in fb.corrections:
            corrections_out.append(
                {
                    "id": c.id,
                    "field_name": c.field_name,
                    "original_value": c.original_value,
                    "corrected_value": c.corrected_value,
                    "corrected_by_name": c.corrected_by_name,
                    "created_at": c.created_at,
                }
            )

    return FeedbackOut(
        id=fb.id,
        feedback_id=fb.feedback_id,
        client_uuid=fb.client_uuid,
        date_str=fb.date_str,
        time_str=fb.time_str,
        staff_id=fb.staff_id,
        staff_name=fb.staff_name,
        uhid=str(fb.uhid),  # STRICTLY TEXT
        patient_name=fb.patient_name,
        location=fb.location,
        consultant=fb.consultant,
        scheme=fb.scheme,
        attendant_name=fb.attendant_name,
        department=fb.department,
        subcategory=fb.subcategory,
        hod_name=fb.hod_name,
        complaint=getattr(fb, "complaint", None) or complaint_summary or eng_trans or "Not Provided",
        complaint_type=complaint_type,
        complaint_summary=complaint_summary,
        detailed_feedback=detailed,
        positive_feedback=pos_fb,
        negative_feedback=neg_fb,
        specific_complaint=spec_complaint,
        suggested_action=sugg_action,
        priority=priority,
        original_language=orig_lang,
        original_transcript=orig_transcript,
        english_translation=eng_trans,
        duration_seconds=duration,
        has_audio=has_audio,
        audio_file_id=audio_id,
        ai_suggested_department=ai_dept,
        consent_status=getattr(fb, "consent_status", "CONSENT_OBTAINED"),
        consent_timestamp=getattr(fb, "consent_timestamp", fb.created_at),
        status=fb.status,
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        retention_expires_at=(fb.created_at + timedelta(hours=48)) if fb.created_at else None,
        retention_expiry_str=(fb.created_at + timedelta(hours=48)).strftime("%d %b %Y, %I:%M %p") if fb.created_at else None,
        corrections=corrections_out,
    )


@router.post("/process-audio", response_model=ProcessAudioResponse)
async def process_audio(
    audio: UploadFile = File(...),
    client_uuid: Optional[str] = Form(None),
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Modular AI Pipeline:
    AUDIO -> QUALITY CHECK -> STT (Hindi/Hinglish/English) -> TRANSLATION -> LLM STRUCTURING -> DEPT SUGGESTION
    """
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file uploaded.")

    active_uuid = client_uuid or str(uuid.uuid4())

    # 1. Audio Quality Check
    quality_report = check_audio_quality(content)

    # 2. Save file temporarily or persistently in private storage
    file_path, sha256_hash, file_size = save_audio_file(
        content, active_uuid, ext=".webm"
    )

    # 3. Get AI Providers
    stt_provider, trans_provider, llm_provider = get_ai_providers()

    # 4. Transcribe conversation
    transcription = stt_provider.transcribe(
        file_path, mime_type=audio.content_type or "audio/webm"
    )
    orig_transcript = transcription.get("original_transcript", "").strip()
    detected_lang = transcription.get("detected_language", "Mixed").strip()

    # 5. Translate to professional English preserving context
    english_translation = trans_provider.translate_to_english(
        orig_transcript, source_language=detected_lang
    )

    # 6. Structured extraction (NO hallucination, NO diagnosis, 'Not Provided' if missing)
    analysis = llm_provider.extract_structured_feedback(
        orig_transcript, english_translation
    )

    log_audit(
        db=db,
        action="AI_PROCESSING",
        entity_type="AudioSession",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=active_uuid,
        details={
            "duration": quality_report.duration_seconds,
            "language": detected_lang,
            "department_suggested": analysis.get("suggested_department"),
        },
    )

    return ProcessAudioResponse(
        success=True,
        audio_file_id=active_uuid,
        duration_seconds=quality_report.duration_seconds,
        quality_warning=quality_report.message if quality_report.is_low_quality else None,
        original_language=detected_lang,
        original_transcript=orig_transcript,
        english_translation=english_translation,
        complaint=analysis.get("complaint") or english_translation or analysis.get("complaint_summary", "Not Provided"),
        complaint_type=analysis.get("complaint_type", "General Feedback"),
        complaint_summary=analysis.get("complaint_summary", "Not Provided"),
        detailed_feedback=analysis.get("detailed_feedback", "Not Provided"),
        positive_feedback=analysis.get("positive_feedback", "Not Provided"),
        negative_feedback=analysis.get("negative_feedback", "Not Provided"),
        specific_complaint=analysis.get("specific_complaint", "Not Provided"),
        suggested_action=analysis.get("suggested_action", "Not Provided"),
        suggested_department=analysis.get("suggested_department"),
        suggested_subcategory=analysis.get("suggested_subcategory"),
        priority=analysis.get("priority", "Not Specified"),
        confidence_score=analysis.get("confidence_score", 1.0),
    )


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackCreate,
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Final Submission Endpoint.
    1. Mandatory Validation: UHID, Patient Name, Department.
    2. Duplicate Prevention / Idempotency check.
    3. DETERMINISTIC HOD MAPPING: Backend determines HOD.
    4. Save normalized records (Feedback, Transcript, Audio, AI Analysis).
    5. Save audit log.
    """
    # 1. Validation check
    if not body.uhid or not body.uhid.strip():
        raise HTTPException(status_code=422, detail="UHID is required.")
    if not body.patient_name or not body.patient_name.strip():
        raise HTTPException(status_code=422, detail="Patient Name is required.")
    if not body.department or not body.department.strip():
        raise HTTPException(status_code=422, detail="Department is required.")

    clean_uuid = body.client_uuid.strip()

    # 2. Duplicate Prevention (Idempotency check)
    existing = db.scalar(
        select(Feedback)
        .where(Feedback.client_uuid == clean_uuid)
        .options(
            selectinload(Feedback.transcript),
            selectinload(Feedback.audio),
            selectinload(Feedback.ai_analysis),
            selectinload(Feedback.corrections),
        )
    )
    if existing:
        # Already submitted cleanly (e.g. double-tap or offline retry)
        return format_feedback_out(existing)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # Generate sequential or unique Feedback ID like FB-2026-000123
    count_today = db.query(Feedback).count() + 1
    feedback_id = body.feedback_id or f"FB-{now.year}-{count_today:06d}"

    # Check if feedback_id is already taken
    while db.scalar(select(Feedback).where(Feedback.feedback_id == feedback_id)):
        count_today += 1
        feedback_id = f"FB-{now.year}-{count_today:06d}"

    # 3. CRITICAL: Deterministic Backend HOD Mapping
    deterministic_hod = get_deterministic_hod(body.department, db=db)

    # 4. Create Feedback Core
    feedback = Feedback(
        feedback_id=feedback_id,
        client_uuid=clean_uuid,
        date_str=date_str,
        time_str=time_str,
        staff_id=current_user.id,
        staff_name=current_user.display_name,
        uhid=str(body.uhid).strip(),  # Treat strictly as TEXT
        patient_name=body.patient_name.strip(),
        location=body.location.strip() if body.location else None,
        consultant=body.consultant.strip() if body.consultant else None,
        scheme=body.scheme.strip() if body.scheme else None,
        attendant_name=body.attendant_name.strip() if body.attendant_name else None,
        department=body.department.strip(),
        subcategory=body.subcategory.strip() if body.subcategory else None,
        hod_name=deterministic_hod,  # MAPPED BY BACKEND
        complaint=(body.complaint.strip() if body.complaint and body.complaint.strip() else (body.complaint_summary or body.english_translation or "Not Provided")),
        consent_status=body.consent_status or "CONSENT_OBTAINED",
        consent_timestamp=body.consent_timestamp or now,
        status="SUBMITTED",
        is_deleted=False,
    )
    db.add(feedback)
    db.flush()

    # 5. Create Transcript Record
    transcript = FeedbackTranscript(
        feedback_id=feedback.id,
        original_language=body.original_language or "Hindi/English",
        original_transcript=body.original_transcript or "Direct submission without recording",
        english_translation=body.english_translation or "Direct submission without recording",
    )
    db.add(transcript)

    # 6. Create AI Analysis Record
    ai_analysis = FeedbackAIAnalysis(
        feedback_id=feedback.id,
        complaint_type=body.complaint_type or "General Feedback",
        complaint_summary=body.complaint_summary or "Not Provided",
        detailed_feedback=body.detailed_feedback or "Not Provided",
        positive_feedback=body.positive_feedback or "Not Provided",
        negative_feedback=body.negative_feedback or "Not Provided",
        specific_complaint=body.specific_complaint or "Not Provided",
        suggested_action=body.suggested_action or "Not Provided",
        suggested_department=body.ai_suggested_department,
        suggested_subcategory=body.subcategory,
        priority=body.priority or "Not Specified",
        provider_used=settings.AI_PROVIDER,
        confidence_score=1.0,
    )
    db.add(ai_analysis)

    # 7. Create Audio Record if audio_file_id provided
    if body.audio_file_id:
        from ...services.audio_service import ensure_audio_dir

        target_file = ensure_audio_dir() / f"{body.audio_file_id}.webm"
        file_path_str = str(target_file) if target_file.exists() else None
        file_size = target_file.stat().st_size if target_file.exists() else 0

        audio_rec = FeedbackAudio(
            feedback_id=feedback.id,
            file_path=file_path_str,
            file_size_bytes=file_size,
            duration_seconds=body.duration_seconds or 0.0,
            mime_type="audio/webm",
            retention_status="KEPT",
        )
        db.add(audio_rec)

        # Enforce retention policy if set to delete
        delete_audio_file_if_policy(file_path_str)

    db.commit()
    db.refresh(feedback)

    # 8. Audit Log
    log_audit(
        db=db,
        action="FEEDBACK_SUBMITTED",
        entity_type="Feedback",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=feedback.feedback_id,
        details={
            "uhid": feedback.uhid,
            "department": feedback.department,
            "hod": feedback.hod_name,
        },
    )

    # Load relationships for out model
    db.refresh(feedback)
    return format_feedback_out(feedback)


@router.get("/my", response_model=List[FeedbackOut])
def get_my_submissions(
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Staff View: Shows submissions by the logged-in staff member.
    Staff does not have access to full historical patient database.
    """
    records = (
        db.query(Feedback)
        .filter(
            Feedback.staff_id == current_user.id,
            Feedback.is_deleted == False,
        )
        .order_by(desc(Feedback.created_at))
        .limit(100)
        .all()
    )
    return [format_feedback_out(r) for r in records]


@router.get("/master-data")
def get_master_data(db: Session = Depends(get_db)):
    """
    Returns active departments, subcategories, schemes, consultants, and consent text
    for mobile form options.
    """
    depts = (
        db.query(Department)
        .filter(Department.is_active == True)
        .options(selectinload(Department.subcategories))
        .all()
    )
    schemes = db.query(Scheme).filter(Scheme.is_active == True).all()
    consultants = db.query(Consultant).filter(Consultant.is_active == True).all()

    # Consent text setting
    consent_setting = db.scalar(
        select(SystemSetting).where(SystemSetting.key == "consent_notice_text")
    )
    consent_text = (
        consent_setting.value if consent_setting else settings.CONSENT_NOTICE_TEXT
    )

    return {
        "departments": [
            {
                "id": d.id,
                "name": d.name,
                "subcategories": [s.name for s in d.subcategories if s.is_active],
            }
            for d in depts
        ],
        "schemes": [s.name for s in schemes],
        "consultants": [{"name": c.name, "department": c.department} for c in consultants],
        "consent_notice_text": consent_text,
    }
