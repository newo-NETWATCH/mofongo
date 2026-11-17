"""Shared test harness for the API Lambda handler. No real AWS: everything runs under moto.

Fixtures (every test module uses these names):
  api_env      autouse. Test environment variables, sys.path, and every lazy cache cleared.
  aws          moto DynamoDB tables, S3 bucket and SNS topic. Request it in any test that
               reaches AWS (all routes that pass authentication do).
  make_claims  fixture returning make_claims(sub=None, email=..., email_verified=..., **overrides) -> dict
  make_event   fixture returning make_event(method, resource, path=None, query=None, body=None,
               claims=<valid claims>) -> dict
  call         fixture returning call(event) -> (status:int, body:dict|str, headers:dict)

Usage:
    def test_x(aws, make_event, call):
        status, body, headers = call(make_event("GET", "/items"))

The helpers are both fixtures and plain importable functions (from conftest import call, ...).
Plain use is only valid while the api_env autouse fixture is active (i.e. inside a test).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import moto and boto3 with the handler directory hidden from sys.path. "python -m pytest" run
# from backend/api puts that directory (as "" or its full path) first, which would let the
# handler's responses.py shadow the third-party "responses" package that moto imports.
_HERE_API = Path(__file__).resolve().parents[1]
_saved_path = list(sys.path)
sys.path[:] = [
    p for p in sys.path
    if not (p == "" or p == "." or Path(p).resolve() == _HERE_API)
]
try:
    import boto3
    from moto import mock_aws
finally:
    sys.path[:] = _saved_path

# NAME CLASH: the handler has its own top-level module "responses" (responses.py), and moto
# depends on the third-party "responses" package. moto has just imported the real one. Take the
# third-party modules out of sys.modules (moto keeps its own references) so the handler's
# "from responses import json_response" finds backend/api/responses.py. This import order must
# stay: moto first, then the handler directory on sys.path. Do not add pythonpath to pytest.ini.
for _name in [n for n in sys.modules if n == "responses" or n.startswith("responses.")]:
    del sys.modules[_name]

# backend/api/tests/conftest.py -> backend/api (flat package, handler is app.handler)
API_DIR = Path(__file__).resolve().parents[1]
# The request schemas live at <repo root>/api/schemas (the Lambda zip copies them to /var/task/schemas).
SCHEMA_DIR = API_DIR.parents[1] / "api" / "schemas"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

REGION = "us-east-2"
USER_POOL_ID = "us-east-2_TESTPOOL"
APP_CLIENT_ID = "testclient123"
ISS = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

TEST_ENV = {
    "ITEMS_TABLE": "mofongo-test-items",
    "REPORTS_TABLE": "mofongo-test-reports",
    "MATCHES_TABLE": "mofongo-test-matches",
    "USERS_TABLE": "mofongo-test-users",
    "IDX_LISTED_BY_DATE": "ListedByDate",
    "IDX_LISTED_BY_CATEGORY": "ListedByCategory",
    "IDX_BY_OWNER": "ByOwner",
    "PHOTOS_BUCKET": "mofongo-test-photos",
    "ALERTS_TOPIC_ARN": "arn:aws:sns:us-east-2:123456789012:mofongo-test-alerts",
    "USER_POOL_ID": USER_POOL_ID,
    "APP_CLIENT_ID": APP_CLIENT_ID,
    "CORS_ORIGIN": "http://localhost:5173",
    "AWS_DEFAULT_REGION": REGION,
    "AWS_REGION": REGION,
    # Dummy credentials. moto never validates them, and they cannot reach a real account.
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "SCHEMA_DIR": str(SCHEMA_DIR),
    "PRESIGN_TTL_SECONDS": "900",
    "PHOTO_MAX_BYTES": "10485760",
    # Never let the SDK look for a profile, a custom endpoint or instance metadata.
    "AWS_EC2_METADATA_DISABLED": "true",
}

# Variables that would point boto3 at a real account or another endpoint.
_UNSET_ENV = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_DYNAMODB",
    "AWS_ENDPOINT_URL_S3",
    "AWS_ENDPOINT_URL_SNS",
    "AWS_CONFIG_FILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "LOG_LEVEL",
)


def _clear_caches() -> None:
    """Drop every lru_cache in the handler so settings and clients are rebuilt under this test."""
    import aws as aws_module  # noqa: WPS433 - imported lazily, after the environment is set
    import config
    import validation

    config.get_settings.cache_clear()
    for name in ("dynamodb_resource", "s3_client", "sns_client"):
        getattr(aws_module, name).cache_clear()
    validation._validator.cache_clear()


@pytest.fixture(autouse=True)
def api_env(monkeypatch):
    """Set the test environment BEFORE app is imported and before any boto3 client exists."""
    for name in _UNSET_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    assert SCHEMA_DIR.is_dir(), f"Request schemas not found at {SCHEMA_DIR}"
    _clear_caches()
    yield dict(TEST_ENV)
    _clear_caches()


def _create_tables(ddb) -> SimpleNamespace:
    """The four tables, mirroring infra/modules/dynamodb/main.tf (names, keys, GSIs, projections)."""

    def attrs(**types):
        return [{"AttributeName": name, "AttributeType": kind} for name, kind in types.items()]

    def gsi(name, hash_key, range_key):
        return {
            "IndexName": name,
            "KeySchema": [
                {"AttributeName": hash_key, "KeyType": "HASH"},
                {"AttributeName": range_key, "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }

    items = ddb.create_table(
        TableName=TEST_ENV["ITEMS_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "itemId", "KeyType": "HASH"}],
        AttributeDefinitions=attrs(itemId="S", listedPk="S", listedCategory="S", createdAt="S"),
        GlobalSecondaryIndexes=[
            gsi(TEST_ENV["IDX_LISTED_BY_DATE"], "listedPk", "createdAt"),
            gsi(TEST_ENV["IDX_LISTED_BY_CATEGORY"], "listedCategory", "createdAt"),
        ],
    )
    reports = ddb.create_table(
        TableName=TEST_ENV["REPORTS_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "ownerId", "KeyType": "HASH"},
            {"AttributeName": "reportId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attrs(ownerId="S", reportId="S", openCategory="S", createdAt="S"),
        GlobalSecondaryIndexes=[
            gsi(TEST_ENV["IDX_BY_OWNER"], "ownerId", "createdAt"),
            gsi("OpenByCategory", "openCategory", "createdAt"),
        ],
    )
    matches = ddb.create_table(
        TableName=TEST_ENV["MATCHES_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "reportId", "KeyType": "HASH"},
            {"AttributeName": "itemId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attrs(reportId="S", itemId="S"),
    )
    users = ddb.create_table(
        TableName=TEST_ENV["USERS_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=attrs(userId="S"),
    )
    return SimpleNamespace(items=items, reports=reports, matches=matches, users=users)


@pytest.fixture
def aws(api_env):
    """moto-backed DynamoDB, S3 and SNS, active for the whole test.

    Yields a namespace: .ddb (boto3 resource), .ddb_client, .s3, .sns (clients), the table objects
    .items .reports .matches .users, plus .bucket and .topic_arn. Seed through these.
    """
    with mock_aws():
        # Built after mock_aws starts, with the test region and dummy credentials already in the env.
        ddb = boto3.resource("dynamodb", region_name=REGION)
        s3 = boto3.client("s3", region_name=REGION)
        sns = boto3.client("sns", region_name=REGION)

        tables = _create_tables(ddb)
        s3.create_bucket(
            Bucket=TEST_ENV["PHOTOS_BUCKET"],
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        topic_arn = sns.create_topic(Name="mofongo-test-alerts")["TopicArn"]
        assert topic_arn == TEST_ENV["ALERTS_TOPIC_ARN"], topic_arn

        # Handler clients must be built inside the mock, not reused from an earlier test.
        _clear_caches()

        yield SimpleNamespace(
            ddb=ddb,
            ddb_client=ddb.meta.client,
            s3=s3,
            sns=sns,
            items=tables.items,
            reports=tables.reports,
            matches=tables.matches,
            users=tables.users,
            bucket=TEST_ENV["PHOTOS_BUCKET"],
            topic_arn=topic_arn,
        )


def make_claims(sub=None, email="owner@example.com", email_verified="true", **overrides) -> dict:
    claims = {
        "sub": sub if sub is not None else str(uuid.uuid4()),
        "token_use": "id",
        "aud": os.environ.get("APP_CLIENT_ID", APP_CLIENT_ID),
        "iss": f"https://cognito-idp.{os.environ.get('AWS_REGION', REGION)}.amazonaws.com/"
        f"{os.environ.get('USER_POOL_ID', USER_POOL_ID)}",
        "email": email,
        "email_verified": email_verified,
    }
    claims.update(overrides)
    # Authorizer claims are strings in API Gateway payload 1.0. Overriding a claim with None DROPS it.
    return {key: value for key, value in claims.items() if value is not None}


_VALID = object()


def make_event(
    method,
    resource,
    path=None,
    query=None,
    body=None,
    claims=_VALID,
    *,
    headers=None,
    raw_body=None,
    base64_body=False,
) -> dict:
    """An API Gateway REST proxy event (payload 1.0).

    body: a dict/list is json.dumps'd. raw_body: a str sent as-is (for malformed JSON); with
    base64_body=True the encoded text is sent and isBase64Encoded is set.
    claims: omit for valid claims for a new random user, a dict for custom claims, None for no authorizer.
    """
    if claims is _VALID:
        claims = make_claims()

    if raw_body is not None:
        body_text = raw_body
    elif body is None:
        body_text = None
    else:
        body_text = json.dumps(body)
    if base64_body and body_text is not None:
        body_text = base64.b64encode(body_text.encode("utf-8")).decode("ascii")

    event_headers = {"Content-Type": "application/json"}
    if headers:
        event_headers.update(headers)

    request_context = {}
    if claims is not None:
        request_context["authorizer"] = {"claims": claims}

    return {
        "httpMethod": method,
        "resource": resource,
        "path": resource,
        "pathParameters": dict(path) if path else None,
        "queryStringParameters": dict(query) if query else None,
        "multiValueQueryStringParameters": {k: [v] for k, v in query.items()} if query else None,
        "headers": event_headers,
        "body": body_text,
        "isBase64Encoded": bool(base64_body and body_text is not None),
        "requestContext": request_context,
    }


def call(event) -> tuple[int, object, dict]:
    import app  # imported after api_env has set the environment

    response = app.handler(event)
    raw = response.get("body")
    try:
        body = json.loads(raw) if raw else raw
    except (TypeError, ValueError):
        body = raw
    return int(response["statusCode"]), body, dict(response.get("headers") or {})


# The helpers are plain module-level functions (import them: "from conftest import call, make_event,
# make_claims") AND fixtures of the same names (request them as arguments). The fixtures are registered
# under name= so the module attributes above stay callable.
@pytest.fixture(name="make_claims")
def _make_claims_fixture(api_env):
    return make_claims


@pytest.fixture(name="make_event")
def _make_event_fixture(api_env):
    return make_event


@pytest.fixture(name="call")
def _call_fixture(api_env):
    return call
