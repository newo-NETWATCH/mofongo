"""Timestamps in the one shape the tables store: 2026-10-21T14:05:09.123Z (data-model.md section 3)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def iso_now() -> str:
    moment = datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
