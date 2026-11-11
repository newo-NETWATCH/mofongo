"""Timestamps in the one shape the API stores and returns: 2026-10-21T14:05:09.123Z."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def iso_now() -> str:
    return to_iso(now())


def iso_in(seconds: int) -> str:
    return to_iso(now() + timedelta(seconds=seconds))


def parse_client_time(text: str) -> datetime:
    """Parse an ISO 8601 time that has Z or an offset. Raises ValueError otherwise."""
    try:
        moment = datetime.fromisoformat(text)
    except (ValueError, OverflowError) as exc:
        raise ValueError("not a time") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("no offset")
    try:
        return moment.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("out of range") from exc
