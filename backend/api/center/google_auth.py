"""Server-side verification of Google ID tokens; identity comes from the token, never the body."""

from dataclasses import dataclass
from typing import Callable


class GoogleAuthError(Exception):
    """The Google token is invalid."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    exp: int | None = None  # expiry of the ID token itself (None when the verifier does not know)


Verifier = Callable[[str], GoogleIdentity]


def make_google_verifier(client_id: str) -> Verifier:
    """Return a function that verifies an ID token (signature, audience, expiry, verified email)."""

    def verify(token: str) -> GoogleIdentity:
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
        except Exception as exc:  # the library raises many types; all mean "bad token"
            raise GoogleAuthError("Invalid Google token") from exc
        if not claims.get("email_verified") or not claims.get("email") or not claims.get("sub"):
            raise GoogleAuthError("Google email is not verified")
        return GoogleIdentity(
            sub=str(claims["sub"])[:64], email=str(claims["email"]).lower()[:254], exp=int(claims.get("exp") or 0) or None
        )

    return verify
