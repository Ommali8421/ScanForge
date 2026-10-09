"""
Upload Service
Handles streaming upload to disk, size cap enforcement, and filename sanitization.
"""

import re
from pathlib import Path
from typing import Tuple
from fastapi import UploadFile, HTTPException
from app.config import settings
from app.services.storage import storage_service
from app.utils.ffprobe import probe_video

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".zip", ".r3d"}


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent directory traversal and invalid characters."""
    base = Path(filename).name
    # Strip any directory path separators and special characters
    clean = re.sub(r"[^\w\.\-]", "_", base)
    if not clean or clean.startswith("."):
        clean = f"upload_{clean}"
    return clean


async def save_uploaded_file(job_id: str, upload_file: UploadFile) -> Tuple[Path, str, dict]:
    """
    Stream upload file directly to disk, enforcing size limits and allowed extensions.
    Returns (saved_file_path, sanitized_filename, probe_info).
    """
    original_name = upload_file.filename or "upload.mp4"
    sanitized = sanitize_filename(original_name)
    ext = Path(sanitized).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    upload_dir = storage_service.get_job_upload_dir(job_id)
    dest_path = upload_dir / sanitized

    max_bytes = settings.SCANFORGE_MAX_UPLOAD_MB * 1024 * 1024
    total_written = 0

    try:
        with open(dest_path, "wb") as f:
            while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
                total_written += len(chunk)
                if total_written > max_bytes:
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed upload size of {settings.SCANFORGE_MAX_UPLOAD_MB} MB"
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    # Probe metadata if video
    probe_info = {}
    if ext in {".mp4", ".mov", ".m4v", ".avi"}:
        probe_info = probe_video(dest_path)
        if probe_info.get("duration", 0) > settings.SCANFORGE_MAX_VIDEO_SECONDS:
            dest_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Video duration ({probe_info['duration']:.1f}s) exceeds maximum allowed limit of {settings.SCANFORGE_MAX_VIDEO_SECONDS}s"
            )

    return dest_path, sanitized, probe_info
