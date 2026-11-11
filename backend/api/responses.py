"""Response building for API Gateway REST proxy integration (payload format 1.0).

Not named http.py on purpose: a top-level http module in /var/task would shadow the standard library http package."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any


def _json_default(value: Any) -> Any:
    # DynamoDB gives numbers back as Decimal. Only whole numbers are stored.
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        raise TypeError("Non-integer Decimal in response")
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def json_response(status: int, body: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Vary": "Origin",
    }
    # With a REST API the Lambda must return the CORS header on real answers. The gateway
    # OPTIONS mock only covers the preflight. One configured origin, never "*".
    origin = os.environ.get("CORS_ORIGIN")
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, default=_json_default, separators=(",", ":")),
        "isBase64Encoded": False,
    }
