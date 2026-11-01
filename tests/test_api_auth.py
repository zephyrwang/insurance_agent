"""
API-level tests for the login -> token -> /chat path in api/main.py.

/chat's actual answers come from a live LangChain ReAct loop against a real LLM —
that path is exercised (and skip-guarded when no GROQ_API_KEY is set) elsewhere, same
as the rest of this repo's live-LLM tests. What's tested here, without needing a live
LLM, is the part that actually matters for access control: a bad/missing token is
rejected before it ever reaches the supervisor, and a valid token's Actor is derived
only from the verified payload and forwarded correctly — never trusted from any other
field in the request body.
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GROQ_API_KEY", "dummy-key-for-construction-only")
os.environ["DATABASE_URL"] = "sqlite:///./_test_api_auth.db"
os.environ["APP_SECRET_KEY"] = "test-secret"
os.environ["STAFF_PASSCODE"] = "letmein"
os.environ["CARRIER_ACCESS_CODES"] = '{"GEICO": "geico-code", "StateFarm": "statefarm-code"}'

from api.main import app  # noqa: E402
from agents.actor import Actor  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    db_path = "./_test_api_auth.db"
    if os.path.exists(db_path):
        os.remove(db_path)


class _FakeSupervisor:
    """Stands in for the real SupervisorAgent so /chat can be exercised without a
    live LLM — records the actor it was called with so tests can assert on it."""

    def __init__(self):
        self.calls = []

    def run(self, question, session_id="default", actor=None):
        self.calls.append({"question": question, "session_id": session_id, "actor": actor})
        return {"question": question, "routed_to": "underwriting", "answer": "fake answer"}

    def get_routing_log(self):
        return []

    @property
    def agents(self):
        return {"underwriting": None, "claims": None, "analytics": None}


@pytest.fixture
def fake_supervisor(client, monkeypatch):
    fake = _FakeSupervisor()
    monkeypatch.setattr("api.main.supervisor", fake)
    return fake


# ── /auth/staff-login ─────────────────────────────────────────────────────────


class TestStaffLoginEndpoint:
    def test_correct_passcode_returns_token(self, client):
        resp = client.post("/auth/staff-login", json={"passcode": "letmein"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "staff"
        assert resp.json()["token"]

    def test_wrong_passcode_rejected(self, client):
        resp = client.post("/auth/staff-login", json={"passcode": "wrong"})
        assert resp.status_code == 401


# ── /auth/carrier-login ───────────────────────────────────────────────────────


class TestCarrierLoginEndpoint:
    def test_correct_pair_returns_token(self, client):
        resp = client.post(
            "/auth/carrier-login", json={"carrier_name": "GEICO", "access_code": "geico-code"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "carrier"
        assert body["carrier_name"] == "GEICO"
        assert body["token"]

    def test_wrong_access_code_rejected(self, client):
        resp = client.post(
            "/auth/carrier-login", json={"carrier_name": "GEICO", "access_code": "wrong"}
        )
        assert resp.status_code == 401


# ── /chat token gating ────────────────────────────────────────────────────────


class TestChatTokenGating:
    def test_missing_token_field_rejected_by_schema(self, client):
        resp = client.post("/chat", json={"question": "hi"})
        assert resp.status_code == 422  # token is a required field

    def test_garbage_token_rejected(self, client, fake_supervisor):
        resp = client.post("/chat", json={"question": "hi", "token": "not-a-real-token"})
        assert resp.status_code == 401
        assert fake_supervisor.calls == []  # never reached the supervisor

    def test_valid_staff_token_derives_staff_actor(self, client, fake_supervisor):
        login = client.post("/auth/staff-login", json={"passcode": "letmein"}).json()
        resp = client.post("/chat", json={"question": "hi", "token": login["token"]})

        assert resp.status_code == 200
        assert fake_supervisor.calls[-1]["actor"] == Actor.staff()

    def test_valid_carrier_token_derives_carrier_actor_from_token_only(
        self, client, fake_supervisor
    ):
        """The request body carries ONLY the token — there's no mode/carrier_name field
        for a client to edit to claim a different identity."""
        login = client.post(
            "/auth/carrier-login", json={"carrier_name": "GEICO", "access_code": "geico-code"}
        ).json()
        resp = client.post("/chat", json={"question": "hi", "token": login["token"]})

        assert resp.status_code == 200
        assert fake_supervisor.calls[-1]["actor"] == Actor.carrier("GEICO")
