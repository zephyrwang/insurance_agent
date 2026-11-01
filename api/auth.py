"""
Lightweight, demo-grade auth: HMAC-signed tokens plus env-configured credentials.

Not enterprise SSO — there's no credential table in the schema, and this upgrade is
explicitly scoped as "a demo-grade app," not a production auth system. Carrier access
codes come from a JSON env var; staff access from a single shared passcode.
"""

import hashlib
import hmac
import json
import os
import time
import base64
from typing import Optional

from agents.actor import Actor
from tools.underwriting_tools import normalize_carrier

TOKEN_TTL_SECONDS = 8 * 3600  # 8 hours


class InvalidToken(Exception):
    pass


def _secret() -> bytes:
    return os.getenv("APP_SECRET_KEY", "dev-secret-change-me").encode()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def sign_actor(actor: Actor) -> str:
    """Sign an Actor into an opaque token. The caller never supplies mode/carrier_name
    directly on later requests — only this token, so there's nothing in the request body
    for a client to edit to claim a different identity."""
    payload = {
        "mode": actor.mode,
        "carrier_name": actor.carrier_name,
        "exp": time.time() + TOKEN_TTL_SECONDS,
    }
    body = _b64encode(json.dumps(payload).encode())
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> Actor:
    """Verify signature and expiry, and return the Actor encoded in the token.
    Raises InvalidToken on any tamper, expiry, or malformed input."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise InvalidToken("Malformed token.")

    expected_sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise InvalidToken("Token signature invalid.")

    try:
        payload = json.loads(_b64decode(body))
    except Exception:
        raise InvalidToken("Malformed token payload.")

    if payload.get("exp", 0) < time.time():
        raise InvalidToken("Token expired.")

    mode = payload.get("mode")
    if mode == "staff":
        return Actor.staff()
    if mode == "carrier":
        carrier_name = payload.get("carrier_name")
        if not carrier_name:
            raise InvalidToken("Carrier token missing carrier_name.")
        return Actor.carrier(carrier_name)
    raise InvalidToken(f"Unknown actor mode: {mode!r}")


def _carrier_access_codes() -> dict:
    raw = os.getenv("CARRIER_ACCESS_CODES", "{}")
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def check_staff_passcode(passcode: str) -> bool:
    expected = os.getenv("STAFF_PASSCODE")
    return bool(expected) and hmac.compare_digest(passcode, expected)


def check_carrier_login(carrier_name: str, access_code: str) -> Optional[str]:
    """Verify a carrier login. Returns the normalized carrier_name on success, else None."""
    normalized = normalize_carrier(carrier_name)
    codes = _carrier_access_codes()
    expected = codes.get(normalized)
    if expected and hmac.compare_digest(access_code, expected):
        return normalized
    return None
