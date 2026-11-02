"""
Tests for SupervisorAgent's automatic re-route when a specialist's own prompt
defers to a sibling ("Please ask the Claims Agent") — the initial keyword/LLM
routing picked the wrong domain, and the specialist recognized that itself.
The supervisor should transparently re-dispatch to the named sibling instead
of surfacing the raw deferral text as if it were the final answer.
"""

import pytest

import agents.supervisor_agent as supervisor_module
from agents.supervisor_agent import SupervisorAgent
from agents.output_validator import extract_deferral_target


TABLE_ANSWER = "| Field | Value |\n|---|---|\n| claims_in_2026 | 3 |\n\n**Comment**\n- ok"


class _FakeAgent:
    def __init__(self, output):
        self.tools = []
        self._output = output
        self.calls = 0

    def invoke(self, inputs):
        self.calls += 1
        return {"output": self._output}


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-for-construction-only")
    monkeypatch.setattr(supervisor_module, "build_analytics_agent", lambda **kw: _FakeAgent("n/a"))
    monkeypatch.setattr(supervisor_module, "build_greeting_agent", lambda **kw: _FakeAgent("n/a"))


# ── extract_deferral_target ───────────────────────────────────────────────────


class TestExtractDeferralTarget:
    def test_recognizes_each_agent_name(self):
        assert extract_deferral_target("Please ask the Claims Agent.") == "claims"
        assert extract_deferral_target("Please ask the Underwriting Agent") == "underwriting"
        assert extract_deferral_target("Please ask the Analytics Agent for trends.") == "analytics"

    def test_non_deferral_answer_returns_none(self):
        assert extract_deferral_target(TABLE_ANSWER) is None

    def test_unrecognized_agent_name_returns_none(self):
        assert extract_deferral_target("Please ask the Billing Agent.") is None


# ── SupervisorAgent auto-redirect ─────────────────────────────────────────────


class TestSupervisorAutoRedirect:
    def test_deferral_from_underwriting_transparently_reroutes_to_claims(self, monkeypatch):
        """Reproduces the reported bug: 'show all the policies with claims in 2026
        from geico' keyword-routes to underwriting, which correctly defers to
        claims — the user must get the claims agent's real answer, not the raw
        deferral text."""
        underwriting = _FakeAgent("Please ask the Claims Agent.")
        claims = _FakeAgent(TABLE_ANSWER)
        monkeypatch.setattr(supervisor_module, "build_underwriting_agent", lambda **kw: underwriting)
        monkeypatch.setattr(supervisor_module, "build_claims_agent", lambda **kw: claims)

        supervisor = SupervisorAgent()
        # "policies" keyword-routes to underwriting; no claims keyword present.
        result = supervisor.run("show all the policies with claims in 2026 from geico")

        assert result["routed_to"] == "claims"
        assert result["answer"] == TABLE_ANSWER
        assert underwriting.calls == 1
        assert claims.calls == 1

    def test_routing_log_records_both_hops(self, monkeypatch):
        underwriting = _FakeAgent("Please ask the Claims Agent.")
        claims = _FakeAgent(TABLE_ANSWER)
        monkeypatch.setattr(supervisor_module, "build_underwriting_agent", lambda **kw: underwriting)
        monkeypatch.setattr(supervisor_module, "build_claims_agent", lambda **kw: claims)

        supervisor = SupervisorAgent()
        supervisor.run("show all the policies with claims in 2026 from geico")

        routed = [e["routed_to"] for e in supervisor.get_routing_log()]
        assert routed == ["underwriting", "claims"]

    def test_no_redirect_when_answer_is_not_a_deferral(self, monkeypatch):
        underwriting = _FakeAgent(TABLE_ANSWER)
        claims = _FakeAgent("should never be called")
        monkeypatch.setattr(supervisor_module, "build_underwriting_agent", lambda **kw: underwriting)
        monkeypatch.setattr(supervisor_module, "build_claims_agent", lambda **kw: claims)

        supervisor = SupervisorAgent()
        result = supervisor.run("show all the policies")

        assert result["routed_to"] == "underwriting"
        assert claims.calls == 0

    def test_no_infinite_loop_when_second_agent_also_defers(self, monkeypatch):
        """If the sibling also defers (shouldn't happen with well-formed prompts,
        but must not hang), only one redirect hop is attempted."""
        underwriting = _FakeAgent("Please ask the Claims Agent.")
        claims = _FakeAgent("Please ask the Underwriting Agent.")
        monkeypatch.setattr(supervisor_module, "build_underwriting_agent", lambda **kw: underwriting)
        monkeypatch.setattr(supervisor_module, "build_claims_agent", lambda **kw: claims)

        supervisor = SupervisorAgent()
        result = supervisor.run("show all the policies with claims in 2026 from geico")

        assert result["routed_to"] == "claims"
        assert underwriting.calls == 1
        assert claims.calls == 1
