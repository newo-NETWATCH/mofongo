"""The one error type and the error body.

The body matches api/schemas/shared/error.json: `message` always, `details` only on 400.
Messages are fixed plain text. They never contain request values, ARNs or stack traces.
"""

from __future__ import annotations

MAX_DETAILS = 50


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details

    def body(self) -> dict:
        body: dict = {"message": self.message[:500]}
        if self.details:
            body["details"] = [
                {"field": str(d["field"])[:100], "issue": str(d["issue"])[:300]}
                for d in self.details[:MAX_DETAILS]
            ]
        return body


def bad_request(details: list[dict]) -> ApiError:
    return ApiError(400, "The request is not valid.", details)


def detail(field: str, issue: str) -> dict:
    return {"field": field, "issue": issue}


def unauthorized() -> ApiError:
    return ApiError(401, "Unauthorized")
