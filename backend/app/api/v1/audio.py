import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.database import get_db
from ...models import Feedback, FeedbackAudio, RoleEnum, User
from ..deps import get_current_user

router = APIRouter(prefix="/audio", tags=["Audio Streaming"])


@router.get("/{audio_id}")
def stream_audio(
    audio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Protected audio access:
    - Audio is stored privately.
    - Admin can listen to any recording.
    - Staff can only access audio for their own recorded feedback.
    """
    audio_rec = db.scalar(
        select(FeedbackAudio).where(
            (FeedbackAudio.id == audio_id) | (FeedbackAudio.file_path.ilike(f"%{audio_id}%"))
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
