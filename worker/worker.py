"""The photo tagger's main loop (docs/decisions/0004-clip-on-ec2-with-sqs-pull.md).

    long-poll SQS -> for each S3 event: read the photo -> CLIP -> conditional UpdateItem -> delete message

Delete or keep the SQS message:
  - tagged                          delete
  - item gone, already tagged,
    RETURNED, or not a photo event  delete (nothing to do, and a retry would change nothing)
  - photo cannot be read            write FAILED + tagError, then delete (retrying cannot help)
  - anything transient (S3, DynamoDB, SQS, the model) KEEP. The message becomes visible again after
    the visibility timeout, and after maxReceiveCount tries the redrive policy moves it to the
    dead-letter queue, which alarms.
  - a body that is not JSON         KEEP, so it reaches the dead-letter queue where someone sees it

Tagging is safe to repeat: S3 delivers at least once, and the write only changes a LISTED item
whose tagStatus is still PENDING (store.py).

Run: python worker.py   (systemd runs it; see deploy/mofongo-worker.service)
"""

from __future__ import annotations

import json
import logging
import re
import signal
import sys
import threading
import time
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import config
import store
import tagger

log = logging.getLogger("worker")

# photos/{itemId}.jpg with a UUID item id (data-model.md section 4.1). fullmatch, so a
# trailing newline or a sub-folder never passes.
PHOTO_KEY = re.compile(r"photos/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jpg")

# Keep this share of the visibility timeout for the work; stop taking new messages past it.
BATCH_BUDGET = 0.8
MAX_BACKOFF_SECONDS = 60

_stop = threading.Event()


def _request_stop(signum, _frame) -> None:
    log.info("signal %s: finishing the current message, then stopping", signum)
    _stop.set()


# ---------------------------------------------------------------- message parsing


def photo_records(body: str, expected_bucket: str) -> list[tuple[str, str]]:
    """Return [(item_id, key)] for the photo-created records in an S3 event message body.

    Returns [] for anything that needs no tagging (the S3 test event, other event types, other
    keys, another bucket). Raises ValueError when the body is not JSON: the caller keeps it.
    """
    data = json.loads(body)  # ValueError (JSONDecodeError) on garbage
    if not isinstance(data, dict):
        raise ValueError("message body is not a JSON object")
    records = data.get("Records")
    if not isinstance(records, list):  # the s3:TestEvent has no Records
        return []
    found: list[tuple[str, str]] = []
    for record in records:
        try:
            if not str(record["eventName"]).startswith("ObjectCreated:"):
                continue
            bucket = record["s3"]["bucket"]["name"]
            key = unquote_plus(record["s3"]["object"]["key"])  # S3 URL-encodes keys in events
        except (KeyError, TypeError):
            continue
        match = PHOTO_KEY.fullmatch(key)
        if bucket != expected_bucket or not match:
            log.warning("ignoring an event for bucket=%s key=%r", bucket, key)
            continue
        found.append((match.group(1).lower(), key))
    return found


# ---------------------------------------------------------------- reading the photo


def read_photo(s3, bucket: str, key: str, max_bytes: int) -> bytes:
    """Download the photo, never more than max_bytes. Raises PhotoError when it can never work."""
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise tagger.PhotoError("photo not found") from exc
        raise  # throttling, 5xx, access problems: transient from the worker's point of view
    if resp.get("ContentLength", 0) > max_bytes:
        resp["Body"].close()
        raise tagger.PhotoError("photo is too large")
    body = resp["Body"]
    try:
        data = body.read(max_bytes + 1)
    finally:
        body.close()
    if len(data) > max_bytes:
        raise tagger.PhotoError("photo is too large")
    if not data:
        raise tagger.PhotoError("photo is empty")
    return data


# ---------------------------------------------------------------- one photo


def process_photo(cfg: config.Settings, s3, items: store.ItemStore, model: tagger.Tagger, item_id: str, key: str) -> str:
    """Tag one photo. Returns what happened: tagged, failed or skipped. Raises on a transient error."""
    if not items.needs_tags(item_id, key):
        log.info("item %s: nothing to tag (gone, already tagged or failed, or returned)", item_id)
        return "skipped"
    try:
        data = read_photo(s3, cfg.photos_bucket, key, cfg.max_photo_bytes)
        started = time.monotonic()
        tags = model.tag(tagger.load_image(data, cfg.max_image_pixels))
    except tagger.PhotoError as exc:
        written = items.mark_failed(item_id, key, exc.reason)
        log.warning("item %s: photo cannot be tagged (%s); marked FAILED=%s", item_id, exc.reason, written)
        return "failed"
    written = items.mark_tagged(item_id, key, tags)
    log.info(
        "item %s: tagged in %.2fs, saved=%s, top category=%s, top color=%s",
        item_id,
        time.monotonic() - started,
        written,
        tags["categories"][0]["value"],
        tags["colors"][0]["value"],
    )
    return "tagged" if written else "skipped"


def handle_message(cfg, s3, sqs, items, model, message: dict) -> None:
    """Process one SQS message. Deletes it only when every record finished without a transient error."""
    try:
        records = photo_records(message["Body"], cfg.photos_bucket)
    except ValueError:
        log.error("message %s is not an S3 event; keeping it for the dead-letter queue", message.get("MessageId"))
        return
    for item_id, key in records:
        process_photo(cfg, s3, items, model, item_id, key)  # a transient error propagates: keep the message
    sqs.delete_message(QueueUrl=cfg.queue_url, ReceiptHandle=message["ReceiptHandle"])


# ---------------------------------------------------------------- the loop


def run(cfg: config.Settings, model: tagger.Tagger, s3=None, sqs=None, items=None) -> None:
    # The SQS read timeout must be longer than the long poll, or every empty poll would time out.
    sqs_config = Config(retries={"mode": "standard", "total_max_attempts": 4}, connect_timeout=5, read_timeout=cfg.wait_seconds + 10)
    s3_config = Config(retries={"mode": "standard", "total_max_attempts": 4}, connect_timeout=5, read_timeout=30)
    sqs = sqs or boto3.client("sqs", region_name=cfg.region, config=sqs_config)
    s3 = s3 or boto3.client("s3", region_name=cfg.region, config=s3_config)
    items = items or store.ItemStore(cfg.items_table, cfg.region)

    failures = 0
    log.info("polling %s", cfg.queue_url)
    while not _stop.is_set():
        try:
            resp = sqs.receive_message(
                QueueUrl=cfg.queue_url,
                MaxNumberOfMessages=cfg.max_messages,
                WaitTimeSeconds=cfg.wait_seconds,
                VisibilityTimeout=cfg.visibility_timeout,
            )
            failures = 0
        except Exception:  # noqa: BLE001 - keep polling through any network or credentials hiccup
            failures += 1
            delay = min(MAX_BACKOFF_SECONDS, 2**failures)
            log.exception("receive failed (%d in a row); retrying in %ds", failures, delay)
            _stop.wait(delay)
            continue

        batch_started = time.monotonic()
        for message in resp.get("Messages", []):
            if _stop.is_set() or time.monotonic() - batch_started > BATCH_BUDGET * cfg.visibility_timeout:
                # Left alone: it shows up again when its visibility timeout ends.
                log.info("not starting message %s (stopping or out of batch time)", message.get("MessageId"))
                continue
            try:
                handle_message(cfg, s3, sqs, items, model, message)
            except Exception:  # noqa: BLE001 - the message stays; the redrive policy counts the try
                log.exception("message %s failed; keeping it", message.get("MessageId"))
    log.info("stopped")


def main() -> int:
    try:
        cfg = config.load_settings()
    except RuntimeError as exc:
        print(f"worker: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    # The model loads ONCE, here, before the first poll. A failure exits non-zero; systemd restarts it.
    model = tagger.Tagger(cfg.clip_model, cfg.clip_pretrained, cfg.clip_weights_path, cfg.torch_threads)
    run(cfg, model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
