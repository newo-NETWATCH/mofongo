"""Small DynamoDB helpers shared by the route modules."""

from __future__ import annotations

import time

from boto3.dynamodb.types import TypeDeserializer

from aws import dynamodb_resource
from config import get_settings

_deserializer = TypeDeserializer()


def query_page(table, *, index: str, key_condition, limit: int, start_key: dict | None):
    """One page of an index query, newest first (AP1, AP2, AP10). No Scan, no filter.

    Returns (rows, LastEvaluatedKey or None). Index reads are eventually consistent, and
    ConsistentRead must never be passed for an index.
    """
    args = {
        "IndexName": index,
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        args["ExclusiveStartKey"] = start_key
    response = table.query(**args)
    return response.get("Items", []), response.get("LastEvaluatedKey")


def old_row_from_failure(error, table, key: dict) -> dict | None:
    """The row as it was when a conditional write failed.

    With ReturnValuesOnConditionCheckFailure=ALL_OLD the error carries the row in raw
    DynamoDB JSON. If it is missing, read the row. None means there was no row.
    """
    raw = error.response.get("Item")
    if raw:
        return {name: _deserializer.deserialize(value) for name, value in raw.items()}
    return table.get_item(Key=key, ConsistentRead=True).get("Item")


def batch_get_items(item_ids: list[str]) -> dict[str, dict]:
    """The Items rows for up to 100 IDs (AP8), keyed by itemId. Retries UnprocessedKeys."""
    ids = list(dict.fromkeys(item_ids))
    if not ids:
        return {}
    table_name = get_settings().items_table
    pending = {"Keys": [{"itemId": item_id} for item_id in ids]}
    found: dict[str, dict] = {}
    for attempt in range(5):
        response = dynamodb_resource().batch_get_item(RequestItems={table_name: pending})
        for row in response.get("Responses", {}).get(table_name, []):
            found[row["itemId"]] = row
        unprocessed = response.get("UnprocessedKeys") or {}
        if table_name not in unprocessed:
            return found
        pending = unprocessed[table_name]
        time.sleep(0.05 * (2**attempt))
    raise RuntimeError("BatchGetItem still had unprocessed keys after 5 tries")
