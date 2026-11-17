"""Who is calling. Claims come from the Cognito User Pools authorizer of the REST API.

In payload format 1.0 the verified claims are at
event["requestContext"]["authorizer"]["claims"], every value a string.

The authorizer checks signature and expiry. It does not tell an ID token from an access
token, so this module does, and it fails closed: no claims, no sub, or the wrong token
type all answer 401. The user ID used for every key comes only from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import get_settings
from errors import unauthorized

# \A and \Z anchor the WHOLE string. "^...$" would let a trailing newline through, because in
# Python "$" also matches just before a final "\n" (so "<uuid>\n" or "<email>\n" would pass and a
# newline is exactly what a header/log-injection payload carries).
_SUB_RE = re.compile(r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
_EMAIL_RE = re.compile(r"\A[^@\s]{1,64}@[^@\s]{1,255}\Z")


@dataclass(frozen=True)
class Caller:
    sub: str
    email: str | None
    email_verified: bool

    @property
    def alert_email(self) -> str | None:
        """The email to subscribe, or None when alerts are not possible for this user."""
        if self.email_verified and self.email and _EMAIL_RE.match(self.email):
            return self.email
        return None


def authenticate(event: dict) -> Caller:
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    claims = authorizer.get("claims")
    if not isinstance(claims, dict) or not claims:
        raise unauthorized()

    # Defense in depth, as api/README.md and docs/data-model.md require.
    if claims.get("token_use") != "id":
        raise unauthorized()

    sub = claims.get("sub")
    if not isinstance(sub, str) or not _SUB_RE.match(sub):
        raise unauthorized()

    # The User Pools authorizer accepts a token from any app client of the pool. Pin ours.
    settings = get_settings()
    if claims.get("aud") != settings.app_client_id:
        raise unauthorized()
    expected_iss = f"https://cognito-idp.{settings.region}.amazonaws.com/{settings.user_pool_id}"
    if claims.get("iss") != expected_iss:
        raise unauthorized()

    email = claims.get("email")
    return Caller(
        sub=sub,
        email=email if isinstance(email, str) else None,
        # Claims arrive as text, so compare with the string "true" (data-model 6.6).
        email_verified=claims.get("email_verified") == "true",
    )
