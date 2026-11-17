"""Matching Lambda, started by DynamoDB Streams (data-model.md section 6).

Handler for the Terraform module:  app.handler   (file app.py at the top of the zip)

Two event source mappings (Items stream, Reports stream) start this one function. Lambda has
already applied the filters of section 6.2, but the code checks the same conditions again, so a
replayed or unfiltered record can never start the wrong direction.

Failure handling (ReportBatchItemFailures): the first record that cannot be finished is returned
in batchItemFailures and processing stops. Lambda retries from that record on, which is safe
because the conditional write into Matches makes every pair idempotent (section 6.7).
A record that is simply not for us, or is malformed, is skipped and is NOT a failure: retrying
it can never help and would block its shard.
"""

from __future__ import annotations

import logging
import os
import re

from boto3.dynamodb.types import TypeDeserializer

from matching import process_new_report, process_tagged_item
from settings import get_settings
from vocab import ITEM_STATUS_LISTED, REPORT_STATUS_OPEN, TAG_PENDING, TAG_TAGGED

log = logging.getLogger("matcher")

_deserializer = TypeDeserializer()
_TABLE_FROM_ARN = re.compile(r":table/([^/]+)/stream/")


def _plain(image: dict | None) -> dict:
    """DynamoDB JSON (for example {"N": "81"}) to plain Python. Numbers become Decimal."""
    return {name: _deserializer.deserialize(value) for name, value in (image or {}).items()}


def _table_name(record: dict) -> str | None:
    match = _TABLE_FROM_ARN.search(record.get("eventSourceARN") or "")
    return match.group(1) if match else None


def _handle_record(record: dict) -> str:
    """Process one stream record. Returns a short label for the log. Raises when it must be retried."""
    settings = get_settings()
    table = _table_name(record)
    event_name = record.get("eventName")
    stream = record.get("dynamodb") or {}

    if table == settings.items_table:
        new, old = _plain(stream.get("NewImage")), _plain(stream.get("OldImage"))
        # Direction A (6.4): a LISTED item that just went PENDING -> TAGGED.
        if (
            event_name == "MODIFY"
            and new.get("status") == ITEM_STATUS_LISTED
            and new.get("tagStatus") == TAG_TAGGED
            and old.get("tagStatus") == TAG_PENDING
        ):
            process_tagged_item(new)
            return "item-tagged"
        return "ignored-item"

    if table == settings.reports_table:
        new = _plain(stream.get("NewImage"))
        # Direction B (6.5): a report that was just filed.
        if event_name == "INSERT" and new.get("status") == REPORT_STATUS_OPEN:
            process_new_report(new)
            return "report-filed"
        return "ignored-report"

    log.warning("record from an unknown stream skipped")
    return "ignored-unknown-stream"


def handler(event, context=None):
    logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    failures: list[dict] = []
    for record in event.get("Records", []):
        sequence = (record.get("dynamodb") or {}).get("SequenceNumber")
        try:
            label = _handle_record(record)
            log.info("record %s seq=%s", label, sequence)
        except Exception as exc:  # noqa: BLE001 - any error means: report this record as failed
            # The error type is logged, never the record: it holds the owner's report text.
            log.error("record failed seq=%s error=%s", sequence, type(exc).__name__)
            if sequence:
                failures.append({"itemIdentifier": sequence})
                break  # Lambda retries from here; later records come back with it
            raise  # no sequence number to report: fail the whole batch
    return {"batchItemFailures": failures}
