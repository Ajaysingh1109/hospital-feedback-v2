import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple
import httpx

from ..core.config import get_settings
from ..schemas import AudioQualityReport

logger = logging.getLogger(__name__)
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


def _get_supabase_storage_config() -> Optional[Tuple[str, str, str]]:
    """
    Returns (supabase_url, service_role_key, bucket_name) if private Supabase
    Storage is configured in environment variables, else None.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    # Service role key or storage key for authorized backend operations
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_KEY", "").strip()
    bucket_name = os.getenv("SUPABASE_STORAGE_BUCKET", "hospital-audio-private").strip()

    if supabase_url and supabase_key:
        return supabase_url, supabase_key, bucket_name
    return None


def upload_to_supabase_storage(file_bytes: bytes, file_name: str, content_type: str = "audio/webm") -> bool:
    """
    Uploads audio file to private Supabase Storage bucket for persistence
    across ephemeral cloud container restarts (e.g. Koyeb Free Tier).
    """
    cfg = _get_supabase_storage_config()
    if not cfg:
        return False

    supabase_url, supabase_key, bucket_name = cfg
    endpoint = f"{supabase_url}/storage/v1/object/{bucket_name}/{file_name}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(endpoint, content=file_bytes, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"[Private Audio Storage] Successfully backed up {file_name} to Supabase bucket '{bucket_name}'.")
                return True
            else:
                logger.warning(f"[Private Audio Storage] Upload failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.warning(f"[Private Audio Storage] Exception uploading {file_name} to Supabase Storage: {e}")

    return False


def fetch_from_supabase_storage(file_name: str) -> Optional[bytes]:
    """
    Fetches audio bytes from private Supabase Storage bucket if local file
    was unlinked or container was restarted on ephemeral cloud hosting.
    """
    cfg = _get_supabase_storage_config()
    if not cfg:
        return None

    supabase_url, supabase_key, bucket_name = cfg
    endpoint = f"{supabase_url}/storage/v1/object/authenticated/{bucket_name}/{file_name}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                logger.info(f"[Private Audio Storage] Restored {file_name} from Supabase bucket '{bucket_name}'.")
                return resp.content
    except Exception as e:
        logger.warning(f"[Private Audio Storage] Exception fetching {file_name} from Supabase: {e}")

    return None


def delete_from_supabase_storage(file_name: str) -> bool:
    """
    Permanently deletes audio file from private Supabase Storage bucket
    during automated 12-hour retention purge.
    """
    cfg = _get_supabase_storage_config()
    if not cfg:
        return False

    supabase_url, supabase_key, bucket_name = cfg
    endpoint = f"{supabase_url}/storage/v1/object/{bucket_name}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.request("DELETE", endpoint, json={"prefixes": [file_name]}, headers=headers)
            if resp.status_code in (200, 204):
                logger.info(f"[Private Audio Storage] Purged {file_name} from Supabase bucket '{bucket_name}'.")
                return True
    except Exception as e:
        logger.warning(f"[Private Audio Storage] Exception deleting {file_name} from Supabase: {e}")

    return False


def save_audio_file(file_bytes: bytes, client_uuid: str, ext: str = ".webm") -> Tuple[str, str, int]:
    """
    Saves audio file into private storage directory.
    If private Supabase Storage is configured, also backs up to bucket
    to survive ephemeral container restarts.
    Returns (target_path, sha256_hash, file_size)
    """
    audio_dir = ensure_audio_dir()
    file_name = f"{client_uuid}{ext}"
    target_path = audio_dir / file_name

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    sha256_hash = compute_sha256(file_bytes)

    # Optional private cloud backup for ephemeral instances
    upload_to_supabase_storage(file_bytes, file_name, content_type="audio/webm")

    return str(target_path), sha256_hash, len(file_bytes)


def delete_audio_file_if_policy(file_path: Optional[str]) -> bool:
    """
    Enforces hospital privacy & retention policy:
    If AUDIO_RETENTION_POLICY == 'delete_after_processing', deletes file securely.
    """
    if settings.AUDIO_RETENTION_POLICY == "delete_after_processing" and file_path:
        try:
            p = Path(file_path)
            if p.exists():
                p.unlink()
            # Also purge from Supabase storage if backed up
            delete_from_supabase_storage(p.name)
            return True
        except Exception:
            pass
    return False
