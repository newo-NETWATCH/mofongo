"""Test harness for the matcher. No real AWS: everything runs under moto.

Fixtures:
  matcher_env  autouse. Test environment variables, sys.path, every lazy cache cleared.
  aws          moto tables (Items, Reports, Matches), an SNS topic with one SQS queue per owner
               (so tests can see which owner got which message), and the tables as attributes.
  stream_record(table, event_name, new=None, old=None, seq=...) builds a DynamoDB Streams record.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws

MATCHER_DIR = Path(__file__).resolve().parents[1]
REGION = "us-east-2"

# The matcher modules are flat (no package), so the folder itself goes on sys.path.
if str(MATCHER_DIR) not in sys.path:
    sys.path.insert(0, str(MATCHER_DIR))

TEST_ENV = {
    "ITEMS_TABLE": "mofongo-test-items",
    "REPORTS_TABLE": "mofongo-test-reports",
    "MATCHES_TABLE": "mofongo-test-matches",
    "IDX_LISTED_BY_CATEGORY": "ListedByCategory",
    "IDX_OPEN_BY_CATEGORY": "OpenByCategory",
    "ALERTS_TOPIC_ARN": "arn:aws:sns:us-east-2:123456789012:mofongo-test-alerts",
    "SITE_URL": "https://site.example/",
    "AWS_DEFAULT_REGION": REGION,
    "AWS_REGION": REGION,
    # Dummy credentials. moto never validates them, and they cannot reach a real account.
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_EC2_METADATA_DISABLED": "true",
}

_UNSET_ENV = (
    "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_DYNAMODB",
    "AWS_ENDPOINT_URL_SNS", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE",
    "LOG_LEVEL", "MATCH_THRESHOLD",
)

_serializer = TypeSerializer()


def _clear_caches() -> None:
    import clients
    import settings

    settings.get_settings.cache_clear()
    clients.dynamodb_resource.cache_clear()
    clients.sns_client.cache_clear()


@pytest.fixture(autouse=True)
def matcher_env(monkeypatch):
    for name in _UNSET_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    if str(MATCHER_DIR) not in sys.path:
        sys.path.insert(0, str(MATCHER_DIR))
    _clear_caches()
    yield
    _clear_caches()


def _gsi(name, hash_key):
    return {
        "IndexName": name,
        "KeySchema": [
            {"AttributeName": hash_key, "KeyType": "HASH"},
            {"AttributeName": "createdAt", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }


def _attrs(**types):
    return [{"AttributeName": n, "AttributeType": t} for n, t in types.items()]


@pytest.fixture
def aws(matcher_env):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        items = ddb.create_table(
            TableName=TEST_ENV["ITEMS_TABLE"],
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "itemId", "KeyType": "HASH"}],
            AttributeDefinitions=_attrs(itemId="S", listedCategory="S", createdAt="S"),
            GlobalSecondaryIndexes=[_gsi("ListedByCategory", "listedCategory")],
        )
        reports = ddb.create_table(
            TableName=TEST_ENV["REPORTS_TABLE"],
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "ownerId", "KeyType": "HASH"},
                {"AttributeName": "reportId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=_attrs(ownerId="S", reportId="S", openCategory="S", createdAt="S"),
            GlobalSecondaryIndexes=[_gsi("OpenByCategory", "openCategory")],
        )
        matches = ddb.create_table(
            TableName=TEST_ENV["MATCHES_TABLE"],
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "reportId", "KeyType": "HASH"},
                {"AttributeName": "itemId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=_attrs(reportId="S", itemId="S"),
        )
        sns = boto3.client("sns", region_name=REGION)
        sqs = boto3.client("sqs", region_name=REGION)
        topic_arn = sns.create_topic(Name="mofongo-test-alerts")["TopicArn"]
        assert topic_arn == TEST_ENV["ALERTS_TOPIC_ARN"], topic_arn
        _clear_caches()

        def subscribe_owner(owner_id: str) -> str:
            """A queue that receives only this owner's messages, like the email subscription does."""
            url = sqs.create_queue(QueueName=f"owner-{owner_id[:8]}")["QueueUrl"]
            arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
            sns.subscribe(
                TopicArn=topic_arn,
                Protocol="sqs",
                Endpoint=arn,
                Attributes={"FilterPolicy": json.dumps({"ownerId": [owner_id]}), "RawMessageDelivery": "true"},
            )
            return url

        def messages(queue_url: str) -> list[dict]:
            resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, MessageAttributeNames=["All"])
            return resp.get("Messages", [])

        yield SimpleNamespace(
            ddb=ddb, items=items, reports=reports, matches=matches, sns=sns, sqs=sqs,
            topic_arn=topic_arn, subscribe_owner=subscribe_owner, messages=messages,
        )


def new_id() -> str:
    return str(uuid.uuid4())


def make_item(*, category="water-bottle", colors=("black", "green"), tagged=True, status="LISTED",
              clip_categories=None, clip_colors=None, created_at="2026-10-20T16:38:55.207Z", **extra) -> dict:
    item_id = extra.pop("itemId", None) or new_id()
    item = {
        "itemId": item_id,
        "finderId": new_id(),
        "title": "Black Hydro Flask",
        "category": category,
        "colors": list(colors),
        "foundLocation": "Library",
        "foundAt": "2026-10-20T16:30:00.000Z",
        "status": status,
        "photoKey": f"photos/{item_id}.jpg",
        "tagStatus": "TAGGED" if tagged else "PENDING",
        "createdAt": created_at,
    }
    if status == "LISTED":
        item["listedPk"] = "LISTED"
        item["listedCategory"] = category
    if tagged:
        item["clipTags"] = {
            "categories": clip_categories if clip_categories is not None else [{"value": category, "score": 81}],
            "colors": clip_colors if clip_colors is not None else [{"value": "black", "score": 62}],
        }
    item.update(extra)
    return item


def make_report(*, category="water-bottle", colors=("black",), status="OPEN",
                created_at="2026-10-20T18:02:41.516Z", **extra) -> dict:
    report = {
        "ownerId": extra.pop("ownerId", None) or new_id(),
        "reportId": extra.pop("reportId", None) or new_id(),
        "category": category,
        "colors": list(colors),
        "description": "Black 32 oz Hydro Flask with a dent near the bottom.",
        "status": status,
        "createdAt": created_at,
    }
    if status == "OPEN":
        report["openCategory"] = category
    report.update(extra)
    return report


def stream_record(table: str, event_name: str, new: dict | None = None, old: dict | None = None, seq: str = "100") -> dict:
    def image(row):
        return {name: _serializer.serialize(value) for name, value in row.items()}

    body = {"SequenceNumber": seq}
    if new is not None:
        body["NewImage"] = image(new)
    if old is not None:
        body["OldImage"] = image(old)
    return {
        "eventName": event_name,
        "eventSourceARN": f"arn:aws:dynamodb:{REGION}:123456789012:table/{table}/stream/2026-10-20T00:00:00.000",
        "dynamodb": body,
    }
