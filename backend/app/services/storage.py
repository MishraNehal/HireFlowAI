"""
Storage service — Supabase Storage integration for HireFlow.

All file operations go through this service:
  - upload_file()   : upload bytes to Supabase Storage → returns public/signed URL
  - download_file() : download file bytes from Supabase Storage
  - delete_file()   : delete a file from Supabase Storage
  - get_url()       : get a signed URL for private file access

Folder structure in bucket:
  resumes/{company_id}/{campaign_id}/{candidate_id}/resume.pdf
  jds/{company_id}/{campaign_id}/jd.pdf
  assessments/{company_id}/{campaign_id}/{candidate_id}/result.json
  recordings/{company_id}/{campaign_id}/{session_id}/video.webm
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _get_supabase_client():
    """Lazily create Supabase client to avoid import errors if not installed."""
    try:
        from supabase import create_client, Client
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY,
        )
        return client
    except ImportError:
        raise RuntimeError(
            "supabase package not installed. Run: pip install supabase"
        )


def upload_file(
    file_bytes: bytes,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload file bytes to Supabase Storage.

    Args:
        file_bytes   : raw file content as bytes
        key          : storage path e.g. "resumes/company_id/campaign_id/resume.pdf"
        content_type : MIME type e.g. "application/pdf", "image/jpeg"

    Returns:
        Signed URL (valid 1 hour) to access the uploaded file.

    Raises:
        Exception on upload failure.
    """
    client = _get_supabase_client()
    bucket = settings.SUPABASE_STORAGE_BUCKET

    try:
        # Upload file — upsert=True overwrites if key already exists
        client.storage.from_(bucket).upload(
            path=key,
            file=file_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "true",
            },
        )

        # Return signed URL valid for 1 hour (3600 seconds)
        signed = client.storage.from_(bucket).create_signed_url(
            path=key,
            expires_in=3600,
        )
        url = signed.get("signedURL") or signed.get("signed_url", "")

        logger.info(f"[Storage] Uploaded: {key} ({len(file_bytes)} bytes)")
        return url

    except Exception as e:
        logger.error(f"[Storage] Upload failed for {key}: {e}", exc_info=True)
        raise


def download_file(key: str) -> bytes:
    """
    Download file bytes from Supabase Storage.

    Args:
        key : storage path e.g. "resumes/company_id/campaign_id/resume.pdf"

    Returns:
        File content as bytes.

    Raises:
        Exception if file not found or download fails.
    """
    client = _get_supabase_client()
    bucket = settings.SUPABASE_STORAGE_BUCKET

    try:
        data = client.storage.from_(bucket).download(key)
        logger.info(f"[Storage] Downloaded: {key} ({len(data)} bytes)")
        return data

    except Exception as e:
        logger.error(f"[Storage] Download failed for {key}: {e}", exc_info=True)
        raise


def delete_file(key: str) -> bool:
    """
    Delete a file from Supabase Storage.

    Args:
        key : storage path e.g. "resumes/company_id/campaign_id/resume.pdf"

    Returns:
        True if deleted successfully, False otherwise.
    """
    client = _get_supabase_client()
    bucket = settings.SUPABASE_STORAGE_BUCKET

    try:
        client.storage.from_(bucket).remove([key])
        logger.info(f"[Storage] Deleted: {key}")
        return True

    except Exception as e:
        logger.error(f"[Storage] Delete failed for {key}: {e}", exc_info=True)
        return False


def get_url(key: str, expires_in: int = 3600) -> str:
    """
    Get a signed URL for private file access.

    Args:
        key        : storage path
        expires_in : URL validity in seconds (default 1 hour)

    Returns:
        Signed URL string.
    """
    client = _get_supabase_client()
    bucket = settings.SUPABASE_STORAGE_BUCKET

    try:
        signed = client.storage.from_(bucket).create_signed_url(
            path=key,
            expires_in=expires_in,
        )
        url = signed.get("signedURL") or signed.get("signed_url", "")
        logger.info(f"[Storage] Signed URL generated for: {key}")
        return url

    except Exception as e:
        logger.error(f"[Storage] get_url failed for {key}: {e}", exc_info=True)
        raise


# ── Helper: build storage keys consistently ──────────────────────────────────

def resume_key(company_id: str, campaign_id: str, candidate_id: str, filename: str = "resume.pdf") -> str:
    return f"resumes/{company_id}/{campaign_id}/{candidate_id}/{filename}"

def jd_key(company_id: str, campaign_id: str) -> str:
    return f"jds/{company_id}/{campaign_id}/jd.pdf"

def assessment_key(company_id: str, campaign_id: str, candidate_id: str) -> str:
    return f"assessments/{company_id}/{campaign_id}/{candidate_id}/result.json"

def recording_key(company_id: str, campaign_id: str, session_id: str) -> str:
    return f"recordings/{company_id}/{campaign_id}/{session_id}/video.webm"
