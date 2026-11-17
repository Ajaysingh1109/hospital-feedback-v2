import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.security import decode_access_token
from ...db.database import get_db
from ...models import Feedback, FeedbackAudio, RoleEnum, User

router = APIRouter(prefix="/audio", tags=["Audio Streaming"])
security = HTTPBearer(auto_error=False)


def get_audio_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> User:
    raw_token = credentials.credentials if credentials else token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(raw_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact hospital administrator.",
        )

    return user


@router.get("/{audio_id}")
def stream_audio(
    audio_id: str,
    current_user: User = Depends(get_audio_user),
    db: Session = Depends(get_db),
):
    """
    Protected audio access (Temporary Ground Truth Review):
    - Audio is stored privately in server persistent storage.
    - Master / Admin can listen to any recording for investigation / verification.
    - Staff can only access recordings they personally recorded.
    - Strictly 12-Hour Retention: Audio expires 12 hours after created_at.
      If expired or physical file is unlinked, returns 404.
    """
    clean_id = audio_id.strip()
    id_without_ext = clean_id[:-5] if clean_id.endswith(".webm") else clean_id

    audio_rec = db.scalar(
        select(FeedbackAudio)
        .outerjoin(Feedback, FeedbackAudio.feedback_id == Feedback.id)
        .where(
            (FeedbackAudio.id == clean_id)
            | (FeedbackAudio.id == id_without_ext)
            | (FeedbackAudio.feedback_id == clean_id)
            | (FeedbackAudio.feedback_id == id_without_ext)
            | (Feedback.feedback_id == clean_id)
            | (Feedback.client_uuid == clean_id)
            | (Feedback.client_uuid == id_without_ext)
            | (FeedbackAudio.file_path.ilike(f"%{clean_id}%"))
            | (FeedbackAudio.file_path.ilike(f"%{id_without_ext}%"))
        )
    )

    if not audio_rec or not audio_rec.file_path:
        raise HTTPException(
            status_code=404,
            detail="Audio file not found or has been purged per hospital retention policy.",
        )

    # Permission check: Admin or Master can listen to all; staff can only listen to own
    fb = audio_rec.feedback
    if current_user.role not in (RoleEnum.ADMIN, RoleEnum.MASTER) and fb and fb.staff_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: You do not have permission to listen to this recording.",
        )

    # Exact 12-Hour Expiration Check (created_at + 12 hours)
    if fb and fb.created_at:
        now_utc = datetime.now(timezone.utc)
        created_utc = fb.created_at if fb.created_at.tzinfo else fb.created_at.replace(tzinfo=timezone.utc)
        if now_utc > (created_utc + timedelta(hours=12)):
            raise HTTPException(
                status_code=404,
                detail="Audio recording has expired and been permanently deleted per 12-hour hospital retention policy.",
            )

    file_path = Path(audio_rec.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Audio recording file has been purged per hospital data retention policy.",
        )

    return FileResponse(
        path=str(file_path),
        media_type=audio_rec.mime_type or "audio/webm",
        filename=file_path.name,
    )

