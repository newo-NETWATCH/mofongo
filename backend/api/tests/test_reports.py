"""Tests for the report routes: createReport, listReports, getReport, closeReport.

Everything runs against moto (no real AWS) through the conftest fixtures api_env, aws,
make_claims, make_event and call. Owner isolation is the main thing under test: every
Reports key is built from the token's sub, so another user's report ID must answer 404.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "api" / "schemas"

REPORTS_TABLE = "mofongo-test-reports"
MATCHES_TABLE = "mofongo-test-matches"
ITEMS_TABLE = "mofongo-test-items"
USERS_TABLE = "mofongo-test-users"
TOPIC_ARN = "arn:aws:sns:us-east-2:123456789012:mofongo-test-alerts"

OWNER_EMAIL = "owner@example.com"

VALID_BODY = {
    "category": "phone",
    "colors": ["black", "blue"],
    "description": "Black phone with a blue case and a cracked corner.",
    "lostLocation": "Library, second floor",
    "lostAt": "2026-01-15T14:30:00Z",
}


# ---------------------------------------------------------------- fixtures and helpers

def _resolve(request, name):
    """A conftest helper, whether it was written as a fixture or as a plain function."""
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        import conftest

        return getattr(conftest, name)


class Ctx:
    """Small wrapper so the tests read the same however conftest exposes its helpers."""

    def __init__(self, aws, make_claims, make_event, call):
        self.aws = aws
        self._make_claims = make_claims
        self._make_event = make_event
        self._call = call

    # tables
    def table(self, name):
        return self.aws.ddb.Table(name)

    @property
    def reports(self):
        return self.table(REPORTS_TABLE)

    @property
    def matches(self):
        return self.table(MATCHES_TABLE)

    @property
    def items(self):
        return self.table(ITEMS_TABLE)

    @property
    def users(self):
        return self.table(USERS_TABLE)

    # callers
    def claims(self, sub=None, **kwargs):
        return self._make_claims(sub=sub or str(uuid.uuid4()), **kwargs)

    def send(self, method, resource, *, claims, path=None, query=None, body=None, content_type="application/json"):
        event = self._make_event(method, resource, path=path, query=query, body=body, claims=claims)
        # make_event may or may not add a Content-Type. The handler requires one on a body.
        headers = dict(event.get("headers") or {})
        if content_type is None:
            headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        elif not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = content_type
        else:
            headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
            headers["Content-Type"] = content_type
        event["headers"] = headers
        return self._call(event)

    def create(self, claims, body=None, **kwargs):
        return self.send("POST", "/reports", claims=claims, body=VALID_BODY if body is None else body, **kwargs)

    def list(self, claims, query=None):
        return self.send("GET", "/reports", claims=claims, query=query)

    def get(self, claims, report_id):
        return self.send("GET", "/reports/{reportId}", claims=claims, path={"reportId": report_id})

    def close(self, claims, report_id):
        return self.send("POST", "/reports/{reportId}/closed", claims=claims, path={"reportId": report_id})

    # seeding
    def seed_report(self, owner, *, created_at="2026-02-01T10:00:00.000Z", status="OPEN", report_id=None, **extra):
        row = {
            "ownerId": owner,
            "reportId": report_id or str(uuid.uuid4()),
            "category": "keys",
            "colors": ["gray"],
            "description": "Seeded report.",
            "status": status,
            "createdAt": created_at,
        }
        if status == "OPEN":
            row["openCategory"] = row["category"]
        row.update(extra)
        self.reports.put_item(Item=row)
        return row

    def seed_item(self, *, finder="f" * 8 + "-0000-4000-8000-" + "0" * 12, category="phone", **extra):
        row = {
            "itemId": str(uuid.uuid4()),
            "finderId": finder,
            "title": "Found phone",
            "category": category,
            "colors": ["black"],
            "foundLocation": "Student center",
            "foundAt": "2026-02-02T09:00:00.000Z",
            "createdAt": "2026-02-02T09:05:00.000Z",
            "status": "LISTED",
            "tagStatus": "PENDING",
            "listedPk": "LISTED",
            "listedCategory": category,
        }
        row.update(extra)
        self.items.put_item(Item=row)
        return row

    def seed_match(self, report_id, item_id, *, score=80, created_at="2026-02-03T08:00:00.000Z", why=None):
        row = {
            "reportId": report_id,
            "itemId": item_id,
            "score": score,
            "why": why or ["same category", "same color"],
            "createdAt": created_at,
            "notifiedAt": "2026-02-03T08:01:00.000Z",
            "scoreParts": {"category": 50, "color": 30},
        }
        self.matches.put_item(Item=row)
        return row


@pytest.fixture
def ctx(request, api_env, aws, monkeypatch):
    """The test context. Points the validator at the repo schemas and drops cached clients.

    The handler caches boto3 clients and settings for the life of a Lambda environment. Here
    each test has its own moto state, so those caches are cleared once the mock is active.
    """
    monkeypatch.setenv("SCHEMA_DIR", str(SCHEMA_DIR))
    import aws as aws_module  # the handler's module, not the fixture
    import config

    config.get_settings.cache_clear()
    for factory in (aws_module.dynamodb_resource, aws_module.s3_client, aws_module.sns_client):
        factory.cache_clear()

    yield Ctx(
        aws,
        _resolve(request, "make_claims"),
        _resolve(request, "make_event"),
        _resolve(request, "call"),
    )

    for factory in (aws_module.dynamodb_resource, aws_module.s3_client, aws_module.sns_client):
        factory.cache_clear()
    config.get_settings.cache_clear()


@pytest.fixture
def owner(ctx):
    return ctx.claims()


def sub_of(claims):
    return claims["sub"]


def topic_subscriptions(ctx):
    return ctx.aws.sns.list_subscriptions_by_topic(TopicArn=TOPIC_ARN)["Subscriptions"]


# ---------------------------------------------------------------- createReport

class TestCreateReport:
    def test_valid_body_returns_201_and_the_report(self, ctx, owner):
        status, body, headers = ctx.create(owner)

        assert status == 201
        report = body["report"]
        assert uuid.UUID(report["reportId"]).version == 4
        assert report["category"] == "phone"
        assert report["colors"] == ["black", "blue"]
        assert report["description"] == VALID_BODY["description"]
        assert report["lostLocation"] == "Library, second floor"
        assert report["lostAt"] == "2026-01-15T14:30:00.000Z"
        assert report["status"] == "OPEN"
        assert report["createdAt"].endswith("Z")
        assert headers["Cache-Control"] == "no-store"
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

    def test_response_never_carries_owner_or_internal_fields(self, ctx, owner):
        _, body, _ = ctx.create(owner)

        assert set(body["report"]) <= {
            "reportId", "category", "colors", "description", "status",
            "createdAt", "lostLocation", "lostAt", "closedAt",
        }
        assert sub_of(owner) not in json.dumps(body)

    def test_writes_a_row_keyed_by_owner_and_report_id(self, ctx, owner):
        _, body, _ = ctx.create(owner)
        report_id = body["report"]["reportId"]

        row = ctx.reports.get_item(Key={"ownerId": sub_of(owner), "reportId": report_id})["Item"]
        assert row["ownerId"] == sub_of(owner)
        assert row["reportId"] == report_id
        assert row["status"] == "OPEN"
        assert row["category"] == "phone"
        assert row["openCategory"] == "phone"  # puts it in the OpenByCategory index
        assert row["lostAt"] == "2026-01-15T14:30:00.000Z"  # normalised to UTC with milliseconds
        assert ctx.reports.scan()["Count"] == 1

    def test_optional_fields_can_be_left_out(self, ctx, owner):
        minimal = {"category": "keys", "colors": ["gray"], "description": "Car key on a red lanyard."}
        status, body, _ = ctx.create(owner, minimal)

        assert status == 201
        assert "lostLocation" not in body["report"]
        assert "lostAt" not in body["report"]

    def test_lost_at_with_an_offset_is_stored_in_utc(self, ctx, owner):
        body_in = {**VALID_BODY, "lostAt": "2026-01-15T10:30:00-05:00"}
        status, body, _ = ctx.create(owner, body_in)

        assert status == 201
        assert body["report"]["lostAt"] == "2026-01-15T15:30:00.000Z"

    def test_owner_comes_from_the_token_not_the_body(self, ctx, owner):
        other = ctx.claims()
        status, body, _ = ctx.create(owner, {**VALID_BODY, "ownerId": sub_of(other)})

        assert status == 400
        assert any(d["field"] == "ownerId" for d in body["details"])
        assert ctx.reports.scan()["Count"] == 0

    def test_two_creates_make_two_distinct_reports(self, ctx, owner):
        _, first, _ = ctx.create(owner)
        _, second, _ = ctx.create(owner)

        assert first["report"]["reportId"] != second["report"]["reportId"]
        assert ctx.reports.scan()["Count"] == 2

    # -- email alerts

    def test_subscribes_the_verified_email_to_the_alerts_topic(self, ctx, owner):
        status, body, _ = ctx.create(owner)

        assert status == 201
        assert body["alerts"] == "started"
        subs = topic_subscriptions(ctx)
        assert len(subs) == 1
        assert subs[0]["Protocol"] == "email"
        assert subs[0]["Endpoint"] == OWNER_EMAIL
        assert subs[0]["TopicArn"] == TOPIC_ARN

    def test_subscription_is_filtered_to_the_callers_user_id(self, ctx, owner):
        ctx.create(owner)

        saved = ctx.users.get_item(Key={"userId": sub_of(owner)})["Item"]
        attributes = ctx.aws.sns.get_subscription_attributes(SubscriptionArn=saved["subscriptionArn"])["Attributes"]
        assert json.loads(attributes["FilterPolicy"]) == {"ownerId": [sub_of(owner)]}
        assert attributes["Endpoint"] == OWNER_EMAIL

    def test_second_report_does_not_subscribe_again(self, ctx, owner):
        _, first, _ = ctx.create(owner)
        _, second, _ = ctx.create(owner)

        assert first["alerts"] == "started"
        assert second["alerts"] == "existing"
        assert len(topic_subscriptions(ctx)) == 1

    def test_each_user_gets_their_own_subscription(self, ctx, owner):
        other = ctx.claims(email="other@example.com")
        ctx.create(owner)
        ctx.create(other)

        endpoints = sorted(s["Endpoint"] for s in topic_subscriptions(ctx))
        assert endpoints == ["other@example.com", OWNER_EMAIL]

    def test_unverified_email_creates_the_report_but_no_subscription(self, ctx):
        caller = ctx.claims(email_verified="false")
        status, body, _ = ctx.create(caller)

        assert status == 201
        assert body["alerts"] == "no-verified-email"
        assert topic_subscriptions(ctx) == []
        assert ctx.reports.scan()["Count"] == 1

    def test_sns_failure_never_fails_the_report(self, ctx, owner, monkeypatch):
        import alerts

        def boom():
            raise RuntimeError("sns is down")

        monkeypatch.setattr(alerts, "sns_client", boom)
        status, body, _ = ctx.create(owner)

        assert status == 201
        assert body["alerts"] == "unavailable"
        assert ctx.reports.scan()["Count"] == 1

    # -- validation

    @pytest.mark.parametrize(
        "field",
        ["category", "colors", "description"],
    )
    def test_missing_required_field_is_400(self, ctx, owner, field):
        bad = {k: v for k, v in VALID_BODY.items() if k != field}
        status, body, _ = ctx.create(owner, bad)

        assert status == 400
        assert body["message"] == "The request is not valid."
        assert {"field": field, "issue": "This field is required."} in body["details"]
        assert ctx.reports.scan()["Count"] == 0

    @pytest.mark.parametrize(
        "change",
        [
            {"category": "spaceship"},
            {"category": 7},
            {"colors": []},
            {"colors": ["black", "white", "gray", "red"]},
            {"colors": ["black", "black"]},
            {"colors": ["plaid"]},
            {"colors": "black"},
            {"description": ""},
            {"description": "   "},
            {"description": "x" * 1001},
            {"lostLocation": ""},
            {"lostAt": "yesterday"},
            {"lostAt": "2026-01-15T14:30:00"},  # no Z or offset
            {"status": "CLOSED"},
            {"reportId": str(uuid.uuid4())},
            {"surprise": "field"},
        ],
        ids=lambda c: next(iter(c)) + "=" + str(next(iter(c.values())))[:12],
    )
    def test_body_failing_the_schema_is_400_and_writes_nothing(self, ctx, owner, change):
        status, body, _ = ctx.create(owner, {**VALID_BODY, **change})

        assert status == 400
        assert body["message"] == "The request is not valid."
        assert body["details"]
        assert ctx.reports.scan()["Count"] == 0
        assert topic_subscriptions(ctx) == []

    def test_error_details_do_not_echo_request_values(self, ctx, owner):
        secret = "do-not-echo-this-value"
        _, body, _ = ctx.create(owner, {**VALID_BODY, "category": secret})

        assert secret not in json.dumps(body)

    def test_future_lost_at_is_400(self, ctx, owner):
        status, body, _ = ctx.create(owner, {**VALID_BODY, "lostAt": "2999-01-01T00:00:00Z"})

        assert status == 400
        assert {"field": "lostAt", "issue": "Must not be in the future."} in body["details"]
        assert ctx.reports.scan()["Count"] == 0

    def test_missing_body_is_400(self, ctx, owner):
        status, body, _ = ctx.send("POST", "/reports", claims=owner, body=None)

        assert status == 400
        assert body["details"][0]["field"] == "body"

    def test_malformed_json_is_400(self, ctx, owner):
        event = ctx._make_event("POST", "/reports", claims=owner)
        event["body"] = "{not json"
        event["headers"] = {"Content-Type": "application/json"}
        status, body, _ = ctx._call(event)

        assert status == 400
        assert body["details"][0]["issue"] == "The body is not valid JSON."

    def test_wrong_content_type_is_400(self, ctx, owner):
        status, body, _ = ctx.create(owner, content_type="text/plain")

        assert status == 400
        assert body["details"][0]["field"] == "Content-Type"
        assert ctx.reports.scan()["Count"] == 0

    def test_oversized_body_is_413(self, ctx, owner):
        padded = {**VALID_BODY, "description": "x" * 40000}
        status, _, _ = ctx.create(owner, padded)

        assert status == 413
        assert ctx.reports.scan()["Count"] == 0

    def test_schema_file_used_by_the_tests_is_the_real_one(self):
        schema = json.loads((SCHEMA_DIR / "requests" / "create-report.json").read_text(encoding="utf-8"))
        assert set(schema["required"]) == {"category", "colors", "description"}
        assert schema["additionalProperties"] is False

    # -- auth

    def test_no_claims_is_401(self, ctx):
        status, body, _ = ctx.send("POST", "/reports", claims=None, body=VALID_BODY)

        assert status == 401
        assert body == {"message": "Unauthorized"}
        assert ctx.reports.scan()["Count"] == 0

    def test_access_token_instead_of_id_token_is_401(self, ctx):
        caller = ctx.claims(token_use="access")
        status, _, _ = ctx.create(caller)

        assert status == 401
        assert ctx.reports.scan()["Count"] == 0


# ---------------------------------------------------------------- listReports

class TestListReports:
    def test_empty_list_for_a_new_user(self, ctx, owner):
        status, body, _ = ctx.list(owner)

        assert status == 200
        assert body == {"reports": []}

    def test_returns_only_the_callers_reports(self, ctx, owner):
        other = ctx.claims()
        mine = ctx.seed_report(sub_of(owner))
        theirs = ctx.seed_report(sub_of(other))

        _, body, _ = ctx.list(owner)
        ids = [r["reportId"] for r in body["reports"]]
        assert ids == [mine["reportId"]]
        assert theirs["reportId"] not in json.dumps(body)

        _, other_body, _ = ctx.list(other)
        assert [r["reportId"] for r in other_body["reports"]] == [theirs["reportId"]]

    def test_newest_first(self, ctx, owner):
        old = ctx.seed_report(sub_of(owner), created_at="2026-01-01T00:00:00.000Z")
        newest = ctx.seed_report(sub_of(owner), created_at="2026-03-01T00:00:00.000Z")
        middle = ctx.seed_report(sub_of(owner), created_at="2026-02-01T00:00:00.000Z")

        _, body, _ = ctx.list(owner)

        assert [r["reportId"] for r in body["reports"]] == [
            newest["reportId"], middle["reportId"], old["reportId"],
        ]

    def test_reports_made_through_the_api_are_listed(self, ctx, owner):
        _, created, _ = ctx.create(owner)

        _, body, _ = ctx.list(owner)

        assert [r["reportId"] for r in body["reports"]] == [created["report"]["reportId"]]

    def test_closed_reports_are_still_listed(self, ctx, owner):
        open_report = ctx.seed_report(sub_of(owner), created_at="2026-01-01T00:00:00.000Z")
        closed = ctx.seed_report(
            sub_of(owner), created_at="2026-02-01T00:00:00.000Z", status="CLOSED",
            closedAt="2026-02-05T00:00:00.000Z",
        )

        _, body, _ = ctx.list(owner)

        by_id = {r["reportId"]: r for r in body["reports"]}
        assert by_id[open_report["reportId"]]["status"] == "OPEN"
        assert by_id[closed["reportId"]]["status"] == "CLOSED"
        assert by_id[closed["reportId"]]["closedAt"] == "2026-02-05T00:00:00.000Z"

    def test_rows_are_shaped_by_the_allowlist(self, ctx, owner):
        ctx.seed_report(sub_of(owner), lostLocation="Gym", internalNote="secret")

        _, body, _ = ctx.list(owner)

        row = body["reports"][0]
        assert row["lostLocation"] == "Gym"
        assert "ownerId" not in row
        assert "openCategory" not in row
        assert "internalNote" not in row
        assert sub_of(owner) not in json.dumps(body)

    def test_pagination_walks_all_pages_without_overlap(self, ctx, owner):
        seeded = [
            ctx.seed_report(sub_of(owner), created_at=f"2026-02-0{n}T00:00:00.000Z") for n in range(1, 6)
        ]
        expected = [r["reportId"] for r in reversed(seeded)]

        seen, token = [], None
        for _ in range(10):  # safety bound
            query = {"limit": "2"} if token is None else {"limit": "2", "nextToken": token}
            status, body, _ = ctx.list(owner, query)
            assert status == 200
            assert len(body["reports"]) <= 2
            seen += [r["reportId"] for r in body["reports"]]
            token = body.get("nextToken")
            if not token:
                break

        assert seen == expected

    def test_next_token_from_another_user_is_rejected(self, ctx, owner):
        other = ctx.claims()
        for n in range(1, 4):
            ctx.seed_report(sub_of(other), created_at=f"2026-02-0{n}T00:00:00.000Z")
        _, page, _ = ctx.list(other, {"limit": "1"})
        token = page["nextToken"]

        status, body, _ = ctx.list(owner, {"limit": "1", "nextToken": token})

        assert status == 400
        assert body["details"] == [{"field": "nextToken", "issue": "This token is not valid."}]

    @pytest.mark.parametrize("limit", ["0", "51", "-1", "abc", "1.5"])
    def test_bad_limit_is_400(self, ctx, owner, limit):
        status, body, _ = ctx.list(owner, {"limit": limit})

        assert status == 400
        assert body["details"][0]["field"] == "limit"

    def test_garbage_next_token_is_400(self, ctx, owner):
        status, _, _ = ctx.list(owner, {"nextToken": "not-a-real-token"})

        assert status == 400

    def test_no_claims_is_401(self, ctx):
        status, _, _ = ctx.send("GET", "/reports", claims=None)

        assert status == 401


# ---------------------------------------------------------------- getReport

class TestGetReport:
    def test_owner_gets_the_report_with_empty_matches(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner), lostLocation="Cafeteria")

        status, body, _ = ctx.get(owner, report["reportId"])

        assert status == 200
        assert body["report"]["reportId"] == report["reportId"]
        assert body["report"]["lostLocation"] == "Cafeteria"
        assert body["report"]["status"] == "OPEN"
        assert body["matches"] == []
        assert "ownerId" not in body["report"]

    def test_owner_gets_matches_with_item_summaries(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner), category="phone")
        item = ctx.seed_item()
        ctx.seed_match(report["reportId"], item["itemId"], score=85, why=["same category"])

        status, body, _ = ctx.get(owner, report["reportId"])

        assert status == 200
        assert len(body["matches"]) == 1
        match = body["matches"][0]
        assert match["score"] == 85
        assert match["why"] == ["same category"]
        assert match["createdAt"] == "2026-02-03T08:00:00.000Z"
        assert match["item"]["itemId"] == item["itemId"]
        assert match["item"]["title"] == "Found phone"
        assert match["item"]["isMine"] is False
        assert "url" in match["item"]["photo"]

    def test_match_does_not_leak_finder_or_internal_fields(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        finder = str(uuid.uuid4())
        item = ctx.seed_item(finder=finder, photoKey="photos/secret.jpg")
        ctx.seed_match(report["reportId"], item["itemId"])

        _, body, _ = ctx.get(owner, report["reportId"])

        text = json.dumps(body)
        assert finder not in text
        assert "finderId" not in text
        assert "scoreParts" not in text
        assert "notifiedAt" not in text
        assert "photoKey" not in text
        assert "listedPk" not in text

    def test_wallet_id_match_still_gets_a_photo_link(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner), category="wallet-id")
        item = ctx.seed_item(category="wallet-id")
        ctx.seed_match(report["reportId"], item["itemId"])

        _, body, _ = ctx.get(owner, report["reportId"])

        assert "url" in body["matches"][0]["item"]["photo"]

    def test_matches_are_sorted_by_score_then_newest(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        low = ctx.seed_item(title="low")
        high = ctx.seed_item(title="high")
        tie_old = ctx.seed_item(title="tie-old")
        tie_new = ctx.seed_item(title="tie-new")
        ctx.seed_match(report["reportId"], low["itemId"], score=10)
        ctx.seed_match(report["reportId"], high["itemId"], score=90)
        ctx.seed_match(report["reportId"], tie_old["itemId"], score=50, created_at="2026-02-03T00:00:00.000Z")
        ctx.seed_match(report["reportId"], tie_new["itemId"], score=50, created_at="2026-02-04T00:00:00.000Z")

        _, body, _ = ctx.get(owner, report["reportId"])

        assert [m["item"]["title"] for m in body["matches"]] == ["high", "tie-new", "tie-old", "low"]

    def test_matches_for_other_reports_are_not_mixed_in(self, ctx, owner):
        mine = ctx.seed_report(sub_of(owner))
        also_mine = ctx.seed_report(sub_of(owner))
        item_a = ctx.seed_item(title="for-first")
        item_b = ctx.seed_item(title="for-second")
        ctx.seed_match(mine["reportId"], item_a["itemId"])
        ctx.seed_match(also_mine["reportId"], item_b["itemId"])

        _, body, _ = ctx.get(owner, mine["reportId"])

        assert [m["item"]["title"] for m in body["matches"]] == ["for-first"]

    def test_match_whose_item_is_gone_is_skipped(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        kept = ctx.seed_item(title="kept")
        ctx.seed_match(report["reportId"], kept["itemId"])
        ctx.seed_match(report["reportId"], str(uuid.uuid4()))  # item deleted

        status, body, _ = ctx.get(owner, report["reportId"])

        assert status == 200
        assert [m["item"]["title"] for m in body["matches"]] == ["kept"]

    def test_closed_report_can_still_be_read(self, ctx, owner):
        report = ctx.seed_report(
            sub_of(owner), status="CLOSED", closedAt="2026-02-05T00:00:00.000Z"
        )

        status, body, _ = ctx.get(owner, report["reportId"])

        assert status == 200
        assert body["report"]["status"] == "CLOSED"
        assert body["report"]["closedAt"] == "2026-02-05T00:00:00.000Z"

    def test_different_owner_gets_404_and_never_sees_the_matches(self, ctx, owner):
        other = ctx.claims()
        report = ctx.seed_report(sub_of(owner))
        item = ctx.seed_item(title="secret-match")
        ctx.seed_match(report["reportId"], item["itemId"])

        status, body, _ = ctx.get(other, report["reportId"])

        assert status == 404
        assert body == {"message": "Report not found."}
        assert "secret-match" not in json.dumps(body)

    def test_not_owner_and_not_found_look_identical(self, ctx, owner):
        other = ctx.claims()
        report = ctx.seed_report(sub_of(owner))

        foreign = ctx.get(other, report["reportId"])
        unknown = ctx.get(other, str(uuid.uuid4()))

        assert foreign[0] == unknown[0] == 404
        assert foreign[1] == unknown[1]

    def test_unknown_id_is_404(self, ctx, owner):
        status, body, _ = ctx.get(owner, str(uuid.uuid4()))

        assert status == 404
        assert body == {"message": "Report not found."}

    @pytest.mark.parametrize(
        "bad_id",
        ["not-a-uuid", "12345", str(uuid.uuid4()).upper(), "../" + str(uuid.uuid4()), ""],
    )
    def test_malformed_id_is_400(self, ctx, owner, bad_id):
        status, body, _ = ctx.get(owner, bad_id)

        assert status == 400
        assert body["details"][0]["field"] == "reportId"

    def test_missing_path_parameters_is_400(self, ctx, owner):
        status, _, _ = ctx.send("GET", "/reports/{reportId}", claims=owner, path=None)

        assert status == 400

    def test_no_claims_is_401(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))

        status, _, _ = ctx.send(
            "GET", "/reports/{reportId}", claims=None, path={"reportId": report["reportId"]}
        )

        assert status == 401


# ---------------------------------------------------------------- closeReport

class TestCloseReport:
    def test_owner_closes_an_open_report(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))

        status, body, _ = ctx.close(owner, report["reportId"])

        assert status == 200
        assert body["reportId"] == report["reportId"]
        assert body["status"] == "CLOSED"
        assert body["closedAt"].endswith("Z")
        assert "ownerId" not in body

    def test_close_updates_the_stored_row(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner), category="bag")

        ctx.close(owner, report["reportId"])

        row = ctx.reports.get_item(
            Key={"ownerId": sub_of(owner), "reportId": report["reportId"]}, ConsistentRead=True
        )["Item"]
        assert row["status"] == "CLOSED"
        assert row["closedAt"].endswith("Z")
        assert "openCategory" not in row  # leaves the OpenByCategory index
        assert row["category"] == "bag"  # everything else is kept
        assert row["description"] == report["description"]

    def test_closed_state_shows_in_get_and_list(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        ctx.close(owner, report["reportId"])

        _, got, _ = ctx.get(owner, report["reportId"])
        _, listed, _ = ctx.list(owner)

        assert got["report"]["status"] == "CLOSED"
        assert listed["reports"][0]["status"] == "CLOSED"

    def test_closing_leaves_matches_readable(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        item = ctx.seed_item()
        ctx.seed_match(report["reportId"], item["itemId"])

        ctx.close(owner, report["reportId"])
        _, body, _ = ctx.get(owner, report["reportId"])

        assert len(body["matches"]) == 1

    def test_only_the_named_report_is_closed(self, ctx, owner):
        target = ctx.seed_report(sub_of(owner))
        bystander = ctx.seed_report(sub_of(owner))

        ctx.close(owner, target["reportId"])

        _, body, _ = ctx.get(owner, bystander["reportId"])
        assert body["report"]["status"] == "OPEN"

    def test_closing_twice_is_409(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        first, _, _ = ctx.close(owner, report["reportId"])

        status, body, _ = ctx.close(owner, report["reportId"])

        assert first == 200
        assert status == 409
        assert body == {"message": "This report is already closed."}

    def test_second_close_keeps_the_first_closed_time(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))
        _, first, _ = ctx.close(owner, report["reportId"])

        ctx.close(owner, report["reportId"])

        row = ctx.reports.get_item(Key={"ownerId": sub_of(owner), "reportId": report["reportId"]})["Item"]
        assert row["closedAt"] == first["closedAt"]

    def test_non_owner_gets_404_and_the_report_stays_open(self, ctx, owner):
        other = ctx.claims()
        report = ctx.seed_report(sub_of(owner))

        status, body, _ = ctx.close(other, report["reportId"])

        assert status == 404  # never 403: someone else's ID looks like an unknown ID
        assert body == {"message": "Report not found."}
        row = ctx.reports.get_item(
            Key={"ownerId": sub_of(owner), "reportId": report["reportId"]}, ConsistentRead=True
        )["Item"]
        assert row["status"] == "OPEN"
        assert row["openCategory"] == report["openCategory"]
        assert "closedAt" not in row

    def test_non_owner_close_creates_no_row_under_their_own_id(self, ctx, owner):
        other = ctx.claims()
        report = ctx.seed_report(sub_of(owner))

        ctx.close(other, report["reportId"])

        assert ctx.reports.get_item(Key={"ownerId": sub_of(other), "reportId": report["reportId"]}).get("Item") is None
        assert ctx.reports.scan()["Count"] == 1

    def test_unknown_id_is_404_and_creates_nothing(self, ctx, owner):
        status, body, _ = ctx.close(owner, str(uuid.uuid4()))

        assert status == 404
        assert body == {"message": "Report not found."}
        assert ctx.reports.scan()["Count"] == 0

    def test_malformed_id_is_400(self, ctx, owner):
        status, body, _ = ctx.close(owner, "not-a-uuid")

        assert status == 400
        assert body["details"][0]["field"] == "reportId"

    def test_no_claims_is_401(self, ctx, owner):
        report = ctx.seed_report(sub_of(owner))

        status, _, _ = ctx.send(
            "POST", "/reports/{reportId}/closed", claims=None, path={"reportId": report["reportId"]}
        )

        assert status == 401
        row = ctx.reports.get_item(Key={"ownerId": sub_of(owner), "reportId": report["reportId"]})["Item"]
        assert row["status"] == "OPEN"


# ---------------------------------------------------------------- whole flow

def test_create_list_get_close_flow(ctx, owner):
    status, created, _ = ctx.create(owner)
    assert status == 201
    report_id = created["report"]["reportId"]

    _, listed, _ = ctx.list(owner)
    assert [r["reportId"] for r in listed["reports"]] == [report_id]

    item = ctx.seed_item()
    ctx.seed_match(report_id, item["itemId"])
    _, got, _ = ctx.get(owner, report_id)
    assert got["report"]["status"] == "OPEN"
    assert [m["item"]["itemId"] for m in got["matches"]] == [item["itemId"]]

    status, closed, _ = ctx.close(owner, report_id)
    assert status == 200
    assert closed["status"] == "CLOSED"

    _, after, _ = ctx.get(owner, report_id)
    assert after["report"]["status"] == "CLOSED"
