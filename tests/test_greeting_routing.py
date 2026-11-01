"""
Tests for the greeting agent and its routing:
  - a brand-new session always meets the greeting agent first, regardless of content
  - subsequent turns route normally
  - keyword routing recognizes smalltalk without misrouting real data questions
  - the greeting system prompt's capability text differs by actor mode

The specialist agent builders are monkeypatched to lightweight fakes so these tests
run without a live LLM — SupervisorAgent.run() still exercises the real routing and
first-turn logic, just not a real ReAct loop.
"""

import pytest

import agents.supervisor_agent as supervisor_module
from agents.supervisor_agent import SupervisorAgent, _keyword_route
from agents.actor import Actor
from agents.greeting_agent import build_greeting_system_prompt


class _FakeAgent:
    """Stands in for a real LangChain agent — returns a tag instead of calling an LLM."""

    def __init__(self, tag):
        self.tag = tag
        self.tools = []

    def run(self, question):
        if self.tag == "greeting":
            return f"Hi! I'm here to help. ({question})"
        # A pre-formed table so enforce_tabular_format's cheap check short-circuits
        # without needing to call the LLM for a reformat.
        return f"| Field | Value |\n|---|---|\n| domain | {self.tag} |\n\n**Comment**\n- ok"


@pytest.fixture(autouse=True)
def fake_agent_builders(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-for-construction-only")
    monkeypatch.setattr(
        supervisor_module, "build_underwriting_agent", lambda **kw: _FakeAgent("underwriting")
    )
    monkeypatch.setattr(supervisor_module, "build_claims_agent", lambda **kw: _FakeAgent("claims"))
    monkeypatch.setattr(
        supervisor_module, "build_analytics_agent", lambda **kw: _FakeAgent("analytics")
    )
    monkeypatch.setattr(
        supervisor_module, "build_greeting_agent", lambda **kw: _FakeAgent("greeting")
    )


# ── first-turn-forces-greeting ────────────────────────────────────────────────


class TestFirstTurnForcesGreeting:
    def test_first_turn_routes_to_greeting_even_for_a_clear_data_question(self):
        supervisor = SupervisorAgent()
        result = supervisor.run("What is the risk score for policy A-10234?")
        assert result["routed_to"] == "greeting"

    def test_second_turn_in_the_same_session_routes_normally(self):
        supervisor = SupervisorAgent()
        supervisor.run("hello", session_id="s1")
        result = supervisor.run("What is the risk score for policy A-10234?", session_id="s1")
        assert result["routed_to"] == "underwriting"

    def test_each_session_gets_its_own_first_turn(self):
        supervisor = SupervisorAgent()
        r1 = supervisor.run("What is the risk score for policy A-10234?", session_id="s1")
        r2 = supervisor.run("What is the risk score for policy A-10234?", session_id="s2")
        assert r1["routed_to"] == "greeting"
        assert r2["routed_to"] == "greeting"

    def test_greeting_answer_is_not_coerced_into_a_table(self):
        """Confirms the skip=True wiring actually took effect end-to-end — the fake
        greeting agent's plain-text reply isn't a table, and must come back unchanged
        rather than triggering an LLM reformat call."""
        supervisor = SupervisorAgent()
        result = supervisor.run("hello")
        assert result["answer"].startswith("Hi! I'm here to help.")


# ── keyword routing ────────────────────────────────────────────────────────────


class TestGreetingKeywordRouting:
    def test_smalltalk_routes_to_greeting(self):
        assert _keyword_route("hello, what can you do?") == "greeting"
        assert _keyword_route("thanks, goodbye") == "greeting"

    def test_real_data_questions_are_not_misrouted_to_greeting(self):
        assert _keyword_route("what is the risk score for policy A-10234") == "underwriting"
        assert _keyword_route("claims history for person P-001") == "claims"
        assert _keyword_route("what is the loss ratio for California") == "analytics"


# ── per-mode capability text ───────────────────────────────────────────────────


class TestGreetingCapabilityText:
    def test_staff_and_carrier_prompts_differ(self):
        staff_prompt = build_greeting_system_prompt(Actor.staff())
        carrier_prompt = build_greeting_system_prompt(Actor.carrier("GEICO"))
        assert staff_prompt != carrier_prompt

    def test_staff_prompt_mentions_all_three_domains(self):
        prompt = build_greeting_system_prompt(Actor.staff()).lower()
        assert "underwriting" in prompt
        assert "claims" in prompt
        assert "analytics" in prompt

    def test_carrier_prompt_names_its_own_carrier_and_cross_carrier_benchmarks(self):
        prompt = build_greeting_system_prompt(Actor.carrier("GEICO"))
        assert "GEICO" in prompt
        assert "cross-carrier" in prompt.lower()

    def test_carrier_prompt_disclaims_other_carriers_records(self):
        prompt = build_greeting_system_prompt(Actor.carrier("GEICO")).lower()
        assert "not reveal another carrier" in prompt
