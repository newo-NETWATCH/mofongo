"""Request checks: the JSON body, path values and query values.

Body size (413), Content-Type and JSON syntax (400) are checked before the schema.
Bodies are validated with jsonschema Draft4Validator against api/schemas/requests/*.json.
Those files are standalone (no $ref), so no RefResolver is needed. The gateway validates
the same bodies too, but this stays as defense in depth.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft4Validator

from config import DEFAULT_LIMIT, MAX_BODY_BYTES, MAX_LIMIT, get_settings
from errors import ApiError, bad_request, detail
from timeutil import UUID_RE, now, parse_client_time, to_iso

_TIME_ISSUE = "Must be an ISO 8601 time with Z or an offset."
_NEXT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_=-]{1,1024}$")
_LIMIT_RE = re.compile(r"^[0-9]{1,3}$")
# base64 turns 3 bytes into 4 characters. Past this length the decoded body cannot fit.
_MAX_BASE64_CHARS = ((MAX_BODY_BYTES + 2) // 3) * 4


# ---------------------------------------------------------------- schemas

@lru_cache(maxsize=None)
def _validator(name: str) -> Draft4Validator:
    path = Path(get_settings().schema_dir) / "requests" / f"{name}.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft4Validator.check_schema(schema)
    return Draft4Validator(schema)


def categories() -> frozenset[str]:
    """The 14 categories, read from the create-item schema so there is one list."""
    schema = _validator("create-item").schema
    return frozenset(schema["properties"]["category"]["enum"])


def _field_path(error, extra: str | None = None) -> str:
    parts: list[str] = []
    for part in error.absolute_path:
        if isinstance(part, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{part}]"
            else:
                parts.append(f"[{part}]")
        else:
            parts.append(str(part))
    if extra:
        parts.append(extra)
    return ".".join(parts) or "body"


def _is_time_field(error) -> bool:
    return bool(error.absolute_path) and error.absolute_path[-1] in ("foundAt", "lostAt")


def _issue(error) -> str:
    validator, schema = error.validator, error.schema
    if validator == "enum":
        return "Must be one of the allowed values."
    if validator in ("minItems", "maxItems"):
        return f"Must have {schema.get('minItems', 0)} to {schema.get('maxItems')} entries."
    if validator == "uniqueItems":
        return "Entries must not repeat."
    if validator == "type":
        wanted = schema.get("type")
        names = {"string": "text", "array": "a list", "object": "an object"}
        return f"Must be {names.get(wanted, 'a different type')}."
    if validator == "pattern":
        if _is_time_field(error):
            return _TIME_ISSUE
        return "Must have at least one character that is not a space."
    if validator in ("minLength", "maxLength"):
        if _is_time_field(error):
            return _TIME_ISSUE
        return f"Must be {schema.get('minLength', 0)} to {schema.get('maxLength')} characters."
    return "Is not valid."


def schema_details(name: str, data: Any) -> list[dict]:
    """Every schema problem as {field, issue}. Values from the request are never echoed."""
    out: list[dict] = []
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    for error in errors:
        if error.validator == "required":
            for key in error.validator_value:
                if isinstance(error.instance, dict) and key not in error.instance:
                    out.append(detail(_field_path(error, key), "This field is required."))
        elif error.validator == "additionalProperties":
            allowed = set(error.schema.get("properties", {}))
            if isinstance(error.instance, dict):
                for key in sorted(set(error.instance) - allowed):
                    out.append(detail(_field_path(error, str(key)[:60]), "This field is not allowed."))
        else:
            out.append(detail(_field_path(error), _issue(error)))
    return out


def check_time_fields(data: dict, fields: tuple[str, ...]) -> tuple[dict[str, str], list[dict]]:
    """Convert client times to UTC with milliseconds. Refuse unparsable or future times."""
    converted: dict[str, str] = {}
    problems: list[dict] = []
    current = now()
    for field in fields:
        if field not in data or not isinstance(data[field], str):
            continue
        try:
            moment = parse_client_time(data[field])
        except ValueError:
            problems.append(detail(field, _TIME_ISSUE))
            continue
        if moment > current:
            problems.append(detail(field, "Must not be in the future."))
            continue
        converted[field] = to_iso(moment)
    return converted, problems


# ---------------------------------------------------------------- body

def _header(event: dict, name: str) -> str | None:
    # Payload format 1.0 headers are case-sensitive, so look the name up ignoring case.
    for key, value in (event.get("headers") or {}).items():
        if isinstance(key, str) and key.lower() == name:
            return value
    return None


def read_body_bytes(event: dict) -> bytes:
    """The raw body, decoded if base64. Raises 413 over 32768 bytes, 400 if it cannot be read."""
    body = event.get("body")
    if body is None or body == "":
        raise bad_request([detail("body", "A JSON body is required.")])
    if not isinstance(body, str):
        raise bad_request([detail("body", "The body could not be read.")])

    if event.get("isBase64Encoded"):
        if len(body) > _MAX_BASE64_CHARS:
            raise ApiError(413, "The request body is too large.")
        try:
            raw = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            raise bad_request([detail("body", "The body could not be read.")])
    else:
        raw = body.encode("utf-8", errors="surrogatepass")
    if len(raw) > MAX_BODY_BYTES:
        raise ApiError(413, "The request body is too large.")
    return raw


def _reject_constant(_name: str):
    raise ValueError("NaN and Infinity are not JSON")


def parse_json_body(event: dict, schema_name: str) -> dict:
    """Size, Content-Type, JSON syntax, then the schema. Returns the parsed object."""
    raw = read_body_bytes(event)

    content_type = (_header(event, "content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise bad_request([detail("Content-Type", "Must be application/json.")])

    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise bad_request([detail("body", "The body is not valid JSON.")])

    problems = schema_details(schema_name, data)
    if problems:
        raise bad_request(problems)
    return data


# ---------------------------------------------------------------- path and query

def path_uuid(event: dict, name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name)
    if not isinstance(value, str) or not UUID_RE.match(value):
        raise bad_request([detail(name, "Must be a lowercase UUID.")])
    return value


def _single(event: dict, name: str) -> str | None:
    multi = (event.get("multiValueQueryStringParameters") or {}).get(name)
    if isinstance(multi, list) and len(multi) > 1:
        raise bad_request([detail(name, "Send this only once.")])
    value = (event.get("queryStringParameters") or {}).get(name)
    return value if isinstance(value, str) else None


def list_params(event: dict, *, allow_category: bool) -> tuple[int, str | None, str | None]:
    """Returns (limit, category, nextToken) after checking every value. Unknown keys are ignored."""
    problems: list[dict] = []

    limit = DEFAULT_LIMIT
    raw_limit = _single(event, "limit")
    if raw_limit is not None:
        if _LIMIT_RE.match(raw_limit) and 1 <= int(raw_limit) <= MAX_LIMIT:
            limit = int(raw_limit)
        else:
            problems.append(detail("limit", f"Must be a whole number from 1 to {MAX_LIMIT}."))

    category = None
    if allow_category:
        category = _single(event, "category")
        if category is not None and category not in categories():
            problems.append(detail("category", "Must be one of the allowed categories."))

    token = _single(event, "nextToken")
    if token is not None and not _NEXT_TOKEN_RE.match(token):
        problems.append(detail("nextToken", "This token is not valid."))

    if problems:
        raise bad_request(problems)
    return limit, category, token
