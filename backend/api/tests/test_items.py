"""Items operations through the Lambda handler, with moto standing in for AWS.

Covers listItems, createItem, getItem and markItemReturned (data-model AP1 to AP4, AP7).
Nothing here talks to real AWS: the `aws` fixture (conftest.py) runs inside mock_aws.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------- fixtures and helpers


@pytest.fixture
def api(make_claims, make_event, call):
    """The three conftest helper fixtures in one namespace."""
    return SimpleNamespace(make_claims=make_claims, make_event=make_event, call=call)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _hours_ago(hours: float) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(hours=hours))


def valid_body(**overrides) -> dict:
    """A body that passes api/schemas/requests/create-item.json."""
    body = {
        "title": "Black Samsung phone",
        "description": "Cracked corner, blue case, found on a bench.",
        "category": "phone",
        "colors": ["black", "blue"],
        "foundLocation": "Library, second floor",
        "foundAt": _hours_ago(2).replace(".000Z", "Z"),
    }
    body.update(overrides)
    return body


def post_item(api, body, claims=None, content_type="application/json"):
    """POST /items. The handler requires a JSON Content-Type header (make_event sets one)."""
    kwargs = {"body": body, "headers": {"Content-Type": content_type}}
    if claims is not None:
        kwargs["claims"] = claims
    return api.call(api.make_event("POST", "/items", **kwargs))


def seed_item(aws, *, finder, created_at, category="phone", status="LISTED", **extra) -> dict:
    """Write an Items row the way createItem would (or as returned, with the sparse keys gone)."""
    item_id = extra.pop("itemId", str(uuid.uuid4()))
    row = {
        "itemId": item_id,
        "finderId": finder,
        "title": f"Found {category}",
        "category": category,
        "colors": ["black"],
        "foundLocation": "Student center",
        "foundAt": created_at,
        "status": status,
        "photoKey": f"photos/{item_id}.jpg",
        "tagStatus": "PENDING",
        "createdAt": created_at,
    }
    if status == "LISTED":
        row["listedPk"] = "LISTED"
        row["listedCategory"] = category
    row.update(extra)
    aws.ddb.Table(os.environ["ITEMS_TABLE"]).put_item(Item=row)
    return row


def items_table(aws):
    return aws.ddb.Table(os.environ["ITEMS_TABLE"])


def stored(aws, item_id):
    return items_table(aws).get_item(Key={"itemId": item_id}, ConsistentRead=True).get("Item")


def list_items(api, query=None, claims=None):
    kwargs = {"query": query}
    if claims is not None:
        kwargs["claims"] = claims
    return api.call(api.make_event("GET", "/items", **kwargs))


def get_item(api, item_id, claims=None):
    kwargs = {"path": {"itemId": item_id}}
    if claims is not None:
        kwargs["claims"] = claims
    return api.call(api.make_event("GET", "/items/{itemId}", **kwargs))


def mark_returned(api, item_id, claims=None):
    kwargs = {"path": {"itemId": item_id}}
    if claims is not None:
        kwargs["claims"] = claims
    return api.call(api.make_event("POST", "/items/{itemId}/returned", **kwargs))


@pytest.fixture
def finder(api):
    return api.make_claims()


@pytest.fixture
def other(api):
    return api.make_claims(email="someone-else@example.com")


# ---------------------------------------------------------------- listItems


class TestListItems:
    def test_empty_table_returns_empty_list(self, aws, api, finder):
        status, body, _ = list_items(api, claims=finder)
        assert status == 200
        assert body == {"items": []}

    def test_requires_authentication(self, aws, api):
        status, body, _ = api.call(api.make_event("GET", "/items", claims=None))
        assert status == 401
        assert body == {"message": "Unauthorized"}

    def test_newest_first_with_summary_fields(self, aws, api, finder, other):
        oldest = seed_item(aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", category="keys")
        newest = seed_item(aws, finder=other["sub"], created_at="2026-10-03T09:00:00.000Z", category="bag")
        middle = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="glasses")

        status, body, headers = list_items(api, claims=finder)

        assert status == 200
        assert [i["itemId"] for i in body["items"]] == [newest["itemId"], middle["itemId"], oldest["itemId"]]
        first = body["items"][0]
        assert first["title"] == newest["title"]
        assert first["category"] == "bag"
        assert first["status"] == "LISTED"
        assert first["tagStatus"] == "PENDING"
        assert first["isMine"] is False  # caller is not the finder of the newest item
        assert body["items"][1]["isMine"] is True
        assert "nextToken" not in body
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        assert headers["Cache-Control"] == "no-store"

    def test_summary_never_leaks_private_fields(self, aws, api, finder, other):
        seed_item(aws, finder=other["sub"], created_at="2026-10-01T09:00:00.000Z", description="private note")
        _, body, _ = list_items(api, claims=finder)
        item = body["items"][0]
        for hidden in ("finderId", "photoKey", "listedPk", "listedCategory", "description"):
            assert hidden not in item
        assert other["sub"] not in str(body)

    def test_returned_items_are_not_listed(self, aws, api, finder):
        seed_item(aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", status="RETURNED")
        listed = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")
        _, body, _ = list_items(api, claims=finder)
        assert [i["itemId"] for i in body["items"]] == [listed["itemId"]]

    def test_category_filter(self, aws, api, finder):
        keys_old = seed_item(aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", category="keys")
        seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="phone")
        keys_new = seed_item(aws, finder=finder["sub"], created_at="2026-10-03T09:00:00.000Z", category="keys")

        status, body, _ = list_items(api, query={"category": "keys"}, claims=finder)

        assert status == 200
        assert [i["itemId"] for i in body["items"]] == [keys_new["itemId"], keys_old["itemId"]]
        assert {i["category"] for i in body["items"]} == {"keys"}

    def test_unknown_category_is_400(self, aws, api, finder):
        status, body, _ = list_items(api, query={"category": "spaceship"}, claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "category"

    @pytest.mark.parametrize("limit", ["0", "51", "abc", "-1", "1.5"])
    def test_bad_limit_is_400(self, aws, api, finder, limit):
        status, body, _ = list_items(api, query={"limit": limit}, claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "limit"

    def test_paging_with_limit_and_next_token(self, aws, api, finder):
        rows = [
            seed_item(aws, finder=finder["sub"], created_at=f"2026-10-0{day}T09:00:00.000Z")
            for day in range(1, 6)
        ]
        expected = [r["itemId"] for r in reversed(rows)]  # newest first

        status, page1, _ = list_items(api, query={"limit": "2"}, claims=finder)
        assert status == 200
        assert [i["itemId"] for i in page1["items"]] == expected[:2]
        assert isinstance(page1["nextToken"], str) and page1["nextToken"]

        _, page2, _ = list_items(api, query={"limit": "2", "nextToken": page1["nextToken"]}, claims=finder)
        assert [i["itemId"] for i in page2["items"]] == expected[2:4]
        assert page2["nextToken"]

        _, page3, _ = list_items(api, query={"limit": "2", "nextToken": page2["nextToken"]}, claims=finder)
        assert [i["itemId"] for i in page3["items"]] == expected[4:]

    def test_category_paging(self, aws, api, finder):
        keys = [
            seed_item(aws, finder=finder["sub"], created_at=f"2026-10-0{day}T09:00:00.000Z", category="keys")
            for day in range(1, 4)
        ]
        seed_item(aws, finder=finder["sub"], created_at="2026-10-09T09:00:00.000Z", category="bag")
        expected = [r["itemId"] for r in reversed(keys)]

        _, page1, _ = list_items(api, query={"category": "keys", "limit": "2"}, claims=finder)
        assert [i["itemId"] for i in page1["items"]] == expected[:2]
        _, page2, _ = list_items(
            api, query={"category": "keys", "limit": "2", "nextToken": page1["nextToken"]}, claims=finder
        )
        assert [i["itemId"] for i in page2["items"]] == expected[2:]

    def test_garbage_next_token_is_400(self, aws, api, finder):
        status, body, _ = list_items(api, query={"nextToken": "not-a-real-token"}, claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "nextToken"

    def test_next_token_from_another_query_is_400(self, aws, api, finder):
        for day in range(1, 4):
            seed_item(aws, finder=finder["sub"], created_at=f"2026-10-0{day}T09:00:00.000Z", category="keys")
        _, page1, _ = list_items(api, query={"category": "keys", "limit": "1"}, claims=finder)
        # A token minted for category=keys must not work on the plain listing.
        status, body, _ = list_items(api, query={"nextToken": page1["nextToken"]}, claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "nextToken"

    def test_wallet_id_photo_hidden_from_non_finder_shown_to_finder(self, aws, api, finder, other):
        wallet = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="wallet-id")
        phone = seed_item(aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", category="phone")

        _, as_other, _ = list_items(api, claims=other)
        by_id = {i["itemId"]: i for i in as_other["items"]}
        assert "photo" not in by_id[wallet["itemId"]]
        assert by_id[wallet["itemId"]]["isMine"] is False
        assert "photo" in by_id[phone["itemId"]]  # other categories are not hidden

        _, as_finder, _ = list_items(api, claims=finder)
        by_id = {i["itemId"]: i for i in as_finder["items"]}
        assert by_id[wallet["itemId"]]["isMine"] is True
        photo = by_id[wallet["itemId"]]["photo"]
        assert f"photos/{wallet['itemId']}.jpg" in photo["url"]
        assert "mofongo-test-photos" in photo["url"]
        assert photo["expiresAt"].endswith("Z")


# ---------------------------------------------------------------- createItem


class TestCreateItem:
    def test_valid_body_returns_201_with_item_and_upload_form(self, aws, api, finder):
        status, body, headers = post_item(api, valid_body(), claims=finder)

        assert status == 201
        item_id = body["itemId"]
        assert str(uuid.UUID(item_id)) == item_id

        item = body["item"]
        assert item["itemId"] == item_id
        assert item["title"] == "Black Samsung phone"
        assert item["description"] == "Cracked corner, blue case, found on a bench."
        assert item["category"] == "phone"
        assert item["colors"] == ["black", "blue"]
        assert item["foundLocation"] == "Library, second floor"
        assert item["status"] == "LISTED"
        assert item["tagStatus"] == "PENDING"
        assert item["isMine"] is True
        assert item["foundAt"].endswith("Z")
        assert "photo" not in item  # nothing uploaded yet
        for hidden in ("finderId", "photoKey", "listedPk", "listedCategory"):
            assert hidden not in item
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

        upload = body["upload"]
        assert upload["url"]
        assert upload["fields"]["key"] == f"photos/{item_id}.jpg"
        assert upload["fields"]["Content-Type"] == "image/jpeg"
        assert upload["expiresAt"].endswith("Z")

    def test_upload_form_is_scoped_to_one_object_and_one_type(self, aws, api, finder):
        import base64
        import json

        _, body, _ = post_item(api, valid_body(), claims=finder)
        fields = body["upload"]["fields"]
        # The signed policy is what limits the form to photos/<itemId>.jpg, JPEG, with a size cap.
        policy = json.loads(base64.b64decode(fields["policy"]))
        conditions = policy["conditions"]
        assert {"Content-Type": "image/jpeg"} in conditions
        assert ["content-length-range", 1, 10485760] in conditions
        assert {"key": f"photos/{body['itemId']}.jpg"} in conditions
        assert {"bucket": "mofongo-test-photos"} in conditions

    def test_writes_listed_row_with_pending_tag_status(self, aws, api, finder):
        _, body, _ = post_item(api, valid_body(), claims=finder)
        row = stored(aws, body["itemId"])

        assert row is not None
        assert row["listedPk"] == "LISTED"
        assert row["listedCategory"] == "phone"
        assert row["status"] == "LISTED"
        assert row["tagStatus"] == "PENDING"
        assert row["finderId"] == finder["sub"]
        assert row["photoKey"] == f"photos/{body['itemId']}.jpg"
        assert row["title"] == "Black Samsung phone"
        assert row["colors"] == ["black", "blue"]
        assert row["createdAt"].endswith("Z")

    def test_description_is_optional(self, aws, api, finder):
        body = valid_body()
        del body["description"]
        status, out, _ = post_item(api, body, claims=finder)
        assert status == 201
        assert "description" not in out["item"]
        assert "description" not in stored(aws, out["itemId"])

    def test_new_item_shows_up_in_listing(self, aws, api, finder, other):
        _, created, _ = post_item(api, valid_body(), claims=finder)
        status, listing, _ = list_items(api, claims=other)
        assert status == 200
        assert [i["itemId"] for i in listing["items"]] == [created["itemId"]]
        assert listing["items"][0]["isMine"] is False

    def test_foundat_with_offset_is_stored_as_utc(self, aws, api, finder):
        local = (datetime.now(timezone(timedelta(hours=-5))) - timedelta(hours=3)).replace(microsecond=0)
        found_at = local.strftime("%Y-%m-%dT%H:%M:%S%z")
        found_at = found_at[:-2] + ":" + found_at[-2:]  # -0500 -> -05:00
        status, out, _ = post_item(api, valid_body(foundAt=found_at), claims=finder)
        assert status == 201
        assert stored(aws, out["itemId"])["foundAt"] == _iso(local)

    def test_finder_comes_from_token_not_body(self, aws, api, finder, other):
        status, body, _ = post_item(api, valid_body(finderId=other["sub"]), claims=finder)
        assert status == 400  # the schema refuses extra fields
        assert {"field": "finderId", "issue": "This field is not allowed."} in body["details"]
        assert items_table(aws).scan()["Count"] == 0

    @pytest.mark.parametrize(
        "mutation, field",
        [
            (lambda b: b.pop("title"), "title"),
            (lambda b: b.pop("colors"), "colors"),
            (lambda b: b.pop("foundAt"), "foundAt"),
            (lambda b: b.update(title="   "), "title"),
            (lambda b: b.update(title="x" * 81), "title"),
            (lambda b: b.update(category="spaceship"), "category"),
            (lambda b: b.update(colors=[]), "colors"),
            (lambda b: b.update(colors=["black", "black"]), "colors"),
            (lambda b: b.update(colors=["black", "white", "gray", "red"]), "colors"),
            (lambda b: b.update(colors=["chartreuse"]), "colors[0]"),
            (lambda b: b.update(foundAt="yesterday-ish"), "foundAt"),
            (lambda b: b.update(status="RETURNED"), "status"),
            (lambda b: b.update(photoKey="photos/evil.jpg"), "photoKey"),
        ],
    )
    def test_body_that_fails_schema_is_400_and_writes_nothing(self, aws, api, finder, mutation, field):
        body = valid_body()
        mutation(body)
        status, out, _ = post_item(api, body, claims=finder)

        assert status == 400
        assert out["message"] == "The request is not valid."
        assert field in [d["field"] for d in out["details"]]
        assert items_table(aws).scan()["Count"] == 0

    def test_future_foundat_is_400(self, aws, api, finder):
        future = _iso(datetime.now(timezone.utc) + timedelta(days=2))
        status, out, _ = post_item(api, valid_body(foundAt=future), claims=finder)
        assert status == 400
        assert {"field": "foundAt", "issue": "Must not be in the future."} in out["details"]
        assert items_table(aws).scan()["Count"] == 0

    def test_body_not_json_is_400(self, aws, api, finder):
        status, out, _ = api.call(api.make_event("POST", "/items", claims=finder, raw_body="{not json"))
        assert status == 400
        assert out["details"] == [{"field": "body", "issue": "The body is not valid JSON."}]

    def test_missing_body_is_400(self, aws, api, finder):
        event = api.make_event("POST", "/items", claims=finder)
        event["body"] = None
        status, out, _ = api.call(event)
        assert status == 400
        assert out["details"] == [{"field": "body", "issue": "A JSON body is required."}]

    def test_wrong_content_type_is_400(self, aws, api, finder):
        status, out, _ = post_item(api, valid_body(), claims=finder, content_type="text/plain")
        assert status == 400
        assert out["details"][0]["field"] == "Content-Type"
        assert items_table(aws).scan()["Count"] == 0

    def test_oversized_body_is_413(self, aws, api, finder):
        status, out, _ = post_item(api, valid_body(description="x" * 40000), claims=finder)
        assert status == 413
        assert items_table(aws).scan()["Count"] == 0

    def test_requires_authentication(self, aws, api):
        status, _, _ = api.call(api.make_event("POST", "/items", body=valid_body(), claims=None))
        assert status == 401
        assert items_table(aws).scan()["Count"] == 0


# ---------------------------------------------------------------- getItem


class TestGetItem:
    def test_found_returns_full_detail_for_finder(self, aws, api, finder):
        row = seed_item(
            aws,
            finder=finder["sub"],
            created_at="2026-10-02T09:00:00.000Z",
            category="laptop-tablet",
            description="Silver laptop with stickers",
            colors=["gray", "multicolor"],
        )
        status, body, _ = get_item(api, row["itemId"], claims=finder)

        assert status == 200
        assert body["itemId"] == row["itemId"]
        assert body["title"] == row["title"]
        assert body["description"] == "Silver laptop with stickers"
        assert body["category"] == "laptop-tablet"
        assert body["colors"] == ["gray", "multicolor"]
        assert body["foundLocation"] == "Student center"
        assert body["foundAt"] == "2026-10-02T09:00:00.000Z"
        assert body["createdAt"] == "2026-10-02T09:00:00.000Z"
        assert body["status"] == "LISTED"
        assert body["tagStatus"] == "PENDING"
        assert body["isMine"] is True
        assert f"photos/{row['itemId']}.jpg" in body["photo"]["url"]
        for hidden in ("finderId", "photoKey", "listedPk", "listedCategory"):
            assert hidden not in body

    def test_is_mine_false_for_other_user_and_finder_id_not_leaked(self, aws, api, finder, other):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")
        status, body, _ = get_item(api, row["itemId"], claims=other)
        assert status == 200
        assert body["isMine"] is False
        assert finder["sub"] not in str(body)
        assert "photo" in body  # a phone photo is visible to everyone

    def test_unknown_id_is_404(self, aws, api, finder):
        status, body, _ = get_item(api, str(uuid.uuid4()), claims=finder)
        assert status == 404
        assert body == {"message": "Item not found."}

    @pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", str(uuid.uuid4()).upper()])
    def test_malformed_id_is_400(self, aws, api, finder, bad_id):
        status, body, _ = get_item(api, bad_id, claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "itemId"

    def test_requires_authentication(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")
        event = api.make_event("GET", "/items/{itemId}", path={"itemId": row["itemId"]}, claims=None)
        status, _, _ = api.call(event)
        assert status == 401

    def test_wallet_id_photo_hidden_from_non_finder(self, aws, api, finder, other):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="wallet-id")

        status, body, _ = get_item(api, row["itemId"], claims=other)
        assert status == 200
        assert "photo" not in body
        assert body["isMine"] is False
        assert body["category"] == "wallet-id"  # the item itself is still visible

    def test_wallet_id_photo_present_for_finder(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="wallet-id")

        status, body, _ = get_item(api, row["itemId"], claims=finder)
        assert status == 200
        assert body["isMine"] is True
        assert f"photos/{row['itemId']}.jpg" in body["photo"]["url"]

    def test_clip_tags_only_when_tagged_and_capped_at_three(self, aws, api, finder):
        clip = {
            "categories": [{"value": c, "score": s} for c, s in
                           [("phone", 90), ("laptop-tablet", 5), ("other", 3), ("bag", 1)]],
            "colors": [{"value": "black", "score": 80}],
        }
        tagged = seed_item(
            aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", tagStatus="TAGGED", clipTags=clip
        )
        pending = seed_item(
            aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", tagStatus="PENDING", clipTags=clip
        )

        _, body, _ = get_item(api, tagged["itemId"], claims=finder)
        assert body["tagStatus"] == "TAGGED"
        assert [e["value"] for e in body["clipTags"]["categories"]] == ["phone", "laptop-tablet", "other"]
        assert body["clipTags"]["categories"][0]["score"] == 90
        assert body["clipTags"]["colors"] == [{"value": "black", "score": 80}]

        _, body, _ = get_item(api, pending["itemId"], claims=finder)
        assert "clipTags" not in body

    def test_returned_item_shows_returned_at(self, aws, api, finder):
        row = seed_item(
            aws,
            finder=finder["sub"],
            created_at="2026-10-02T09:00:00.000Z",
            status="RETURNED",
            returnedAt="2026-10-03T12:00:00.000Z",
        )
        status, body, _ = get_item(api, row["itemId"], claims=finder)
        assert status == 200
        assert body["status"] == "RETURNED"
        assert body["returnedAt"] == "2026-10-03T12:00:00.000Z"

    def test_get_after_create_round_trip(self, aws, api, finder):
        _, created, _ = post_item(api, valid_body(), claims=finder)
        status, body, _ = get_item(api, created["itemId"], claims=finder)
        assert status == 200
        assert body["itemId"] == created["itemId"]
        assert body["title"] == created["item"]["title"]
        assert body["isMine"] is True


# ---------------------------------------------------------------- markItemReturned


class TestMarkItemReturned:
    def test_finder_marks_returned(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")

        status, body, _ = mark_returned(api, row["itemId"], claims=finder)

        assert status == 200
        assert body["itemId"] == row["itemId"]
        assert body["status"] == "RETURNED"
        assert body["isMine"] is True
        assert body["returnedAt"].endswith("Z")
        assert "finderId" not in body

    def test_updates_dynamodb_and_drops_sparse_index_keys(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")

        _, body, _ = mark_returned(api, row["itemId"], claims=finder)
        after = stored(aws, row["itemId"])

        assert after["status"] == "RETURNED"
        assert after["returnedAt"] == body["returnedAt"]
        assert "listedPk" not in after
        assert "listedCategory" not in after
        assert after["finderId"] == finder["sub"]  # ownership untouched
        assert after["title"] == row["title"]

    def test_returned_item_leaves_browse_listings(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", category="keys")
        stays = seed_item(aws, finder=finder["sub"], created_at="2026-10-01T09:00:00.000Z", category="keys")

        mark_returned(api, row["itemId"], claims=finder)

        _, all_items, _ = list_items(api, claims=finder)
        assert [i["itemId"] for i in all_items["items"]] == [stays["itemId"]]
        _, by_category, _ = list_items(api, query={"category": "keys"}, claims=finder)
        assert [i["itemId"] for i in by_category["items"]] == [stays["itemId"]]

    def test_different_user_is_403_and_row_unchanged(self, aws, api, finder, other):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")

        status, body, _ = mark_returned(api, row["itemId"], claims=other)

        assert status == 403
        assert body == {"message": "Only the finder can mark this item returned."}
        after = stored(aws, row["itemId"])
        assert after["status"] == "LISTED"
        assert after["listedPk"] == "LISTED"
        assert "returnedAt" not in after

    def test_unknown_id_is_404_and_creates_no_row(self, aws, api, finder):
        status, body, _ = mark_returned(api, str(uuid.uuid4()), claims=finder)
        assert status == 404
        assert body == {"message": "Item not found."}
        assert items_table(aws).scan()["Count"] == 0

    def test_already_returned_is_409(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")
        assert mark_returned(api, row["itemId"], claims=finder)[0] == 200

        status, body, _ = mark_returned(api, row["itemId"], claims=finder)

        assert status == 409
        assert body == {"message": "This item is already marked returned."}
        assert stored(aws, row["itemId"])["status"] == "RETURNED"

    def test_other_user_on_returned_item_is_403_not_409(self, aws, api, finder, other):
        # The finder check comes first, so a stranger learns nothing about the item's state.
        row = seed_item(
            aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z", status="RETURNED",
            returnedAt="2026-10-03T12:00:00.000Z",
        )
        status, _, _ = mark_returned(api, row["itemId"], claims=other)
        assert status == 403

    def test_malformed_id_is_400(self, aws, api, finder):
        status, body, _ = mark_returned(api, "not-a-uuid", claims=finder)
        assert status == 400
        assert body["details"][0]["field"] == "itemId"

    def test_requires_authentication(self, aws, api, finder):
        row = seed_item(aws, finder=finder["sub"], created_at="2026-10-02T09:00:00.000Z")
        event = api.make_event(
            "POST", "/items/{itemId}/returned", path={"itemId": row["itemId"]}, claims=None
        )
        status, _, _ = api.call(event)
        assert status == 401
        assert stored(aws, row["itemId"])["status"] == "LISTED"

    def test_create_then_return_end_to_end(self, aws, api, finder, other):
        _, created, _ = post_item(api, valid_body(), claims=finder)
        item_id = created["itemId"]

        assert mark_returned(api, item_id, claims=other)[0] == 403
        status, body, _ = mark_returned(api, item_id, claims=finder)
        assert status == 200 and body["status"] == "RETURNED"

        _, detail, _ = get_item(api, item_id, claims=other)
        assert detail["status"] == "RETURNED"
        assert detail["isMine"] is False
