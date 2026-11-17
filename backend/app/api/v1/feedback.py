import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("hospital_feedback.feedback")

from fastapi import (
    APIRouter,
    BackgroundTasks,
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
    AsyncFeedbackOut,
    ConsultantOut,
    DepartmentOut,
    FeedbackCreate,
    FeedbackOut,
    ProcessAudioResponse,
    ProcessTextRequest,
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
from ...services.hospital_normalization import (
    extract_and_normalize_location,
    normalize_explicit_location,
)
from ..deps import get_current_user, require_staff_or_admin

router = APIRouter(prefix="/feedback", tags=["Patient Feedback"])
settings = get_settings()


def format_feedback_out(fb: Feedback) -> FeedbackOut:
    retention_exp = None
    retention_exp_str = None
    is_audio_expired = False
    now_utc = datetime.now(timezone.utc)

    if fb.created_at:
        created_utc = fb.created_at if fb.created_at.tzinfo else fb.created_at.replace(tzinfo=timezone.utc)
        retention_exp = created_utc + timedelta(hours=12)
        retention_exp_str = retention_exp.strftime("%d %b %Y, %I:%M %p")
        if now_utc > retention_exp:
            is_audio_expired = True

    has_audio = False
    audio_id = None
    duration = 0.0
    if fb.audio:
        audio_id = fb.audio.id
        duration = fb.audio.duration_seconds
        # Audio is streamable only if within 12 hours and file physically exists on persistent storage
        if not is_audio_expired and fb.audio.file_path and Path(fb.audio.file_path).exists():
            has_audio = True

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
        processing_error=getattr(fb, "processing_error", None),
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        retention_expires_at=retention_exp,
        retention_expiry_str=retention_exp_str,
        audio_expires_at=retention_exp,
        audio_expiry_str=retention_exp_str,
        is_audio_expired=is_audio_expired,
        corrections=corrections_out,
        field_provenance={
            "uhid": "STAFF_ENTERED",
            "patient_name": "STAFF_ENTERED",
            "consultant": "STAFF_ENTERED",
            "department": "STAFF_ENTERED",
            "location": "STAFF_ENTERED",
            "scheme": "STAFF_ENTERED",
            "original_transcript": "EXPLICITLY_SPOKEN",
            "complaint": "EXPLICITLY_SPOKEN" if fb.complaint != "Not Provided" else "NOT_PROVIDED",
            "complaint_summary": "EXPLICITLY_SPOKEN" if complaint_summary != "Not Provided" else "NOT_PROVIDED",
            "complaint_type": "AI_DERIVED",
            "hod_name": "SYSTEM_RESOLVED",
        },
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

    # 1. Audio Quality & Length Check
    quality_report = check_audio_quality(content)
    if len(content) < 1500 or quality_report.is_low_quality:
        logger.info(
            "VOICE_DEBUG: mime_type=%s size_bytes=%d duration_ms=%d status=AUDIO_TOO_SHORT",
            audio.content_type or "audio/webm",
            len(content),
            int(quality_report.duration_seconds * 1000),
        )
        raise HTTPException(
            status_code=400,
            detail="Speech could not be understood. Audio appears silent or too short. Please record again.",
        )

    # 2. Save file temporarily or persistently in private storage
    file_path, sha256_hash, file_size = save_audio_file(
        content, active_uuid, ext=".webm"
    )

    # 3. Get AI Providers with explicit failure reporting
    try:
        stt_provider, trans_provider, llm_provider = get_ai_providers()
    except Exception as e:
        logger.error(f"[AI Factory] Provider resolution failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Voice service is not configured. Please contact the administrator.",
        )

    # 4. Transcribe conversation
    transcription = stt_provider.transcribe(
        file_path, mime_type=audio.content_type or "audio/webm"
    )
    orig_transcript = transcription.get("original_transcript", "").strip()
    detected_lang = transcription.get("detected_language", "Mixed").strip()
    stt_success = bool(orig_transcript)

    # Log safe diagnostic VOICE_DEBUG
    logger.info(
        "VOICE_DEBUG: stt_provider=%s stt_model=%s stt_success=%s transcript_length=%d",
        settings.AI_PROVIDER,
        getattr(stt_provider, "model_name", "default"),
        stt_success,
        len(orig_transcript),
    )

    # CRITICAL EMPTY / FAILED TRANSCRIPT SAFETY:
    # If STT failed or returned empty transcript: DO NOT call LLM!
    if not stt_success or not orig_transcript:
        raise HTTPException(
            status_code=400,
            detail="Speech could not be understood. Please record again.",
        )

    # Suspiciously short check (e.g. 'uh', 'um', 'haan', 'yes', 'ok')
    suspicious_fillers = {"uh", "um", "haan", "ha", "yes", "no", "ok", "hmm", "hmmm", "na", "achha"}
    words = [w.strip(".,!?") for w in orig_transcript.lower().split() if w.strip(".,!?")]
    if len(orig_transcript) < 4 or (len(words) <= 1 and words and words[0] in suspicious_fillers):
        raise HTTPException(
            status_code=400,
            detail="Speech was too short or unclear to understand. Please record again or enter details manually.",
        )

    # 5. Translate to professional English preserving context
    try:
        english_translation = trans_provider.translate_to_english(
            orig_transcript, source_language=detected_lang
        )
        translation_success = bool(english_translation and english_translation.strip())
    except Exception as e:
        logger.error(f"[Translation] Translation failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Translation service unavailable: {e}",
        )

    # 6. Structured extraction (NO hallucination, NO diagnosis, 'Not Provided' if missing)
    try:
        analysis = llm_provider.extract_structured_feedback(
            orig_transcript, english_translation
        )
        ai_analysis_success = bool(analysis and analysis.get("complaint"))
    except Exception as e:
        logger.error(f"[LLM] Structured extraction failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AI analysis unavailable: {e}",
        )

    # 7. Contextual Hospital Shorthand Normalization for Location (e.g., GW1 -> General Ward 1)
    norm_location = (
        extract_and_normalize_location(orig_transcript)
        or extract_and_normalize_location(english_translation)
        or analysis.get("suggested_location")
    )

    diagnostics = {
        "STT_SUCCESS": stt_success,
        "TRANSCRIPT_PRESENT": bool(orig_transcript),
        "TRANSLATION_SUCCESS": translation_success,
        "AI_ANALYSIS_SUCCESS": ai_analysis_success,
        "mode": "AUDIO_PIPELINE",
        "stt_provider": settings.AI_PROVIDER,
        "stt_model": getattr(stt_provider, "model_name", "default"),
    }

    # Log safe diagnostic VOICE_DEBUG
    logger.info(
        "VOICE_DEBUG: STT_SUCCESS=%s TRANSCRIPT_PRESENT=%s TRANSLATION_SUCCESS=%s AI_ANALYSIS_SUCCESS=%s",
        stt_success,
        bool(orig_transcript),
        translation_success,
        ai_analysis_success,
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
        suggested_location=norm_location,
        priority=analysis.get("priority", "Not Specified"),
        confidence_score=analysis.get("confidence_score", 1.0),
        field_provenance=analysis.get("field_provenance") or {
            "uhid": "STAFF_ENTERED",
            "patient_name": "STAFF_ENTERED",
            "consultant": "STAFF_ENTERED",
            "department": "STAFF_ENTERED",
            "location": "STAFF_ENTERED",
            "scheme": "STAFF_ENTERED",
            "original_transcript": "EXPLICITLY_SPOKEN",
            "complaint": "EXPLICITLY_SPOKEN",
            "complaint_summary": "EXPLICITLY_SPOKEN",
            "complaint_type": "AI_DERIVED",
            "suggested_department": "AI_DERIVED",
            "priority": "AI_DERIVED",
        },
        diagnostics=diagnostics,
    )


@router.post("/process-text", response_model=ProcessAudioResponse)
async def process_text(
    payload: ProcessTextRequest,
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Developer & QA Test Mode:
    Passes raw speech/text directly into the conversion pipeline:
    FAITHFUL ORIGINAL TRANSCRIPT -> LANGUAGE DETECTION -> HINDI/HINGLISH -> PROFESSIONAL ENGLISH -> STRUCTURED FEEDBACK -> SHORT SUMMARY
    Isolates AI/translation from the microphone/audio capture.
    """
    raw_text = (payload.text or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Empty text provided.")

    try:
        _, trans_provider, llm_provider = get_ai_providers()
    except Exception as e:
        logger.error(f"[AI Factory] Provider resolution failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI conversion service is not configured. Please contact administrator.",
        )

    # 1. Original transcript is preserved verbatim
    orig_transcript = raw_text

    # 2. Language detection & translation
    detected_lang = payload.language_hint or "Hinglish"
    try:
        english_translation = trans_provider.translate_to_english(
            orig_transcript, source_language=detected_lang
        )
        translation_success = bool(english_translation and english_translation.strip())
    except Exception as e:
        logger.error(f"[Translation] Text translation failed: {e}")
        raise HTTPException(status_code=502, detail=f"Translation service unavailable: {e}")

    # 3. Structured feedback extraction & short summary
    try:
        analysis = llm_provider.extract_structured_feedback(
            orig_transcript, english_translation
        )
        ai_analysis_success = bool(analysis and analysis.get("complaint"))
    except Exception as e:
        logger.error(f"[LLM] Structured extraction failed: {e}")
        raise HTTPException(status_code=502, detail=f"AI analysis unavailable: {e}")

    # 4. Contextual Location Normalization
    suggested_loc = (
        analysis.get("suggested_location")
        or extract_and_normalize_location(orig_transcript)
        or extract_and_normalize_location(english_translation)
    )

    diagnostics = {
        "STT_SUCCESS": True,  # Bypassed/text-mode test
        "TRANSCRIPT_PRESENT": True,
        "TRANSLATION_SUCCESS": translation_success,
        "AI_ANALYSIS_SUCCESS": ai_analysis_success,
        "mode": "TEXT_DEVELOPER_TEST_MODE",
    }
    logger.info(
        "VOICE_DEBUG: [TEXT_MODE] STT_SUCCESS=true TRANSCRIPT_PRESENT=true TRANSLATION_SUCCESS=%s AI_ANALYSIS_SUCCESS=%s",
        translation_success,
        ai_analysis_success,
    )

    return ProcessAudioResponse(
        success=True,
        audio_file_id=None,
        duration_seconds=0.0,
        quality_warning=None,
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
        suggested_location=suggested_loc,
        priority=analysis.get("priority", "Not Specified"),
        confidence_score=analysis.get("confidence_score", 0.95),
        field_provenance=analysis.get("field_provenance") or {
            "uhid": "STAFF_ENTERED",
            "patient_name": "STAFF_ENTERED",
            "consultant": "STAFF_ENTERED",
            "department": "STAFF_ENTERED",
            "location": "STAFF_ENTERED",
            "scheme": "STAFF_ENTERED",
            "original_transcript": "EXPLICITLY_SPOKEN",
            "complaint": "EXPLICITLY_SPOKEN",
            "complaint_summary": "EXPLICITLY_SPOKEN",
            "complaint_type": "AI_DERIVED",
            "suggested_department": "AI_DERIVED",
            "priority": "AI_DERIVED",
        },
        diagnostics=diagnostics,
    )



def process_feedback_background_job(
    feedback_db_id: str,
    client_uuid: str,
    audio_file_path: Optional[str] = None,
    manual_complaint: Optional[str] = None,
    engine_bind: Any = None,
):
    """
    Server-side Asynchronous Background Pipeline (Section 1, 5, 7, 8, 12):
    QUEUED -> TRANSCRIBING -> TRANSLATING -> ANALYZING -> VALIDATING -> COMPLETED / NEEDS_REVIEW
    1. Bounded retries with backoff (up to 3 attempts).
    2. Empty/silent/suspicious audio/STT never silently accepted -> sets NEEDS_REVIEW.
    3. Contextual hospital shorthand normalization (GW1 -> General Ward 1).
    4. Deterministic HOD mapping.
    5. Patient isolation guaranteed per client_uuid.
    """
    import os
    import time
    from sqlalchemy.orm import sessionmaker
    from ...db.database import SessionLocal
    from ...models import Feedback, FeedbackAIAnalysis, FeedbackAudio, FeedbackTranscript
    from ...services.ai.factory import get_ai_providers
    from ...services.hod_service import get_deterministic_hod
    from ...services.hospital_normalization import (
        extract_and_normalize_location,
        normalize_explicit_location,
    )

    if engine_bind is not None:
        SessionMaker = sessionmaker(autocommit=False, autoflush=False, bind=engine_bind)
        db = SessionMaker()
    else:
        db = SessionLocal()
    try:
        feedback = db.query(Feedback).filter(Feedback.id == feedback_db_id).first()
        if not feedback:
            logger.error("[Background Job] Feedback ID %s not found in DB.", feedback_db_id)
            return

        feedback.status = "PROCESSING"
        db.commit()

        stt_provider, trans_provider, llm_provider = get_ai_providers()
        orig_transcript = ""
        detected_lang = "Hinglish"

        # ----------------------------------------------------------------------
        # STEP 1: SPEECH-TO-TEXT / AUDIO VALIDATION (SECTION 8 & 12)
        # ----------------------------------------------------------------------
        if audio_file_path and os.path.exists(audio_file_path):
            audio_size = os.path.getsize(audio_file_path)
            if audio_size < 1500:
                logger.warning(
                    "[Background Job] Audio size under 1500 bytes (%d B). Setting NEEDS_REVIEW for client_uuid=%s",
                    audio_size,
                    client_uuid,
                )
                feedback.status = "NEEDS_REVIEW"
                feedback.processing_error = f"Audio quality too low or silent ({audio_size} bytes)."
                if manual_complaint and manual_complaint.strip():
                    feedback.complaint = manual_complaint.strip()
                db.commit()
                return

            feedback.status = "TRANSCRIBING"
            db.commit()

            transcription = None
            last_stt_err = None
            for attempt in range(1, 4):
                try:
                    transcription = stt_provider.transcribe(audio_file_path, mime_type="audio/webm")
                    if transcription and transcription.get("original_transcript"):
                        break
                except Exception as e:
                    last_stt_err = str(e)
                    time.sleep(1.0 * attempt)

            raw_transcript = (transcription.get("original_transcript", "") if transcription else "").strip()
            detected_lang = transcription.get("detected_language", "Mixed") if transcription else "Mixed"

            # Suspicious fillers check (e.g. 'uh', 'um', 'haan', 'ok')
            suspicious_fillers = {"uh", "um", "haan", "ha", "yes", "no", "ok", "hmm", "hmmm", "na", "achha"}
            words = [w.strip(".,!?") for w in raw_transcript.lower().split() if w.strip(".,!?")]
            is_suspicious = len(raw_transcript) < 4 or (len(words) <= 1 and words and words[0] in suspicious_fillers)

            if not raw_transcript or is_suspicious:
                logger.warning(
                    "[Background Job] Empty or suspicious STT transcript ('%s'). Setting NEEDS_REVIEW for client_uuid=%s",
                    raw_transcript,
                    client_uuid,
                )
                feedback.status = "NEEDS_REVIEW"
                feedback.processing_error = last_stt_err or f"Speech could not be understood or was too brief ('{raw_transcript}')."
                if manual_complaint and manual_complaint.strip():
                    feedback.complaint = manual_complaint.strip()

                trans_rec = db.query(FeedbackTranscript).filter(FeedbackTranscript.feedback_id == feedback.id).first()
                if not trans_rec:
                    trans_rec = FeedbackTranscript(
                        feedback_id=feedback.id,
                        original_language=detected_lang,
                        original_transcript=raw_transcript or "Unclear audio",
                        english_translation=manual_complaint or "Audio unclear — manual review required",
                    )
                    db.add(trans_rec)
                db.commit()
                return

            orig_transcript = raw_transcript
        elif manual_complaint and manual_complaint.strip():
            orig_transcript = manual_complaint.strip()
            detected_lang = "Hinglish"
        else:
            feedback.status = "NEEDS_REVIEW"
            feedback.processing_error = "No audio recording or manual complaint found."
            db.commit()
            return

        # ----------------------------------------------------------------------
        # STEP 2: TRANSLATION (HINDI/HINGLISH -> PROFESSIONAL ENGLISH)
        # ----------------------------------------------------------------------
        feedback.status = "TRANSLATING"
        db.commit()

        english_translation = None
        last_trans_err = None
        for attempt in range(1, 4):
            try:
                english_translation = trans_provider.translate_to_english(
                    orig_transcript, source_language=detected_lang
                )
                if english_translation and english_translation.strip():
                    break
            except Exception as e:
                last_trans_err = str(e)
                time.sleep(1.0 * attempt)

        if not english_translation:
            logger.warning("[Background Job] Translation failed. Setting NEEDS_REVIEW for client_uuid=%s", client_uuid)
            feedback.status = "NEEDS_REVIEW"
            feedback.processing_error = f"Translation service unavailable: {last_trans_err}"
            db.commit()
            return

        # ----------------------------------------------------------------------
        # STEP 3: STRUCTURED AI ANALYSIS & SHORT SUMMARY (SECTION 1 & 12)
        # ----------------------------------------------------------------------
        feedback.status = "ANALYZING"
        db.commit()

        analysis = None
        last_ai_err = None
        for attempt in range(1, 4):
            try:
                analysis = llm_provider.extract_structured_feedback(
                    orig_transcript, english_translation
                )
                if analysis and analysis.get("complaint"):
                    break
            except Exception as e:
                last_ai_err = str(e)
                time.sleep(1.0 * attempt)

        if not analysis:
            logger.warning("[Background Job] AI analysis failed. Setting NEEDS_REVIEW for client_uuid=%s", client_uuid)
            feedback.status = "NEEDS_REVIEW"
            feedback.processing_error = f"AI structuring unavailable: {last_ai_err}"
            db.commit()
            return

        # ----------------------------------------------------------------------
        # STEP 4: HOSPITAL SHORTHAND NORMALIZATION (SECTION 14)
        # ----------------------------------------------------------------------
        shorthand_loc = (
            extract_and_normalize_location(orig_transcript)
            or extract_and_normalize_location(english_translation)
            or analysis.get("suggested_location")
        )
        if not feedback.location and shorthand_loc:
            feedback.location = shorthand_loc
        elif feedback.location:
            feedback.location = normalize_explicit_location(feedback.location)

        # ----------------------------------------------------------------------
        # STEP 5: VALIDATION BEFORE COMPLETED (SECTION 12)
        # ----------------------------------------------------------------------
        feedback.status = "VALIDATING"
        db.commit()

        if not feedback.uhid or not feedback.patient_name or not feedback.department:
            feedback.status = "NEEDS_REVIEW"
            feedback.processing_error = "Required patient field missing."
            db.commit()
            return

        final_complaint = analysis.get("complaint") or english_translation or analysis.get("complaint_summary")
        feedback.complaint = final_complaint
        feedback.status = "COMPLETED"
        feedback.processing_error = None

        # Upsert Transcript record
        trans_rec = db.query(FeedbackTranscript).filter(FeedbackTranscript.feedback_id == feedback.id).first()
        if not trans_rec:
            trans_rec = FeedbackTranscript(
                feedback_id=feedback.id,
                original_language=detected_lang,
                original_transcript=orig_transcript,
                english_translation=english_translation,
            )
            db.add(trans_rec)
        else:
            trans_rec.original_language = detected_lang
            trans_rec.original_transcript = orig_transcript
            trans_rec.english_translation = english_translation

        # Upsert AI Analysis record
        ai_rec = db.query(FeedbackAIAnalysis).filter(FeedbackAIAnalysis.feedback_id == feedback.id).first()
        if not ai_rec:
            ai_rec = FeedbackAIAnalysis(
                feedback_id=feedback.id,
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
                provider_used=settings.AI_PROVIDER,
                confidence_score=analysis.get("confidence_score", 0.95),
            )
            db.add(ai_rec)
        else:
            ai_rec.complaint_type = analysis.get("complaint_type", "General Feedback")
            ai_rec.complaint_summary = analysis.get("complaint_summary", "Not Provided")
            ai_rec.detailed_feedback = analysis.get("detailed_feedback", "Not Provided")
            ai_rec.positive_feedback = analysis.get("positive_feedback", "Not Provided")
            ai_rec.negative_feedback = analysis.get("negative_feedback", "Not Provided")
            ai_rec.specific_complaint = analysis.get("specific_complaint", "Not Provided")
            ai_rec.suggested_action = analysis.get("suggested_action", "Not Provided")
            ai_rec.suggested_department = analysis.get("suggested_department")
            ai_rec.suggested_subcategory = analysis.get("suggested_subcategory")
            ai_rec.priority = analysis.get("priority", "Not Specified")

        db.commit()
        logger.info(
            "[Background Job] SUCCESS: Feedback %s (client_uuid=%s) transitioned to COMPLETED.",
            feedback.feedback_id,
            client_uuid,
        )

    except Exception as exc:
        logger.error("[Background Job] Fatal error processing %s: %s", client_uuid, exc, exc_info=True)
        try:
            feedback = db.query(Feedback).filter(Feedback.id == feedback_db_id).first()
            if feedback:
                feedback.status = "NEEDS_REVIEW"
                feedback.processing_error = str(exc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/async", response_model=AsyncFeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_async_feedback(
    background_tasks: BackgroundTasks,
    client_uuid: str = Form(...),
    uhid: str = Form(...),
    patient_name: str = Form(...),
    department: str = Form(...),
    location: Optional[str] = Form(None),
    consultant: Optional[str] = Form(None),
    scheme: Optional[str] = Form(None),
    attendant_name: Optional[str] = Form(None),
    manual_complaint: Optional[str] = Form(None),
    consent_status: Optional[str] = Form("CONSENT_OBTAINED"),
    audio: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Asynchronous 'Save & Next Patient' Endpoint (Section 2, 3, 5):
    1. Validates required patient fields (UHID, Name, Dept).
    2. Idempotent check by client_uuid.
    3. Saves audio to {client_uuid}.webm.
    4. Creates Feedback record with status 'QUEUED' and commits immediately.
    5. Dispatches server-side background processing job.
    6. Returns within milliseconds so staff can move to the next patient immediately.
    """
    clean_uhid = str(uhid).strip()
    clean_name = str(patient_name).strip()
    clean_dept = str(department).strip()
    clean_uuid = str(client_uuid).strip()

    if not clean_uhid:
        raise HTTPException(status_code=422, detail="UHID is required.")
    if not clean_name:
        raise HTTPException(status_code=422, detail="Patient Name is required.")
    if not clean_dept:
        raise HTTPException(status_code=422, detail="Department is required.")
    if not audio and not (manual_complaint and manual_complaint.strip()):
        raise HTTPException(status_code=422, detail="Either audio recording or manual complaint is required.")

    # Idempotency check: duplicate prevention
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
        return AsyncFeedbackOut(
            success=True,
            feedback_id=existing.feedback_id,
            client_uuid=existing.client_uuid,
            status=existing.status,
            message="Already saved — returning existing record.",
            feedback=format_feedback_out(existing),
        )

    # Save audio file if provided
    has_audio = False
    audio_path_str = None
    audio_bytes_len = 0
    if audio:
        audio_content = await audio.read()
        if audio_content and len(audio_content) > 0:
            has_audio = True
            audio_path_str, _, audio_bytes_len = save_audio_file(audio_content, clean_uuid, ext=".webm")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # Generate sequential unique feedback ID
    count_today = db.query(Feedback).count() + 1
    feedback_id = f"FB-{now.year}-{count_today:06d}"
    while db.scalar(select(Feedback).where(Feedback.feedback_id == feedback_id)):
        count_today += 1
        feedback_id = f"FB-{now.year}-{count_today:06d}"

    deterministic_hod = get_deterministic_hod(clean_dept, db=db)
    final_location = normalize_explicit_location(location) if location and location.strip() else None

    # Initial placeholder complaint
    initial_complaint = (
        manual_complaint.strip()
        if manual_complaint and manual_complaint.strip()
        else "Audio captured — processing in background..."
    )

    feedback = Feedback(
        feedback_id=feedback_id,
        client_uuid=clean_uuid,
        date_str=date_str,
        time_str=time_str,
        staff_id=current_user.id,
        staff_name=current_user.display_name,
        uhid=clean_uhid,
        patient_name=clean_name,
        location=final_location,
        consultant=consultant.strip() if consultant and consultant.strip() else None,
        scheme=scheme.strip() if scheme and scheme.strip() else None,
        attendant_name=attendant_name.strip() if attendant_name and attendant_name.strip() else None,
        department=clean_dept,
        hod_name=deterministic_hod,
        complaint=initial_complaint,
        consent_status=consent_status or "CONSENT_OBTAINED",
        consent_timestamp=now,
        status="QUEUED",
        is_deleted=False,
    )
    db.add(feedback)
    db.flush()

    if has_audio:
        audio_rec = FeedbackAudio(
            feedback_id=feedback.id,
            file_path=audio_path_str,
            file_size_bytes=audio_bytes_len,
            duration_seconds=max(0.5, round(audio_bytes_len / 6000.0, 1)),
            mime_type=audio.content_type or "audio/webm",
            retention_status="KEPT",
        )
        db.add(audio_rec)

    db.commit()
    db.refresh(feedback)

    log_audit(
        db=db,
        action="FEEDBACK_ASYNC_QUEUED",
        entity_type="Feedback",
        actor_username=current_user.username,
        actor_id=current_user.id,
        entity_id=feedback.feedback_id,
        details={"client_uuid": clean_uuid, "has_audio": has_audio},
    )

    # Dispatch background worker
    bind = db.get_bind()
    background_tasks.add_task(
        process_feedback_background_job,
        feedback.id,
        clean_uuid,
        audio_path_str,
        manual_complaint,
        engine_bind=bind,
    )

    return AsyncFeedbackOut(
        success=True,
        feedback_id=feedback.feedback_id,
        client_uuid=clean_uuid,
        status="QUEUED",
        message="Saved — Processing in Background",
        feedback=format_feedback_out(feedback),
    )


@router.get("/queue-status")
def get_queue_status(
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Returns background queue statistics for the logged-in staff member (Section 10).
    """
    active_statuses = ["QUEUED", "PROCESSING", "TRANSCRIBING", "TRANSLATING", "ANALYZING", "VALIDATING"]
    processing_count = (
        db.query(Feedback)
        .filter(
            Feedback.staff_id == current_user.id,
            Feedback.status.in_(active_statuses),
            Feedback.is_deleted == False,
        )
        .count()
    )
    completed_count = (
        db.query(Feedback)
        .filter(
            Feedback.staff_id == current_user.id,
            Feedback.status == "COMPLETED",
            Feedback.is_deleted == False,
        )
        .count()
    )
    needs_review_count = (
        db.query(Feedback)
        .filter(
            Feedback.staff_id == current_user.id,
            Feedback.status == "NEEDS_REVIEW",
            Feedback.is_deleted == False,
        )
        .count()
    )

    recent_jobs = (
        db.query(Feedback)
        .filter(
            Feedback.staff_id == current_user.id,
            Feedback.is_deleted == False,
        )
        .order_by(desc(Feedback.created_at))
        .limit(20)
        .all()
    )

    items = []
    for r in recent_jobs:
        items.append({
            "feedback_id": r.feedback_id,
            "client_uuid": r.client_uuid,
            "status": r.status,
            "processing_error": r.processing_error,
            "time_str": r.time_str,
            "created_at": r.created_at,
            "uhid_short": str(r.uhid)[:6] + ("..." if len(str(r.uhid)) > 6 else ""),
        })

    return {
        "processing_count": processing_count,
        "completed_count": completed_count,
        "needs_review_count": needs_review_count,
        "items": items,
    }


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackCreate,
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    """
    Final Submission Endpoint.
    1. Mandatory Validation: UHID, Patient Name, Department, Non-empty Complaint.
    2. Duplicate Prevention / Idempotency check.
    3. DETERMINISTIC HOD MAPPING: Backend determines HOD.
    4. Save normalized records (Feedback, Transcript, Audio, AI Analysis).
    5. Save audit log.
    """
    # 1. Validation check
    if not body.uhid or not str(body.uhid).strip():
        raise HTTPException(status_code=422, detail="UHID is required.")
    if not body.patient_name or not body.patient_name.strip():
        raise HTTPException(status_code=422, detail="Patient Name is required.")
    if not body.department or not body.department.strip():
        raise HTTPException(status_code=422, detail="Department is required.")
    if body.complaint is not None and not body.complaint.strip() and not (body.complaint_summary and body.complaint_summary.strip() and body.complaint_summary.strip().lower() != "not provided") and not (body.english_translation and body.english_translation.strip()):
        raise HTTPException(status_code=422, detail="Complaint text cannot be empty.")

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

    # 4. Create Feedback Core (with location normalization e.g. GW1 -> General Ward 1)
    final_location = (
        normalize_explicit_location(body.location)
        if body.location and body.location.strip()
        else (body.suggested_location.strip() if body.suggested_location else None)
    )

    feedback = Feedback(
        feedback_id=feedback_id,
        client_uuid=clean_uuid,
        date_str=date_str,
        time_str=time_str,
        staff_id=current_user.id,
        staff_name=current_user.display_name,
        uhid=str(body.uhid).strip(),  # Treat strictly as TEXT
        patient_name=body.patient_name.strip(),
        location=final_location,
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

    # 7. Create Audio Record if audio exists on disk (by audio_file_id or client_uuid)
    from ...services.audio_service import ensure_audio_dir

    audio_dir = ensure_audio_dir()
    audio_path_found = None
    if body.audio_file_id:
        cand_name = body.audio_file_id if body.audio_file_id.endswith(".webm") else f"{body.audio_file_id}.webm"
        target_by_id = audio_dir / cand_name
        if target_by_id.exists():
            audio_path_found = target_by_id
    if not audio_path_found:
        target_by_uuid = audio_dir / f"{clean_uuid}.webm"
        if target_by_uuid.exists():
            audio_path_found = target_by_uuid

    if audio_path_found or body.audio_file_id:
        file_path_str = str(audio_path_found) if audio_path_found else None
        file_size = audio_path_found.stat().st_size if audio_path_found else 0
        audio_rec = FeedbackAudio(
            feedback_id=feedback.id,
            file_path=file_path_str,
            file_size_bytes=file_size,
            duration_seconds=body.duration_seconds or max(0.5, round(file_size / 6000.0, 1)),
            mime_type="audio/webm",
            retention_status="KEPT",
        )
        db.add(audio_rec)

        if file_path_str:
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
