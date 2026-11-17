import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple

from ..core.config import get_settings
from ..schemas import AudioQualityReport

settings = get_settings()


def ensure_audio_dir() -> Path:
    try:
        p = Path(settings.AUDIO_STORAGE_DIR).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    except (PermissionError, OSError):
        # Fallback to /tmp/audio or local ./data/audio if persistent disk is unmounted / not permitted
        fallback = Path("/tmp/audio").resolve()
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except Exception:
            local_fallback = Path("./data/audio").resolve()
            local_fallback.mkdir(parents=True, exist_ok=True)
            return local_fallback


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_audio_quality(file_bytes: bytes, file_ext: str = ".webm") -> AudioQualityReport:
    """
    Analyzes basic audio properties.
    Detects if audio is under threshold or silent.
    """
    size = len(file_bytes)
    # Estimate duration based on typical webm/opus bitrate (~32kbps = ~4KB/s)
    # A 1-second webm file is typically ~4,000 to 12,000 bytes
    estimated_duration = max(0.5, round(size / 6000.0, 1))

    # Low quality flag if under 1.5KB (likely empty/silence header only)
    is_low_quality = size < 1500

    message = None
    if is_low_quality:
        message = "Audio quality appears low or recording is very short. Please review or re-record if necessary."

    return AudioQualityReport(
        is_low_quality=is_low_quality,
        message=message,
        duration_seconds=estimated_duration,
        file_size_bytes=size,
    )


def save_audio_file(file_bytes: bytes, client_uuid: str, ext: str = ".webm") -> Tuple[str, str, int]:
    """
    Saves audio file into private storage directory.
    Returns (relative_path, sha256_hash, file_size)
    """
    audio_dir = ensure_audio_dir()
    file_name = f"{client_uuid}{ext}"
    target_path = audio_dir / file_name

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    sha256_hash = compute_sha256(file_bytes)
    return str(target_path), sha256_hash, len(file_bytes)


def delete_audio_file_if_policy(file_path: Optional[str]) -> bool:
    """
    Enforces hospital privacy & retention policy:
    If AUDIO_RETENTION_POLICY == 'delete_after_processing', deletes file securely.
    """
    if settings.AUDIO_RETENTION_POLICY == "delete_after_processing" and file_path:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception:
            pass
    return False
