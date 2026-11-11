"""Presigned S3 links for item photos.

The Lambda role holds s3:GetObject and s3:PutObject on photos/* only. A presigned URL is
as strong as the role that signed it and is checked when it is used, so those two grants
are what make these links work. Nothing here checks that the photo exists.
"""

from __future__ import annotations

from aws import s3_client
from config import UPLOAD_TTL_SECONDS, get_settings
from timeutil import iso_in


def photo_key(item_id: str) -> str:
    # Derived from the item ID (a validated UUID), never read back from a stored value.
    return f"photos/{item_id}.jpg"


def photo_link(item_id: str) -> dict:
    """A 15-minute GET link: {url, expiresAt}. Made fresh on every request, never stored."""
    settings = get_settings()
    url = s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.photos_bucket, "Key": photo_key(item_id)},
        ExpiresIn=settings.presign_ttl_seconds,
    )
    return {"url": url, "expiresAt": iso_in(settings.presign_ttl_seconds)}


def upload_form(item_id: str) -> dict:
    """A 5-minute presigned POST for exactly photos/{itemId}.jpg, image/jpeg, 1 byte to the cap.

    The result holds a credential for one object. It goes to the caller and nowhere else:
    do not log it.
    """
    settings = get_settings()
    key = photo_key(item_id)
    post = s3_client().generate_presigned_post(
        Bucket=settings.photos_bucket,
        Key=key,
        Fields={"Content-Type": "image/jpeg"},
        Conditions=[
            {"Content-Type": "image/jpeg"},
            ["content-length-range", 1, settings.photo_max_bytes],
        ],
        ExpiresIn=UPLOAD_TTL_SECONDS,
    )
    return {"url": post["url"], "fields": post["fields"], "expiresAt": iso_in(UPLOAD_TTL_SECONDS)}
