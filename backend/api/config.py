"""Settings read from the Lambda environment (set by infra/modules/api_lambda).

Nothing here runs at import time, so the modules import without any environment.
A missing variable raises RuntimeError on first use, which the handler turns into a
generic 500 (the variable name goes to the log only).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# Fixed by docs/data-model.md and api/openapi.yaml. They are the API contract, not settings.
MAX_BODY_BYTES = 32768
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_MATCHES = 100
UPLOAD_TTL_SECONDS = 300
LISTED_PARTITION = "LISTED"


@dataclass(frozen=True)
class Settings:
    region: str
    items_table: str
    reports_table: str
    matches_table: str
    users_table: str
    idx_listed_by_date: str
    idx_listed_by_category: str
    idx_by_owner: str
    photos_bucket: str
    alerts_topic_arn: str
    user_pool_id: str
    app_client_id: str
    schema_dir: str
    presign_ttl_seconds: int
    photo_max_bytes: int
    cors_origin: str


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        # AWS_REGION is set by Lambda itself. The project only uses us-east-2.
        region=os.environ.get("AWS_REGION", "us-east-2"),
        items_table=_required("ITEMS_TABLE"),
        reports_table=_required("REPORTS_TABLE"),
        matches_table=_required("MATCHES_TABLE"),
        users_table=_required("USERS_TABLE"),
        idx_listed_by_date=_required("IDX_LISTED_BY_DATE"),
        idx_listed_by_category=_required("IDX_LISTED_BY_CATEGORY"),
        idx_by_owner=_required("IDX_BY_OWNER"),
        photos_bucket=_required("PHOTOS_BUCKET"),
        alerts_topic_arn=_required("ALERTS_TOPIC_ARN"),
        user_pool_id=_required("USER_POOL_ID"),
        app_client_id=_required("APP_CLIENT_ID"),
        schema_dir=os.environ.get("SCHEMA_DIR", "/var/task/schemas"),
        presign_ttl_seconds=int(os.environ.get("PRESIGN_TTL_SECONDS", "900")),
        photo_max_bytes=int(os.environ.get("PHOTO_MAX_BYTES", "10485760")),
        cors_origin=_required("CORS_ORIGIN"),
    )
