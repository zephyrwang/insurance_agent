"""
Unit tests for api/auth.py — token signing/verification and login credential checks.

No FastAPI TestClient needed: these exercise the pure functions directly, which is
also what the /chat and /auth/* endpoints call under the hood.
"""

import time
import pytest

from agents.actor import Actor
from api.auth import (
    sign_actor,
    verify_token,
    check_staff_passcode,
    check_carrier_login,
    InvalidToken,
)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("STAFF_PASSCODE", "letmein")
    monkeypatch.setenv(
        "CARRIER_ACCESS_CODES",
        '{"GEICO": "geico-code", "StateFarm": "statefarm-code"}',
    )


# ── token round-trip ──────────────────────────────────────────────────────────


class TestTokenRoundTrip:
    def test_staff_actor_round_trips(self):
        token = sign_actor(Actor.staff())
        actor = verify_token(token)
        assert actor == Actor.staff()

    def test_carrier_actor_round_trips(self):
        token = sign_actor(Actor.carrier("GEICO"))
        actor = verify_token(token)
        assert actor == Actor.carrier("GEICO")

    def test_tampered_signature_rejected(self):
        token = sign_actor(Actor.carrier("GEICO"))
        body, sig = token.rsplit(".", 1)
        tampered = f"{body}.{'0' * len(sig)}"
        with pytest.raises(InvalidToken):
            verify_token(tampered)

    def test_tampered_payload_rejected(self):
        """Flipping the carrier_name in the payload without re-signing must fail —
        this is exactly the 'edit the JSON to claim a different identity' attack."""
        token = sign_actor(Actor.carrier("GEICO"))
        body, sig = token.rsplit(".", 1)

        import json
        from api.auth import _b64encode, _b64decode

        payload = json.loads(_b64decode(body))
        payload["carrier_name"] = "StateFarm"
        forged_body = _b64encode(json.dumps(payload).encode())
        forged_token = f"{forged_body}.{sig}"  # old signature, new payload

        with pytest.raises(InvalidToken):
            verify_token(forged_token)

    def test_expired_token_rejected(self, monkeypatch):
        token = sign_actor(Actor.staff())
        # Jump the clock past the token's TTL.
        future = time.time() + 999999
        monkeypatch.setattr(time, "time", lambda: future)
        with pytest.raises(InvalidToken):
            verify_token(token)

    def test_malformed_token_rejected(self):
        with pytest.raises(InvalidToken):
            verify_token("not-a-real-token")


# ── staff passcode ────────────────────────────────────────────────────────────


class TestStaffPasscode:
    def test_correct_passcode_accepted(self):
        assert check_staff_passcode("letmein") is True

    def test_wrong_passcode_rejected(self):
        assert check_staff_passcode("wrong") is False

    def test_missing_passcode_env_rejects_everything(self, monkeypatch):
        monkeypatch.delenv("STAFF_PASSCODE", raising=False)
        assert check_staff_passcode("letmein") is False


# ── carrier login ─────────────────────────────────────────────────────────────


class TestCarrierLogin:
    def test_correct_pair_returns_normalized_carrier_name(self):
        assert check_carrier_login("GEICO", "geico-code") == "GEICO"

    def test_alias_is_normalized(self):
        """normalize_carrier() should resolve 'geico' the same as 'GEICO'."""
        assert check_carrier_login("geico", "geico-code") == "GEICO"

    def test_wrong_access_code_rejected(self):
        assert check_carrier_login("GEICO", "wrong-code") is None

    def test_unknown_carrier_rejected(self):
        assert check_carrier_login("UnknownCarrierCo", "anything") is None
