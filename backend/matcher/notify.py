"""Record and notify, never twice (data-model.md section 6.7, AP14, AP15, AP16).

1. PutItem into Matches with attribute_not_exists(reportId). The conditional write is the guard:
   ConditionalCheckFailedException means the pair was recorded before, so nothing is sent.
2. Publish to SNS with the owner's ID as the message attribute `ownerId`. The subscription filter
   policy delivers it only to that owner.
3. Set notifiedAt. A failure here is only logged: the email has already gone.

Nothing here logs an email address, a token or the message body.
"""

from __future__ import annotations

import logging

from botocore.exceptions import BotoCoreError, ClientError, ConnectionClosedError, ReadTimeoutError

from clients import matches_table, sns_client
from scoring import Score
from settings import get_settings
from timeutil import iso_now

log = logging.getLogger("matcher")

RECORDED_AND_SENT = "notified"
ALREADY_RECORDED = "already-recorded"
SEND_UNKNOWN = "publish-unknown"

SUBJECT = "Mofongo: a found item may match your report"


def record_and_notify(*, report_id: str, item_id: str, owner_id: str, result: Score) -> str:
    """Run the three steps for one pair at or above the threshold.

    Returns RECORDED_AND_SENT, ALREADY_RECORDED or SEND_UNKNOWN. Raises when SNS refused the
    message or was never reached (after undoing the row), so the caller reports the stream
    record as failed and the retry records and sends the pair again.
    """
    settings = get_settings()
    matches = matches_table()
    key = {"reportId": report_id, "itemId": item_id}

    # Step 1 (AP14). Timestamps are written once, here.
    try:
        matches.put_item(
            Item={
                "reportId": report_id,
                "itemId": item_id,
                "score": result.total,
                "scoreParts": dict(result.parts),
                "why": list(result.why),
                "createdAt": iso_now(),
            },
            ConditionExpression="attribute_not_exists(reportId)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return ALREADY_RECORDED  # recorded before: never email it twice
        raise

    # Step 2. The body is only a link; the match details stay in the app.
    try:
        sns_client().publish(
            TopicArn=settings.alerts_topic_arn,
            Subject=SUBJECT,
            Message=f"Open {settings.site_url}/reports/{report_id} to see it.",
            MessageAttributes={"ownerId": {"DataType": "String", "StringValue": owner_id}},
        )
    except (ReadTimeoutError, ConnectionClosedError):
        # The request reached SNS but the answer was lost, so it may have sent the email.
        # Keep the row and do not retry (a retry would find the row and send nothing anyway).
        log.warning("publish result unknown report=%s item=%s", report_id, item_id)
        return SEND_UNKNOWN
    except (ClientError, BotoCoreError):
        # SNS refused, or the request never reached SNS. Undo the row (AP16) so the retry can
        # record and send the pair again, then let the handler report the record as failed.
        _undo(matches, key, report_id, item_id)
        raise

    # Step 3 (AP15). The email has gone; a failure here is only logged.
    try:
        matches.update_item(
            Key=key,
            UpdateExpression="SET notifiedAt = :now",
            ConditionExpression="attribute_exists(reportId)",
            ExpressionAttributeValues={":now": iso_now()},
        )
    except (ClientError, BotoCoreError) as exc:
        log.error("notifiedAt not saved report=%s item=%s error=%s", report_id, item_id, _code(exc))
    return RECORDED_AND_SENT


def _undo(matches, key: dict, report_id: str, item_id: str) -> None:
    try:
        matches.delete_item(Key=key, ConditionExpression="attribute_not_exists(notifiedAt)")
    except (ClientError, BotoCoreError) as exc:
        # The row stays, so a retry would find it and send nothing. Make that loud.
        log.error("undo failed, match kept without email report=%s item=%s error=%s", report_id, item_id, _code(exc))


def _code(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", "ClientError")
    return type(exc).__name__
