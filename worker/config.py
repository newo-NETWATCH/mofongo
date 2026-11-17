"""Settings read from the environment (written to /etc/mofongo/worker.env by the instance bootstrap).

Nothing here runs at import time. load_settings() raises RuntimeError on a missing or
malformed variable, so the service fails at start and systemd shows the reason.

Environment contract (infra/modules/tagger provides the first three):

    QUEUE_URL           URL of the photo queue (the main queue, not the DLQ). PHOTO_QUEUE_URL also works.
    PHOTOS_BUCKET       the photos bucket name. Events naming another bucket are rejected.
    ITEMS_TABLE         mofongo-dev-items
    AWS_REGION          optional (REGION also works), default us-east-2 (the project only uses us-east-2)

    SQS_WAIT_SECONDS    optional, long-poll time, 1 to 20, default 20
    SQS_MAX_MESSAGES    optional, 1 to 10, default 5
    VISIBILITY_TIMEOUT  optional, seconds a received message stays hidden, default 300. It must
                        be longer than SQS_MAX_MESSAGES tagging runs. The worker passes it on
                        every receive and stops a batch at 80% of it.
    MAX_PHOTO_BYTES     optional, default 10485760 (the same cap as the upload form)
    MAX_IMAGE_PIXELS    optional, default 50000000
    CLIP_MODEL          optional, default ViT-B-32
    CLIP_PRETRAINED     optional, default laion2b_s34b_b79k
    CLIP_WEIGHTS_PATH   optional, a local checkpoint file used instead of the Hugging Face
                        download (see README, "Pinning the weights")
    TORCH_THREADS       optional, default is the number of vCPUs
    LOG_LEVEL           optional, default INFO

HF_HOME (where the model is cached) is read by the Hugging Face library, not here. The
systemd unit sets it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_REGION = "us-east-2"


@dataclass(frozen=True)
class Settings:
    region: str
    queue_url: str
    photos_bucket: str
    items_table: str
    wait_seconds: int
    max_messages: int
    visibility_timeout: int
    max_photo_bytes: int
    max_image_pixels: int
    clip_model: str
    clip_pretrained: str
    clip_weights_path: str | None
    torch_threads: int | None
    log_level: str


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable {name}")
    return value


def _first(*names: str) -> str:
    """The first of several accepted names that is set (the instance setup uses QUEUE_URL)."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing environment variable {names[0]}")


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number") from exc
    if not low <= value <= high:
        raise RuntimeError(f"{name} must be between {low} and {high}")
    return value


def load_settings() -> Settings:
    threads_raw = os.environ.get("TORCH_THREADS", "").strip()  # empty means "use every vCPU"
    weights = os.environ.get("CLIP_WEIGHTS_PATH", "").strip()
    return Settings(
        region=os.environ.get("AWS_REGION", "").strip() or os.environ.get("REGION", "").strip() or DEFAULT_REGION,
        queue_url=_first("QUEUE_URL", "PHOTO_QUEUE_URL"),
        photos_bucket=_required("PHOTOS_BUCKET"),
        items_table=_required("ITEMS_TABLE"),
        wait_seconds=_int("SQS_WAIT_SECONDS", 20, 1, 20),
        max_messages=_int("SQS_MAX_MESSAGES", 5, 1, 10),
        visibility_timeout=_int("VISIBILITY_TIMEOUT", 300, 30, 43200),
        max_photo_bytes=_int("MAX_PHOTO_BYTES", 10 * 1024 * 1024, 1, 100 * 1024 * 1024),
        max_image_pixels=_int("MAX_IMAGE_PIXELS", 50_000_000, 1, 500_000_000),
        clip_model=os.environ.get("CLIP_MODEL", "").strip() or "ViT-B-32",
        clip_pretrained=os.environ.get("CLIP_PRETRAINED", "").strip() or "laion2b_s34b_b79k",
        clip_weights_path=weights or None,
        torch_threads=_int("TORCH_THREADS", 1, 1, 256) if threads_raw else None,
        log_level=os.environ.get("LOG_LEVEL", "").strip().upper() or "INFO",
    )
