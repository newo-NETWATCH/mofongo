"""Email alerts: getMyAlerts, subscribeMyAlerts, and the subscription step of createReport.

data-model 6.6. The Lambda only subscribes and reads subscription state. Publishing
belongs to the matcher, so this role has no sns:Publish. The email always comes from the
verified token claim, never from a request.
"""

from __future__ import annotations

import json
import logging

from botocore.exceptions import ClientError

from auth import Caller
from aws import sns_client, users_table
from config import get_settings
from errors import ApiError
from timeutil import iso_now

logger = logging.getLogger(__name__)
Response = tuple[int, dict]


def _saved_arn(caller: Caller) -> str | None:
    row = users_table().get_item(Key={"userId": caller.sub}, ConsistentRead=True).get("Item")  # AP19
    return row.get("subscriptionArn") if row else None


def _state(arn: str) -> str:
    sns = sns_client()
    try:
        attributes = sns.get_subscription_attributes(SubscriptionArn=arn)["Attributes"]
    except sns.exceptions.NotFoundException:
        return "GONE"
    return "UNCONFIRMED" if attributes.get("PendingConfirmation") == "true" else "CONFIRMED"


def _subscribe(caller: Caller, email: str) -> str:
    """Subscribe the caller's email with a filter on their user ID. Returns the ARN.

    The filter policy goes inside the Subscribe call, so there is never a moment with an
    unfiltered subscription. It is never changed afterwards.
    """
    response = sns_client().subscribe(
        TopicArn=get_settings().alerts_topic_arn,
        Protocol="email",
        Endpoint=email,
        Attributes={"FilterPolicy": json.dumps({"ownerId": [caller.sub]})},
        ReturnSubscriptionArn=True,
    )
    return response["SubscriptionArn"]


def _save(caller: Caller, arn: str) -> None:
    """AP20: overwrites on purpose, a new subscription replaces the old ARN."""
    users_table().put_item(
        Item={"userId": caller.sub, "subscriptionArn": arn, "subscribedAt": iso_now()}
    )


def start_for_new_report(caller: Caller) -> str:
    """The `alerts` value for POST /reports. Never raises: the report is already saved."""
    try:
        if _saved_arn(caller) is not None:
            return "existing"
        email = caller.alert_email
        if email is None:
            return "no-verified-email"
        _save(caller, _subscribe(caller, email))
        return "started"
    except Exception:
        logger.exception("Email alerts could not be started")
        return "unavailable"


def get_my_alerts(event: dict, caller: Caller) -> Response:
    arn = _saved_arn(caller)
    if arn is None:
        return 200, {"state": "NONE"}
    return 200, {"state": _state(arn)}


def subscribe_my_alerts(event: dict, caller: Caller) -> Response:
    email = caller.alert_email
    if email is None:
        raise ApiError(403, "Email alerts need a verified email address.")
    try:
        arn = _subscribe(caller, email)
    except ClientError as error:
        # For example FilterPolicyLimitExceeded at 200 filter policies per topic. Nothing saved.
        logger.error("SNS refused the subscription: %s", error.response.get("Error", {}).get("Code"))
        raise ApiError(503, "Email alerts are not available right now.")
    _save(caller, arn)
    return 200, {"state": _state(arn)}
