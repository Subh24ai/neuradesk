"""GCS image upload utility.

Uploads base64-encoded screenshots to Google Cloud Storage.
Returns None when GCS_BUCKET is not configured or the upload fails,
so ticket creation is never blocked by storage errors.
"""

import base64
import os
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

_BUCKET_NAME: str = os.getenv("GCS_BUCKET", "")


def upload_image_b64(ticket_id: str, image_b64: str) -> Optional[str]:
    """Upload base64-encoded image to GCS; return public URL or None on failure."""
    if not _BUCKET_NAME:
        return None
    try:
        from google.cloud import storage as gcs  # type: ignore[import]

        client = gcs.Client()
        bucket = client.bucket(_BUCKET_NAME)
        blob_name = f"tickets/{ticket_id}/screenshot.png"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(base64.b64decode(image_b64), content_type="image/png")
        url = f"https://storage.googleapis.com/{_BUCKET_NAME}/{blob_name}"
        log.info("gcs.upload_ok", ticket_id=ticket_id, url=url)
        return url
    except Exception:
        log.warning("gcs.upload_failed", ticket_id=ticket_id)
        return None
