"""Settings read from the Lambda environment (set by infra/modules/matcher_lambda).

Nothing here runs at import time, so the modules import without any environment. A missing
or malformed variable raises RuntimeError on first use. The handler reports that record as
failed, so it is retried after the deploy is fixed (only the error type is logged).

Environment contract (the Terraform module must set all of these):

    ITEMS_TABLE              mofongo-dev-items
    REPORTS_TABLE            mofongo-dev-reports
    MATCHES_TABLE            mofongo-dev-matches
    IDX_LISTED_BY_CATEGORY   ListedByCategory   (Items)
    IDX_OPEN_BY_CATEGORY     OpenByCategory     (Reports)
    ALERTS_TOPIC_ARN         the SNS topic the matcher publishes to
    SITE_URL                 the site origin used in the email link, for example https://example.cloudfront.net
    MATCH_THRESHOLD          optional, whole number 0 to 100, default 60 (section 6.3)
    LOG_LEVEL                optional, default INFO

AWS_REGION is set by Lambda itself. The project only uses us-east-2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# Section 6.4 and 6.5: follow the pages, newest first, and stop at 500 candidates.
MAX_CANDIDATES = 500
# One Query page. The cap above is applied across pages.
QUERY_PAGE_SIZE = 100
DEFAULT_THRESHOLD = 60


@dataclass(frozen=True)
class Settings:
    region: str
    items_table: str
    reports_table: str
    matches_table: str
    idx_listed_by_category: str
    idx_open_by_category: str
    alerts_topic_arn: str
    site_url: str
    threshold: int


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


def _threshold() -> int:
    raw = os.environ.get("MATCH_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("MATCH_THRESHOLD must be a whole number") from exc
    if not 0 <= value <= 100:
        raise RuntimeError("MATCH_THRESHOLD must be between 0 and 100")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        region=os.environ.get("AWS_REGION", "us-east-2"),
        items_table=_required("ITEMS_TABLE"),
        reports_table=_required("REPORTS_TABLE"),
        matches_table=_required("MATCHES_TABLE"),
        idx_listed_by_category=_required("IDX_LISTED_BY_CATEGORY"),
        idx_open_by_category=_required("IDX_OPEN_BY_CATEGORY"),
        alerts_topic_arn=_required("ALERTS_TOPIC_ARN"),
        site_url=_required("SITE_URL").rstrip("/"),
        threshold=_threshold(),
    )
