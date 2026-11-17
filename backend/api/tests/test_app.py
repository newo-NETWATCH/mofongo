"""Handler-level tests for app.handler: routing, body limits, error envelope, headers, 401 first.

No real AWS. Tests that never reach the data layer do not request the `aws` fixture on
purpose, so any stray data access would fail instead of passing silently. Fixtures and
helpers (api_env, aws, make_claims, make_event, call) are fixtures from conftest.py.
"""

from __future__ import annotations

import base64
import json
import os

import pytest


MAX_BODY_BYTES = 32768
JSON_HEADERS = {"Content-Type": "application/json"}

# conftest.py provides these as fixtures (not importable functions). This autouse fixture binds the
# live ones to module-level names so the helpers below can call them.
make_claims = make_event = call = None


@pytest.fixture(autouse=True)
def _bind_helpers(make_claims, make_event, call):
    globals().update(make_claims=make_claims, make_event=make_event, call=call)


ALL_ROUTES = [
    ("GET", "/items"),
    ("POST", "/items"),
    ("GET", "/items/{itemId}"),
    ("POST", "/items/{itemId}/returned"),
    ("GET", "/reports"),
    ("POST", "/reports"),
    ("GET", "/reports/{reportId}"),
    ("POST", "/reports/{reportId}/closed"),
    ("GET", "/me/alerts"),
    ("POST", "/me/alerts"),
]


def _post_items(body, *, headers=None, base64_encoded=False):
    """A POST /items event with a raw string body, bypassing make_event's json.dumps."""
    event = make_event("POST", "/items", body=None, claims=make_claims())
    event["body"] = body
    event["headers"] = JSON_HEADERS if headers is None else headers
    event["isBase64Encoded"] = base64_encoded
    return event


def _assert_security_headers(headers):
    lowered = {k.lower(): v for k, v in headers.items()}
    assert lowered["access-control-allow-origin"] == os.environ["CORS_ORIGIN"]
    assert lowered["cache-control"] == "no-store"
    assert lowered["x-content-type-options"] == "nosniff"


def _assert_envelope(body, *, with_details=False):
    assert isinstance(body, dict)
    assert isinstance(body["message"], str) and body["message"]
    if with_details:
        assert isinstance(body["details"], list) and body["details"]
        for entry in body["details"]:
            assert set(entry) == {"field", "issue"}
            assert isinstance(entry["field"], str) and isinstance(entry["issue"], str)
    else:
        assert set(body) == {"message"}


# ---------------------------------------------------------------- routing


def test_routes_table_has_the_ten_operations():
    import app

    assert set(app.ROUTES) == set(ALL_ROUTES)


def test_unknown_path_is_404():
    status, body, _ = call(make_event("GET", "/nope"))
    assert status == 404
    assert body == {"message": "Not found."}


def test_known_path_with_unsupported_method_is_404():
    status, body, _ = call(make_event("DELETE", "/items"))
    assert status == 404
    _assert_envelope(body)


def test_resource_must_be_the_route_template_not_a_concrete_path():
    status, _, _ = call(make_event("GET", "/items/3f1c2a4e-0000-4000-8000-000000000000"))
    assert status == 404


def test_method_is_case_insensitive():
    import app

    seen = []
    original = app.ROUTES[("GET", "/me/alerts")]
    app.ROUTES[("GET", "/me/alerts")] = lambda event, caller: (seen.append(caller.sub) or (200, {"ok": True}))
    try:
        status, body, _ = call(make_event("get", "/me/alerts"))
    finally:
        app.ROUTES[("GET", "/me/alerts")] = original
    assert status == 200
    assert body == {"ok": True}
    assert len(seen) == 1


# ---------------------------------------------------------------- 401 before data access


@pytest.mark.parametrize("method,resource", ALL_ROUTES)
def test_no_authorizer_claims_is_401_on_every_route(method, resource):
    status, body, headers = call(make_event(method, resource, claims=None))
    assert status == 401
    assert body == {"message": "Unauthorized"}
    _assert_security_headers(headers)


def test_401_comes_before_routing_so_unknown_routes_do_not_leak_404():
    status, body, _ = call(make_event("GET", "/nope", claims=None))
    assert status == 401
    assert body == {"message": "Unauthorized"}


def test_401_happens_before_any_route_function_runs(monkeypatch):
    import app

    def must_not_run(event, caller):  # pragma: no cover - failing path
        raise AssertionError("route ran without authentication")

    for key in list(app.ROUTES):
        monkeypatch.setitem(app.ROUTES, key, must_not_run)

    for claims in (None, {}, make_claims(token_use="access")):
        status, body, _ = call(make_event("GET", "/items", claims=claims))
        assert status == 401
        assert body == {"message": "Unauthorized"}


def test_401_before_body_is_read():
    event = make_event("POST", "/items", claims=None)
    event["body"] = "x" * (MAX_BODY_BYTES + 1)
    status, body, _ = call(event)
    assert status == 401
    assert body == {"message": "Unauthorized"}


def test_401_with_no_authorizer_key_at_all():
    event = make_event("GET", "/items")
    event["requestContext"] = {}
    status, body, _ = call(event)
    assert status == 401
    assert body == {"message": "Unauthorized"}


# ---------------------------------------------------------------- body size and syntax


def test_body_over_limit_is_413():
    status, body, headers = call(_post_items("a" * (MAX_BODY_BYTES + 1)))
    assert status == 413
    assert body == {"message": "The request body is too large."}
    _assert_security_headers(headers)


def test_body_limit_counts_bytes_not_characters():
    # 16385 two-byte characters = 32770 bytes, but only 16385 characters.
    status, body, _ = call(_post_items("é" * 16385))
    assert status == 413
    assert body["message"] == "The request body is too large."


def test_body_exactly_at_limit_is_not_413():
    status, body, _ = call(_post_items("a" * MAX_BODY_BYTES))
    assert status == 400  # not JSON, but it got past the size check


def test_base64_body_over_limit_is_413():
    raw = b"a" * (MAX_BODY_BYTES + 1)
    status, body, _ = call(_post_items(base64.b64encode(raw).decode(), base64_encoded=True))
    assert status == 413
    assert body["message"] == "The request body is too large."


def test_base64_body_is_decoded_before_parsing():
    encoded = base64.b64encode(b"{not json").decode()
    status, body, _ = call(_post_items(encoded, base64_encoded=True))
    assert status == 400
    assert {"field": "body", "issue": "The body is not valid JSON."} in body["details"]


def test_invalid_base64_is_400():
    status, body, _ = call(_post_items("%%%not base64%%%", base64_encoded=True))
    assert status == 400
    assert body["details"] == [{"field": "body", "issue": "The body could not be read."}]


@pytest.mark.parametrize("bad", ["{not json", "", "{'a': 1}", '{"a": 1,}', "NaN", '{"a": Infinity}', "\ud800"])
def test_body_that_is_not_valid_json_is_400(bad):
    status, body, headers = call(_post_items(bad))
    assert status == 400
    assert body["message"] == "The request is not valid."
    assert body["details"]
    _assert_security_headers(headers)


def test_not_valid_json_detail_names_the_body_and_never_echoes_it():
    secret = "SECRET-MARKER-123"
    status, body, _ = call(_post_items("{" + secret))
    assert status == 400
    assert body["details"] == [{"field": "body", "issue": "The body is not valid JSON."}]
    assert secret not in json.dumps(body)


def test_missing_body_is_400_body_required():
    event = _post_items(None)
    status, body, _ = call(event)
    assert status == 400
    assert body["details"] == [{"field": "body", "issue": "A JSON body is required."}]


def test_wrong_content_type_is_400():
    status, body, _ = call(_post_items("{}", headers={"Content-Type": "text/plain"}))
    assert status == 400
    assert body["details"] == [{"field": "Content-Type", "issue": "Must be application/json."}]


def test_content_type_header_lookup_ignores_case_and_charset():
    # Payload format 1.0 headers are case-sensitive, so the code must look the name up ignoring case.
    # The Content-Type check passes, so the failure reported is the JSON syntax, not the header.
    status, body, _ = call(_post_items("not json", headers={"content-type": "Application/JSON; charset=utf-8"}))
    assert status == 400
    assert body["details"] == [{"field": "body", "issue": "The body is not valid JSON."}]


def test_schema_violation_lists_required_fields():
    # conftest points SCHEMA_DIR at <repo>/api/schemas, so the real create-item schema is used.
    status, body, _ = call(_post_items("{}"))
    assert status == 400
    _assert_envelope(body, with_details=True)
    assert all(d["issue"] == "This field is required." for d in body["details"])


# ---------------------------------------------------------------- error envelope


def test_error_envelope_for_404_has_message_only():
    status, body, _ = call(make_event("GET", "/nope"))
    assert status == 404
    _assert_envelope(body)


def test_error_envelope_for_400_has_message_and_details():
    status, body, _ = call(_post_items("{nope"))
    assert status == 400
    _assert_envelope(body, with_details=True)


def test_api_error_body_shape_and_limits():
    from errors import MAX_DETAILS, ApiError

    assert ApiError(404, "Not found.").body() == {"message": "Not found."}
    long = ApiError(400, "x" * 900, [{"field": "f" * 300, "issue": "i" * 900}] * (MAX_DETAILS + 20)).body()
    assert len(long["message"]) == 500
    assert len(long["details"]) == MAX_DETAILS
    assert len(long["details"][0]["field"]) == 100
    assert len(long["details"][0]["issue"]) == 300


def test_unhandled_error_is_500_with_fixed_message(monkeypatch):
    import app

    def boom(event, caller):
        raise RuntimeError("secret internal detail arn:aws:dynamodb:table/x")

    monkeypatch.setitem(app.ROUTES, ("GET", "/items"), boom)
    status, body, headers = call(make_event("GET", "/items"))
    assert status == 500
    assert body == {"message": "Something went wrong. Try again later."}
    assert "secret" not in json.dumps(body)
    _assert_security_headers(headers)


def test_missing_required_env_is_500_not_a_crash(monkeypatch):
    import config

    monkeypatch.delenv("APP_CLIENT_ID")
    config.get_settings.cache_clear()
    status, body, headers = call(make_event("GET", "/items"))
    assert status == 500
    assert body == {"message": "Something went wrong. Try again later."}
    assert "APP_CLIENT_ID" not in json.dumps(body)


# ---------------------------------------------------------------- response headers


def test_success_response_carries_security_and_cors_headers(aws):
    status, body, headers = call(make_event("GET", "/me/alerts"))
    assert status == 200
    _assert_security_headers(headers)
    assert headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    "event_factory",
    [
        lambda: make_event("GET", "/me/alerts", claims=None),  # 401
        lambda: make_event("GET", "/nope"),  # 404
        lambda: _post_items("{nope"),  # 400
        lambda: _post_items("a" * (MAX_BODY_BYTES + 1)),  # 413
    ],
    ids=["401", "404", "400", "413"],
)
def test_every_error_response_carries_the_same_headers(event_factory):
    status, _, headers = call(event_factory())
    assert status in (400, 401, 404, 413)
    _assert_security_headers(headers)


def test_cors_origin_is_the_configured_origin_never_wildcard():
    _, _, headers = call(make_event("GET", "/nope"))
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert headers["Access-Control-Allow-Origin"] != "*"
    assert headers["Vary"] == "Origin"


def test_cors_header_ignores_request_origin():
    event = make_event("GET", "/nope")
    event["headers"] = {"Origin": "https://evil.example"}
    _, _, headers = call(event)
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_cors_header_follows_the_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN", "https://app.example.org")
    _, _, headers = call(make_event("GET", "/nope"))
    assert headers["Access-Control-Allow-Origin"] == "https://app.example.org"


def test_response_shape_for_api_gateway():
    import app

    response = app.handler(make_event("GET", "/nope"), None)
    assert set(response) >= {"statusCode", "headers", "body"}
    assert isinstance(response["statusCode"], int)
    assert isinstance(response["body"], str)
    assert response["isBase64Encoded"] is False
    json.loads(response["body"])
