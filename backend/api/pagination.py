"""nextToken: base64url of {"q": <query id>, "k": <LastEvaluatedKey>} (data-model section 3).

The token travels through the browser, so it is checked before it becomes an
ExclusiveStartKey: it must decode, belong to this exact query, carry exactly the key
attributes of the index, and hold this request's partition value. Any failure is a 400
and nothing is queried.
"""

from __future__ import annotations

import base64
import binascii
import json

from errors import bad_request, detail
from timeutil import TIMESTAMP_RE, UUID_RE

# index name -> (attribute names of the index key, how to check each value)
_ID = "uuid"
_TS = "timestamp"
_TEXT = "text"
_KEY_SHAPES = {
    "ListedByDate": {"itemId": _ID, "listedPk": _TEXT, "createdAt": _TS},
    "ListedByCategory": {"itemId": _ID, "listedCategory": _TEXT, "createdAt": _TS},
    "ByOwner": {"ownerId": _TEXT, "reportId": _ID, "createdAt": _TS},
}


def _invalid():
    return bad_request([detail("nextToken", "This token is not valid.")])


def encode(query_id: str, last_key: dict) -> str:
    raw = json.dumps({"q": query_id, "k": last_key}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode(
    token: str,
    *,
    index: str,
    query_id: str,
    partition_attr: str,
    partition_value: str,
) -> dict:
    """Return the ExclusiveStartKey for this request, or raise 400."""
    shape = _KEY_SHAPES[index]
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError, RecursionError):
        raise _invalid()

    if not isinstance(payload, dict) or set(payload) != {"q", "k"}:
        raise _invalid()
    if payload["q"] != query_id:
        raise _invalid()

    key = payload["k"]
    if not isinstance(key, dict) or set(key) != set(shape):
        raise _invalid()
    for attr, kind in shape.items():
        value = key[attr]
        if not isinstance(value, str) or not value or len(value) > 128:
            raise _invalid()
        if kind == _ID and not UUID_RE.match(value):
            raise _invalid()
        if kind == _TS and not TIMESTAMP_RE.match(value):
            raise _invalid()
    if key[partition_attr] != partition_value:
        raise _invalid()
    return key
