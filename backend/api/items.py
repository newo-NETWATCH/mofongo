"""Items: listItems, createItem, getItem, markItemReturned (data-model AP1 to AP4, AP7)."""

from __future__ import annotations

import uuid

from boto3.dynamodb.conditions import Attr, Key

import pagination
import photos
import serializers
import validation
from auth import Caller
from aws import items_table
from config import LISTED_PARTITION, get_settings
from errors import ApiError, bad_request
from store import old_row_from_failure, query_page
from timeutil import iso_now

Response = tuple[int, dict]


def list_items(event: dict, caller: Caller) -> Response:
    limit, category, token = validation.list_params(event, allow_category=True)
    settings = get_settings()

    if category is None:  # AP1
        index = settings.idx_listed_by_date
        index_name, partition_attr, partition_value = "ListedByDate", "listedPk", LISTED_PARTITION
    else:  # AP2
        index = settings.idx_listed_by_category
        index_name, partition_attr, partition_value = "ListedByCategory", "listedCategory", category
    query_id = f"{index_name}|{partition_value}"

    start_key = None
    if token is not None:
        start_key = pagination.decode(
            token,
            index=index_name,
            query_id=query_id,
            partition_attr=partition_attr,
            partition_value=partition_value,
        )

    rows, last_key = query_page(
        items_table(),
        index=index,
        key_condition=Key(partition_attr).eq(partition_value),
        limit=limit,
        start_key=start_key,
    )
    body: dict = {"items": [serializers.item_summary(row, caller.sub) for row in rows]}
    if last_key:
        body["nextToken"] = pagination.encode(query_id, last_key)
    return 200, body


def create_item(event: dict, caller: Caller) -> Response:
    data = validation.parse_json_body(event, "create-item")
    times, time_problems = validation.check_time_fields(data, ("foundAt",))
    if time_problems:
        raise bad_request(time_problems)

    item_id = str(uuid.uuid4())
    row = {
        "itemId": item_id,
        "finderId": caller.sub,  # from the token, never from the body
        "title": data["title"],
        "category": data["category"],
        "colors": list(data["colors"]),
        "foundLocation": data["foundLocation"],
        "foundAt": times["foundAt"],
        "status": "LISTED",
        "photoKey": photos.photo_key(item_id),
        "tagStatus": "PENDING",
        "createdAt": iso_now(),
        "listedPk": LISTED_PARTITION,
        "listedCategory": data["category"],
    }
    if data.get("description"):
        row["description"] = data["description"]

    table = items_table()
    try:  # AP4. The item is written first, the upload form handed out second.
        table.put_item(Item=row, ConditionExpression=Attr("itemId").not_exists())
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        raise ApiError(409, "The item could not be created. Try again.")

    return 201, {
        "itemId": item_id,
        "item": serializers.new_item(row),
        "upload": photos.upload_form(item_id),
    }


def get_item(event: dict, caller: Caller) -> Response:
    item_id = validation.path_uuid(event, "itemId")
    row = items_table().get_item(Key={"itemId": item_id}, ConsistentRead=True).get("Item")  # AP3
    if row is None:
        raise ApiError(404, "Item not found.")
    return 200, serializers.item_detail(row, caller.sub)


def mark_item_returned(event: dict, caller: Caller) -> Response:
    item_id = validation.path_uuid(event, "itemId")
    key = {"itemId": item_id}
    table = items_table()
    try:  # AP7. The condition makes the finder check and the state check atomic.
        response = table.update_item(
            Key=key,
            UpdateExpression="SET #status = :returned, returnedAt = :now REMOVE listedPk, listedCategory",
            ConditionExpression="attribute_exists(itemId) AND finderId = :sub AND #status = :listed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":returned": "RETURNED",
                ":listed": "LISTED",
                ":now": iso_now(),
                ":sub": caller.sub,
            },
            ReturnValues="ALL_NEW",
            ReturnValuesOnConditionCheckFailure="ALL_OLD",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException as error:
        old = old_row_from_failure(error, table, key)
        if old is None:
            raise ApiError(404, "Item not found.")
        if old.get("finderId") != caller.sub:
            raise ApiError(403, "Only the finder can mark this item returned.")
        raise ApiError(409, "This item is already marked returned.")
    return 200, serializers.item_detail(response["Attributes"], caller.sub)
