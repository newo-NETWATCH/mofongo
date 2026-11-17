"""Tests for auth.authenticate and the 401 path through app.handler.

No real AWS: the `aws` fixture (moto) backs the one route call that reaches the data layer.
Fixtures and helpers (api_env, aws, make_claims, make_event, call) come from conftest.py.
"""

from __future__ import annotations

import os
import uuid

import pytest

from conftest import call, make_claims, make_event

ROUTE = ("GET", "/items")


def _authenticate(claims):
    import auth

    return auth.authenticate(make_event(*ROUTE, claims=claims))


def _assert_unauthorized(claims):
    import auth
    from errors import ApiError

    with pytest.raises(ApiError) as exc:
        auth.authenticate(make_event(*ROUTE, claims=claims))
    assert exc.value.status == 401
    assert exc.value.body() == {"message": "Unauthorized"}


def _assert_401_via_handler(claims):
    status, body, headers = call(make_event(*ROUTE, claims=claims))
    assert status == 401
    assert body == {"message": "Unauthorized"}
    return headers


# ---------------------------------------------------------------- valid claims


def test_valid_claims_return_caller():
    sub = str(uuid.uuid4())
    caller = _authenticate(make_claims(sub=sub, email="owner@example.com"))
    assert caller.sub == sub
    assert caller.email == "owner@example.com"
    assert caller.email_verified is True


def test_valid_claims_reach_route(aws):
    status, body, _ = call(make_event(*ROUTE, claims=make_claims()))
    assert status == 200
    assert isinstance(body, dict)


def test_uppercase_uuid_sub_is_accepted():
    sub = str(uuid.uuid4()).upper()
    assert _authenticate(make_claims(sub=sub)).sub == sub


def test_caller_is_immutable():
    caller = _authenticate(make_claims())
    with pytest.raises(Exception):
        caller.sub = "someone-else"  # frozen dataclass


# ---------------------------------------------------------------- missing claims


def test_missing_authorizer_is_401():
    _assert_unauthorized(None)


def test_missing_authorizer_via_handler_is_401(aws):
    _assert_401_via_handler(None)


def test_empty_claims_is_401():
    _assert_unauthorized({})


def test_claims_not_a_dict_is_401():
    import auth
    from errors import ApiError

    for bad in ("claims", ["sub"], 7, None):
        event = make_event(*ROUTE, claims=None)
        event["requestContext"] = {"authorizer": {"claims": bad}}
        with pytest.raises(ApiError) as exc:
            auth.authenticate(event)
        assert exc.value.status == 401


def test_event_without_request_context_is_401():
    import auth
    from errors import ApiError

    event = make_event(*ROUTE, claims=None)
    event.pop("requestContext", None)
    with pytest.raises(ApiError) as exc:
        auth.authenticate(event)
    assert exc.value.status == 401


def test_authorizer_none_is_401():
    import auth
    from errors import ApiError

    event = make_event(*ROUTE, claims=None)
    event["requestContext"] = {"authorizer": None}
    with pytest.raises(ApiError) as exc:
        auth.authenticate(event)
    assert exc.value.status == 401


# ---------------------------------------------------------------- token_use


@pytest.mark.parametrize("token_use", ["access", "refresh", "", "ID", None])
def test_token_use_not_id_is_401(token_use):
    claims = make_claims(token_use=token_use)
    if token_use is None:
        # make_claims already drops a None override, so the key may be gone already.
        claims.pop("token_use", None)
    _assert_unauthorized(claims)


def test_missing_token_use_via_handler_is_401(aws):
    claims = make_claims()
    claims.pop("token_use")
    _assert_401_via_handler(claims)


# ---------------------------------------------------------------- sub


@pytest.mark.parametrize(
    "sub",
    [
        "not-a-uuid",
        "",
        "12345",
        "00000000-0000-0000-0000-00000000000",  # one char short
        "00000000-0000-0000-0000-0000000000000",  # one char long
        "0000000000000000000000000000000000000",  # no dashes
        "gggggggg-gggg-gggg-gggg-gggggggggggg",  # not hex
        " " + str(uuid.uuid4()),  # leading space
        str(uuid.uuid4()) + "\n",  # trailing newline must not slip past the regex
        "user@example.com",
        "' OR 1=1 --",
    ],
)
def test_sub_not_a_uuid_is_401(sub):
    claims = make_claims()
    claims["sub"] = sub
    _assert_unauthorized(claims)


def test_missing_sub_is_401():
    claims = make_claims()
    claims.pop("sub")
    _assert_unauthorized(claims)


def test_non_string_sub_is_401():
    claims = make_claims()
    claims["sub"] = 12345
    _assert_unauthorized(claims)


def test_bad_sub_via_handler_is_401(aws):
    claims = make_claims()
    claims["sub"] = "not-a-uuid"
    _assert_401_via_handler(claims)


# ---------------------------------------------------------------- aud


@pytest.mark.parametrize("aud", ["someotherclient", "", "TESTCLIENT123", "testclient123 "])
def test_wrong_aud_is_401(aud):
    claims = make_claims()
    claims["aud"] = aud
    _assert_unauthorized(claims)


def test_missing_aud_is_401():
    claims = make_claims()
    claims.pop("aud")
    _assert_unauthorized(claims)


def test_wrong_aud_via_handler_is_401(aws):
    claims = make_claims()
    claims["aud"] = "someotherclient"
    _assert_401_via_handler(claims)


# ---------------------------------------------------------------- iss


def test_wrong_pool_in_iss_is_401():
    claims = make_claims()
    claims["iss"] = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_OTHERPOOL"
    _assert_unauthorized(claims)


def test_wrong_region_in_iss_is_401():
    claims = make_claims()
    claims["iss"] = "https://cognito-idp.us-east-1.amazonaws.com/us-east-2_TESTPOOL"
    _assert_unauthorized(claims)


def test_foreign_issuer_is_401():
    claims = make_claims()
    claims["iss"] = "https://evil.example.com/us-east-2_TESTPOOL"
    _assert_unauthorized(claims)


def test_iss_with_trailing_slash_is_401():
    claims = make_claims()
    claims["iss"] += "/"
    _assert_unauthorized(claims)


def test_missing_iss_is_401():
    claims = make_claims()
    claims.pop("iss")
    _assert_unauthorized(claims)


def test_wrong_iss_via_handler_is_401(aws):
    claims = make_claims()
    claims["iss"] = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_OTHERPOOL"
    _assert_401_via_handler(claims)


def test_correct_iss_is_built_from_settings():
    claims = make_claims()
    assert claims["iss"] == "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_TESTPOOL"
    assert _authenticate(claims)


# ---------------------------------------------------------------- email / email_verified


def test_email_verified_string_true_is_true():
    assert _authenticate(make_claims(email_verified="true")).email_verified is True


@pytest.mark.parametrize("value", ["false", "True", "TRUE", "1", "yes", "", " true"])
def test_email_verified_other_strings_are_false(value):
    assert _authenticate(make_claims(email_verified=value)).email_verified is False


def test_email_verified_real_boolean_is_false():
    # Claims are always strings from API Gateway; a bool is not the contract, so it is not trusted.
    assert _authenticate(make_claims(email_verified=True)).email_verified is False


def test_email_verified_missing_is_false():
    claims = make_claims()
    claims.pop("email_verified")
    assert _authenticate(claims).email_verified is False


def test_missing_email_gives_none():
    claims = make_claims()
    claims.pop("email")
    caller = _authenticate(claims)
    assert caller.email is None
    assert caller.alert_email is None


def test_non_string_email_gives_none():
    claims = make_claims()
    claims["email"] = 12345
    assert _authenticate(claims).email is None


# ---------------------------------------------------------------- Caller.alert_email


def _caller(email, verified):
    from auth import Caller

    return Caller(sub=str(uuid.uuid4()), email=email, email_verified=verified)


def test_alert_email_returned_when_verified_and_well_formed():
    assert _caller("owner@example.com", True).alert_email == "owner@example.com"


def test_alert_email_none_when_not_verified():
    assert _caller("owner@example.com", False).alert_email is None


def test_alert_email_none_when_email_missing():
    assert _caller(None, True).alert_email is None
    assert _caller("", True).alert_email is None


@pytest.mark.parametrize(
    "email",
    [
        "no-at-sign",
        "@example.com",
        "owner@",
        "two@@example.com",
        "with space@example.com",
        "owner@exa mple.com",
        "owner@example.com\nBcc: x@y.z",
        ("a" * 65) + "@example.com",  # local part over 64
        "a@" + ("b" * 256),  # domain over 255
    ],
)
def test_alert_email_none_when_malformed(email):
    assert _caller(email, True).alert_email is None


def test_alert_email_via_authenticate_end_to_end():
    verified = _authenticate(make_claims(email="a@example.com", email_verified="true"))
    unverified = _authenticate(make_claims(email="a@example.com", email_verified="false"))
    assert verified.alert_email == "a@example.com"
    assert unverified.alert_email is None


# ---------------------------------------------------------------- distinct users


def test_distinct_subs_give_distinct_callers():
    a = _authenticate(make_claims())
    b = _authenticate(make_claims())
    assert a.sub != b.sub


# ---------------------------------------------------------------- envelope and headers


def test_401_body_is_shared_error_envelope(aws):
    status, body, _ = call(make_event(*ROUTE, claims=None))
    assert status == 401
    assert body == {"message": "Unauthorized"}
    assert "details" not in body  # details are only for 400


def test_401_does_not_leak_claim_values(aws):
    claims = make_claims()
    claims["aud"] = "leaky-client-id-value"
    claims["sub"] = "leaky-sub-value"
    status, body, _ = call(make_event(*ROUTE, claims=claims))
    assert status == 401
    text = str(body)
    assert "leaky" not in text
    assert os.environ["APP_CLIENT_ID"] not in text
    assert os.environ["USER_POOL_ID"] not in text


def test_401_carries_cors_and_security_headers(aws):
    headers = _assert_401_via_handler(None)
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert headers["Access-Control-Allow-Origin"] != "*"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Type"] == "application/json"
    assert headers["Vary"] == "Origin"


def test_200_carries_cors_and_security_headers(aws):
    status, _, headers = call(make_event(*ROUTE, claims=make_claims()))
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_auth_runs_before_routing(aws):
    # An unknown route with no claims is 401, not 404: nothing is revealed to the unauthenticated.
    event = make_event("GET", "/does-not-exist", claims=None)
    status, body, _ = call(event)
    assert status == 401
    assert body == {"message": "Unauthorized"}


def test_unknown_route_with_valid_claims_is_404(aws):
    status, body, _ = call(make_event("GET", "/does-not-exist", claims=make_claims()))
    assert status == 404
    assert "message" in body


@pytest.mark.parametrize(
    "method,resource",
    [
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
    ],
)
def test_every_route_rejects_missing_claims(aws, method, resource):
    event = make_event(method, resource, claims=None)
    status, body, _ = call(event)
    assert status == 401
    assert body == {"message": "Unauthorized"}


@pytest.mark.parametrize(
    "method,resource",
    [
        ("GET", "/items"),
        ("POST", "/items"),
        ("GET", "/reports"),
        ("POST", "/reports"),
        ("GET", "/me/alerts"),
        ("POST", "/me/alerts"),
    ],
)
def test_every_route_rejects_access_token(aws, method, resource):
    event = make_event(method, resource, claims=make_claims(token_use="access"))
    status, body, _ = call(event)
    assert status == 401
    assert body == {"message": "Unauthorized"}
