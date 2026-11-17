"""The Items table update (data-model.md sections 4.1, 6.2 and 6.8).

Two writes, both conditional so a repeat or a late delivery changes nothing:

    mark_tagged   PENDING -> TAGGED while LISTED. This is the change the matcher's stream
                  filter waits for (OldImage.tagStatus PENDING, NewImage TAGGED and LISTED).
    mark_failed   PENDING -> FAILED while LISTED, with a short tagError.

The condition is `status = LISTED AND tagStatus = PENDING AND photoKey = :key`:
  - a RETURNED item is never touched,
  - a TAGGED item is never overwritten (S3 delivers at least once, and a duplicate message
    must not tag twice or flip a good item to FAILED),
  - a FAILED item stays FAILED until someone resets it to PENDING (README, "Failed photos"),
  - an event whose key is not the item's own photoKey is ignored.
The item row exists before the photo does (the API writes it first), so a missing row means
the item is gone and there is nothing to tag.

Both functions return True when the row was written and False when the condition said no.
Any other error is raised, so the caller keeps the SQS message.
"""

from __future__ import annotations

from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_CONFIG = Config(retries={"mode": "standard", "total_max_attempts": 4}, connect_timeout=5, read_timeout=10)

_CONDITION = "#status = :listed AND #tagStatus = :pending AND photoKey = :key"
_NAMES = {"#status": "status", "#tagStatus": "tagStatus"}

TAG_ERROR_MAX = 200


def now_iso() -> str:
    """ISO 8601 UTC with milliseconds, like the other timestamps (2026-10-20T16:41:12.481Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ItemStore:
    def __init__(self, table_name: str, region: str, table=None) -> None:
        # `table` lets tests pass their own; production builds it from the name.
        self._table = table or boto3.resource("dynamodb", region_name=region, config=_CONFIG).Table(table_name)

    def _update(self, item_id: str, photo_key: str, expression: str, names: dict, values: dict) -> bool:
        try:
            self._table.update_item(
                Key={"itemId": item_id},
                UpdateExpression=expression,
                ConditionExpression=_CONDITION,
                ExpressionAttributeNames={**_NAMES, **names},
                ExpressionAttributeValues={":listed": "LISTED", ":pending": "PENDING", ":key": photo_key, **values},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def needs_tags(self, item_id: str, photo_key: str) -> bool:
        """True when the item is LISTED, still PENDING and owns this photo key.

        A cheap read so a repeated S3 event does not cost a CLIP run. It is only an
        optimization: the conditional writes above stay the real guard against a race.
        """
        resp = self._table.get_item(
            Key={"itemId": item_id},
            ConsistentRead=True,
            ProjectionExpression="#status, #tagStatus, photoKey",
            ExpressionAttributeNames=_NAMES,
        )
        row = resp.get("Item")
        return bool(
            row
            and row.get("status") == "LISTED"
            and row.get("tagStatus") == "PENDING"
            and row.get("photoKey") == photo_key
        )

    def mark_tagged(self, item_id: str, photo_key: str, clip_tags: dict) -> bool:
        return self._update(
            item_id,
            photo_key,
            "SET #tagStatus = :tagged, clipTags = :tags, taggedAt = :at REMOVE tagError",
            {},
            {":tagged": "TAGGED", ":tags": clip_tags, ":at": now_iso()},
        )

    def mark_failed(self, item_id: str, photo_key: str, reason: str) -> bool:
        return self._update(
            item_id,
            photo_key,
            "SET #tagStatus = :failed, tagError = :err",
            {},
            {":failed": "FAILED", ":err": reason[:TAG_ERROR_MAX]},
        )
