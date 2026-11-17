"""The two matching directions (data-model.md sections 6.4 and 6.5).

Direction A: an item just got its tags while LISTED -> score it against the open reports of its
category (AP17). Direction B: a report was just filed -> score it against the listed items of its
category (AP18). Both then run "record and notify" for every pair at or above the threshold.

A pair that fails is not allowed to stop the others: every qualifying pair is tried, and the
first error is raised at the end so the stream record is retried. Pairs already recorded are
skipped on the retry by the conditional write.
"""

from __future__ import annotations

import logging

from boto3.dynamodb.conditions import Key

from clients import items_table, reports_table
from notify import record_and_notify
from scoring import score_pair
from settings import MAX_CANDIDATES, QUERY_PAGE_SIZE, get_settings
from timeutil import UUID_RE
from vocab import CATEGORIES, ITEM_STATUS_LISTED, REPORT_STATUS_OPEN, TAG_TAGGED

log = logging.getLogger("matcher")


def _is_id(value) -> bool:
    return isinstance(value, str) and bool(UUID_RE.match(value))


def _query_candidates(table, *, index: str, key_name: str, value: str) -> list[dict]:
    """Newest first, following pages, stopping at MAX_CANDIDATES. No Scan, no filter, no ConsistentRead."""
    rows: list[dict] = []
    start_key = None
    while True:
        args = {
            "IndexName": index,
            "KeyConditionExpression": Key(key_name).eq(value),
            "ScanIndexForward": False,
            "Limit": min(QUERY_PAGE_SIZE, MAX_CANDIDATES - len(rows)),
        }
        if start_key:
            args["ExclusiveStartKey"] = start_key
        response = table.query(**args)
        rows.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            return rows
        if len(rows) >= MAX_CANDIDATES:
            log.warning("candidate cap of %d reached for %s=%s; older rows were not checked", MAX_CANDIDATES, key_name, value)
            return rows


def _valid_item(item: dict) -> bool:
    return (
        _is_id(item.get("itemId"))
        and item.get("category") in CATEGORIES
        and isinstance(item.get("colors"), list)
    )


def _valid_report(report: dict) -> bool:
    return (
        _is_id(report.get("reportId"))
        and _is_id(report.get("ownerId"))
        and report.get("category") in CATEGORIES
        and isinstance(report.get("colors"), list)
    )


def _usable_listed_item(candidate: dict) -> dict | None:
    """Section 6.5 step 3: TAGGED uses the index copy, PENDING is re-read once, FAILED is skipped."""
    status = candidate.get("tagStatus")
    if status == TAG_TAGGED:
        return candidate
    if status == "PENDING":
        # The index may be a moment behind the table. AP3: one consistent read.
        fresh = items_table().get_item(Key={"itemId": candidate["itemId"]}, ConsistentRead=True).get("Item")
        if fresh and fresh.get("tagStatus") == TAG_TAGGED and fresh.get("status") == ITEM_STATUS_LISTED:
            return fresh
    return None  # still PENDING, FAILED, or gone: direction A picks it up when the tags arrive


def process_tagged_item(item: dict) -> dict[str, int]:
    """Direction A. `item` is the whole deserialized NewImage. Returns outcome counts."""
    counts: dict[str, int] = {}
    if not _valid_item(item):
        log.warning("skipped malformed item record")
        return _bump(counts, "skipped-malformed")
    item_id = item["itemId"]

    reports = _query_candidates(
        reports_table(),
        index=get_settings().idx_open_by_category,
        key_name="openCategory",
        value=item["category"],
    )
    pairs = []
    for report in reports:
        if not _valid_report(report):
            log.warning("skipped malformed report candidate for item=%s", item_id)
            _bump(counts, "skipped-malformed")
            continue
        pairs.append((report, item))
    return _score_and_notify(pairs, counts)


def process_new_report(report: dict) -> dict[str, int]:
    """Direction B. `report` is the whole deserialized NewImage. Returns outcome counts."""
    counts: dict[str, int] = {}
    if not _valid_report(report):
        log.warning("skipped malformed report record")
        return _bump(counts, "skipped-malformed")

    candidates = _query_candidates(
        items_table(),
        index=get_settings().idx_listed_by_category,
        key_name="listedCategory",
        value=report["category"],
    )
    pairs = []
    for candidate in candidates:
        if not _is_id(candidate.get("itemId")):
            _bump(counts, "skipped-malformed")
            continue
        item = _usable_listed_item(candidate)
        if item is None:
            _bump(counts, "skipped-untagged")
            continue
        if not _valid_item(item):
            _bump(counts, "skipped-malformed")
            continue
        pairs.append((report, item))
    return _score_and_notify(pairs, counts)


def _score_and_notify(pairs: list[tuple[dict, dict]], counts: dict[str, int]) -> dict[str, int]:
    threshold = get_settings().threshold
    first_error: Exception | None = None
    for report, item in pairs:
        result = score_pair(report, item)
        if result is None:
            _bump(counts, "skipped-category")
            continue
        if result.total < threshold:
            _bump(counts, "below-threshold")
            continue
        try:
            outcome = record_and_notify(
                report_id=report["reportId"],
                item_id=item["itemId"],
                owner_id=report["ownerId"],
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 - keep trying the other pairs, raise below
            log.error("pair failed report=%s item=%s score=%d error=%s", report["reportId"], item["itemId"], result.total, type(exc).__name__)
            _bump(counts, "failed")
            first_error = first_error or exc
            continue
        log.info("pair report=%s item=%s score=%d outcome=%s", report["reportId"], item["itemId"], result.total, outcome)
        _bump(counts, outcome)
    if first_error is not None:
        raise first_error
    return counts


def _bump(counts: dict[str, int], name: str) -> dict[str, int]:
    counts[name] = counts.get(name, 0) + 1
    return counts
