"""Tests for getMyAlerts and subscribeMyAlerts (alerts.py).

No real AWS: SNS and DynamoDB come from the `aws` fixture (moto). Fixtures and helpers
(api_env, aws, make_claims, make_event, call) are fixtures from conftest.py.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from botocore.exceptions import ClientError


GET = ("GET", "/me/alerts")
POST = ("POST", "/me/alerts")

# conftest.py provides these as fixtures (not importable functions). This autouse fixture binds the
# live ones to module-level names so the helpers below can call them.
make_claims = make_event = call = None


@pytest.fixture(autouse=True)
def _bind_helpers(make_claims, make_event, call):
    globals().update(make_claims=make_claims, make_event=make_event, call=call)



def _users(aws):
    return aws.ddb.Table(os.environ["USERS_TABLE"])


def _subscriptions(aws):
    topic_arn = os.environ["ALERTS_TOPIC_ARN"]
    return aws.sns.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]


def _subscribe_via_api(aws, sub=None, email="owner@example.com"):
    sub = sub or str(uuid.uuid4())
    claims = make_claims(sub=sub, email=email)
    status, body, _ = call(make_event(*POST, claims=claims))
    assert status == 200, body
    return sub, claims, body


class _SnsProxy:
    """Wraps the moto SNS client and forces the subscription's PendingConfirmation value.

    moto reports a fresh email subscription as PendingConfirmation "false", but real SNS keeps an
    email subscription pending until the recipient clicks the confirmation link. Force the value so
    the handler's UNCONFIRMED/CONFIRMED branch is what gets tested, not moto's confirmation model.
    Default "false" (confirmed); pass pending="true" for the UNCONFIRMED path.
    """

    def __init__(self, real, pending="false"):
        self._real = real
        self._pending = pending

    def __getattr__(self, name):
        return getattr(self._real, name)

    def get_subscription_attributes(self, SubscriptionArn):
        response = self._real.get_subscription_attributes(SubscriptionArn=SubscriptionArn)
        response["Attributes"]["PendingConfirmation"] = self._pending
        return response


# ---------------------------------------------------------------- getMyAlerts


def test_get_alerts_none_when_user_has_no_row(aws):
    status, body, _ = call(make_event(*GET, claims=make_claims()))
    assert status == 200
    assert body == {"state": "NONE"}


def test_get_alerts_unconfirmed_after_subscribe(aws, monkeypatch):
    import alerts

    sub, claims, _ = _subscribe_via_api(aws)
    # Make SNS report the fresh email subscription as still pending (moto auto-reports it "false").
    monkeypatch.setattr(alerts, "sns_client", lambda: _SnsProxy(aws.sns, pending="true"))
    status, body, _ = call(make_event(*GET, claims=claims))
    assert status == 200
    assert body == {"state": "UNCONFIRMED"}


def test_get_alerts_confirmed_when_subscription_is_confirmed(aws, monkeypatch):
    import alerts

    sub, claims, _ = _subscribe_via_api(aws)
    monkeypatch.setattr(alerts, "sns_client", lambda: _SnsProxy(aws.sns))
    status, body, _ = call(make_event(*GET, claims=claims))
    assert status == 200
    assert body == {"state": "CONFIRMED"}


def test_get_alerts_gone_when_subscription_no_longer_exists(aws):
    sub = str(uuid.uuid4())
    missing_arn = os.environ["ALERTS_TOPIC_ARN"] + ":" + str(uuid.uuid4())
    _users(aws).put_item(Item={"userId": sub, "subscriptionArn": missing_arn})
    status, body, _ = call(make_event(*GET, claims=make_claims(sub=sub)))
    assert status == 200
    assert body == {"state": "GONE"}


def test_get_alerts_row_without_arn_is_none(aws):
    sub = str(uuid.uuid4())
    _users(aws).put_item(Item={"userId": sub})
    status, body, _ = call(make_event(*GET, claims=make_claims(sub=sub)))
    assert status == 200
    assert body == {"state": "NONE"}


def test_get_alerts_only_reads_the_callers_own_row(aws):
    _subscribe_via_api(aws)  # some other user is subscribed
    status, body, _ = call(make_event(*GET, claims=make_claims()))
    assert status == 200
    assert body == {"state": "NONE"}


def test_get_alerts_does_not_leak_arn_or_email(aws):
    _, claims, _ = _subscribe_via_api(aws)
    status, body, _ = call(make_event(*GET, claims=claims))
    assert status == 200
    assert set(body) == {"state"}


# ---------------------------------------------------------------- subscribeMyAlerts


def test_subscribe_creates_pending_email_subscription(aws, monkeypatch):
    import alerts

    # Make SNS report the fresh email subscription as still pending (moto auto-reports it "false").
    monkeypatch.setattr(alerts, "sns_client", lambda: _SnsProxy(aws.sns, pending="true"))
    sub, _, body = _subscribe_via_api(aws, email="owner@example.com")
    assert body == {"state": "UNCONFIRMED"}

    subs = _subscriptions(aws)
    assert len(subs) == 1
    assert subs[0]["Protocol"] == "email"
    assert subs[0]["Endpoint"] == "owner@example.com"


def test_subscribe_sets_filter_policy_on_the_users_id(aws):
    sub, _, _ = _subscribe_via_api(aws)
    arn = _subscriptions(aws)[0]["SubscriptionArn"]
    attributes = aws.sns.get_subscription_attributes(SubscriptionArn=arn)["Attributes"]
    assert json.loads(attributes["FilterPolicy"]) == {"ownerId": [sub]}


def test_subscribe_saves_arn_and_time_on_users_row(aws):
    sub, _, _ = _subscribe_via_api(aws)
    row = _users(aws).get_item(Key={"userId": sub}, ConsistentRead=True)["Item"]
    assert row["subscriptionArn"] == _subscriptions(aws)[0]["SubscriptionArn"]
    assert row["subscribedAt"].endswith("Z")


def test_subscribe_email_comes_from_claim_not_request_body(aws):
    event = make_event(*POST, body={"email": "attacker@example.com"}, claims=make_claims(email="owner@example.com"))
    status, body, _ = call(event)
    assert status == 200
    assert [s["Endpoint"] for s in _subscriptions(aws)] == ["owner@example.com"]


def test_subscribe_two_users_get_separate_filtered_subscriptions(aws):
    sub_a, _, _ = _subscribe_via_api(aws, email="a@example.com")
    sub_b, _, _ = _subscribe_via_api(aws, email="b@example.com")
    filters = {}
    for s in _subscriptions(aws):
        attrs = aws.sns.get_subscription_attributes(SubscriptionArn=s["SubscriptionArn"])["Attributes"]
        filters[s["Endpoint"]] = json.loads(attrs["FilterPolicy"])
    assert filters == {"a@example.com": {"ownerId": [sub_a]}, "b@example.com": {"ownerId": [sub_b]}}


def test_subscribe_twice_succeeds_and_row_points_at_a_live_subscription(aws, monkeypatch):
    import alerts

    # Make SNS report the fresh email subscription as still pending (moto auto-reports it "false").
    monkeypatch.setattr(alerts, "sns_client", lambda: _SnsProxy(aws.sns, pending="true"))
    sub, claims, _ = _subscribe_via_api(aws)
    status, body, _ = call(make_event(*POST, claims=claims))
    assert status == 200
    assert body == {"state": "UNCONFIRMED"}
    row = _users(aws).get_item(Key={"userId": sub}, ConsistentRead=True)["Item"]
    assert row["subscriptionArn"] in {s["SubscriptionArn"] for s in _subscriptions(aws)}


@pytest.mark.parametrize(
    "overrides",
    [
        {"email_verified": "false"},
        {"email_verified": "True"},  # only the exact string "true" counts
        {"email_verified": ""},
        {"email": None},
        {"email": ""},
        {"email": "not-an-email"},
        {"email": "two@@example.com"},
        {"email": "has space@example.com"},
    ],
)
def test_subscribe_without_verified_email_is_403_and_changes_nothing(aws, overrides):
    sub = str(uuid.uuid4())
    claims = make_claims(sub=sub, **overrides)
    status, body, _ = call(make_event(*POST, claims=claims))
    assert status == 403
    assert body == {"message": "Email alerts need a verified email address."}
    assert _subscriptions(aws) == []
    assert "Item" not in _users(aws).get_item(Key={"userId": sub}, ConsistentRead=True)


def test_subscribe_without_email_claim_key_is_403(aws):
    claims = make_claims(email=None)  # None drops the claim
    assert "email" not in claims
    status, body, _ = call(make_event(*POST, claims=claims))
    assert status == 403
    assert body["message"] == "Email alerts need a verified email address."
    assert _subscriptions(aws) == []


def test_subscribe_sns_refusal_is_503_and_nothing_is_saved(aws, monkeypatch):
    import alerts

    def refuse(caller, email):
        raise ClientError(
            {"Error": {"Code": "FilterPolicyLimitExceeded", "Message": "arn:aws:sns:secret detail"}},
            "Subscribe",
        )

    monkeypatch.setattr(alerts, "_subscribe", refuse)
    sub = str(uuid.uuid4())
    status, body, _ = call(make_event(*POST, claims=make_claims(sub=sub)))
    assert status == 503
    assert body == {"message": "Email alerts are not available right now."}
    assert "Item" not in _users(aws).get_item(Key={"userId": sub}, ConsistentRead=True)


def test_subscribe_response_has_state_only(aws):
    _, _, body = _subscribe_via_api(aws)
    assert set(body) == {"state"}
    assert "owner@example.com" not in json.dumps(body)
    assert "arn:" not in json.dumps(body)


def test_subscribe_never_publishes_to_the_topic(aws, monkeypatch):
    # data-model 6.6: the API role has no sns:Publish, so the code must never call it.
    import alerts

    real = aws.sns

    class NoPublish(_SnsProxy):
        def publish(self, *args, **kwargs):  # pragma: no cover - failing path
            raise AssertionError("alerts.py must not publish")

    monkeypatch.setattr(alerts, "sns_client", lambda: NoPublish(real))
    status, _, _ = call(make_event(*POST, claims=make_claims()))
    assert status == 200
