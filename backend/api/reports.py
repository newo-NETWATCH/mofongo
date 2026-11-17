"""Reports: listReports, createReport, getReport, closeReport (data-model AP8 to AP13).

Every Reports key is built from the token's sub. A report ID from the URL is only ever the
sort key, so someone else's ID finds nothing and answers 404, never 403.
"""

from __future__ import annotations

import uuid

from boto3.dynamodb.conditions import Attr, Key

import alerts
import pagination
import serializers
import validation
from auth import Caller
from aws import matches_table, reports_table
from config import MAX_MATCHES, get_settings
from errors import ApiError, bad_request
from store import batch_get_items, old_row_from_failure, query_page
from timeutil import iso_now

Response = tuple[int, dict]

_NOT_FOUND = "Report not found."


def list_reports(event: dict, caller: Caller) -> Response:
    limit, _category, token = validation.list_params(event, allow_category=False)
    query_id = f"ByOwner|{caller.sub}"  # AP10: the partition value always comes from the token

    start_key = None
    if token is not None:
        start_key = pagination.decode(
            token,
            index="ByOwner",
            query_id=query_id,
            partition_attr="ownerId",
            partition_value=caller.sub,
        )

    rows, last_key = query_page(
        reports_table(),
        index=get_settings().idx_by_owner,
        key_condition=Key("ownerId").eq(caller.sub),
        limit=limit,
        start_key=start_key,
    )
    body: dict = {"reports": [serializers.report(row) for row in rows]}
    if last_key:
        body["nextToken"] = pagination.encode(query_id, last_key)
    return 200, body


def create_report(event: dict, caller: Caller) -> Response:
    data = validation.parse_json_body(event, "create-report")
    times, time_problems = validation.check_time_fields(data, ("lostAt",))
    if time_problems:
        raise bad_request(time_problems)

    row = {
        "ownerId": caller.sub,  # from the token, never from the body
        "reportId": str(uuid.uuid4()),
        "category": data["category"],
        "colors": list(data["colors"]),
        "description": data["description"],
        "status": "OPEN",
        "openCategory": data["category"],
        "createdAt": iso_now(),
    }
    if data.get("lostLocation"):
        row["lostLocation"] = data["lostLocation"]
    if "lostAt" in times:
        row["lostAt"] = times["lostAt"]

    table = reports_table()
    try:  # AP9
        table.put_item(Item=row, ConditionExpression=Attr("reportId").not_exists())
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        raise ApiError(409, "The report could not be created. Try again.")

    # The report is saved first. A problem with email alerts never fails this route.
    outcome = alerts.start_for_new_report(caller)
    return 201, {"report": serializers.report(row), "alerts": outcome}


def get_report(event: dict, caller: Caller) -> Response:
    report_id = validation.path_uuid(event, "reportId")

    # AP11. Matches are keyed by reportId alone, so the key does not protect them. They are
    # read only after this call has shown that the report belongs to the caller. Keep the two
    # together in this function.
    row = reports_table().get_item(
        Key={"ownerId": caller.sub, "reportId": report_id}, ConsistentRead=True
    ).get("Item")
    if row is None:
        raise ApiError(404, _NOT_FOUND)

    # AP13. TODO(week 6): Limit=100 returns the first 100 by itemId, not the best 100.
    # If a report can ever have more than 100 matches, read them all and keep the top 100.
    found = matches_table().query(
        KeyConditionExpression=Key("reportId").eq(report_id), Limit=MAX_MATCHES
    ).get("Items", [])

    items = batch_get_items([m["itemId"] for m in found])  # AP8
    matches = [
        serializers.match(m, items[m["itemId"]], caller.sub) for m in found if m["itemId"] in items
    ]
    matches.sort(key=lambda m: (m["score"], m["createdAt"]), reverse=True)
    return 200, {"report": serializers.report(row), "matches": matches}


def close_report(event: dict, caller: Caller) -> Response:
    report_id = validation.path_uuid(event, "reportId")
    key = {"ownerId": caller.sub, "reportId": report_id}
    table = reports_table()
    try:  # AP12. Removing openCategory takes the report out of OpenByCategory in the same write.
        response = table.update_item(
            Key=key,
            UpdateExpression="SET #status = :closed, closedAt = :now REMOVE openCategory",
            ConditionExpression="attribute_exists(reportId) AND #status = :open",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":closed": "CLOSED", ":open": "OPEN", ":now": iso_now()},
            ReturnValues="ALL_NEW",
            ReturnValuesOnConditionCheckFailure="ALL_OLD",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException as error:
        if old_row_from_failure(error, table, key) is None:
            raise ApiError(404, _NOT_FOUND)
        raise ApiError(409, "This report is already closed.")
    return 200, serializers.report(response["Attributes"])
