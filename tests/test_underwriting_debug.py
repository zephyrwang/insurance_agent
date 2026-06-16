"""
Diagnostic tests for "Error in underwriting agent: Connection error."

The error originates in SupervisorAgent.run() when agent.run(question) raises.
Run this file with `pytest tests/test_underwriting_debug.py -v` to narrow down
which layer is broken.  The tests are ordered from outermost to innermost:

  Step 1 — Routing         (pure logic, no I/O)
  Step 2 — DB connectivity (SQLAlchemy session / file check)
  Step 3 — Tool functions  (SQL queries against a test DB)
  Step 4 — Agent init      (LangChain agent build with a mock LLM)

If all four steps pass, the fault is in the live Groq API connection
(invalid/missing GROQ_API_KEY or network). That requires a live API key
to test and is documented in TestLLMConnectivity at the bottom.
"""

import os
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AutoPolicy, Claim
from agents.supervisor_agent import _keyword_route, ROUTING_RULES

# ─────────────────────────────────────────────────────────────
# Step 1 — Routing
# A failure here means the question never reaches the underwriting agent.
# ─────────────────────────────────────────────────────────────

class TestRoutingDebug:
    POLICY_QUESTION = "What is the risk score for policy A-10234?"

    def test_routes_to_underwriting(self):
        """Core assertion: the exact failing question must route to underwriting."""
        result = _keyword_route(self.POLICY_QUESTION)
        assert result == "underwriting", (
            f"Expected 'underwriting', got '{result}'. "
            "The question may be tied or hitting the wrong keyword bucket."
        )

    def test_routes_cleanly_no_tie(self):
        """Routing should be decisive — not fall through to the LLM."""
        q = self.POLICY_QUESTION.lower()
        scores = {domain: 0 for domain in ROUTING_RULES}
        for domain, keywords in ROUTING_RULES.items():
            for kw in keywords:
                if kw in q:
                    scores[domain] += 1
        sorted_vals = sorted(scores.values(), reverse=True)
        assert sorted_vals[0] > sorted_vals[1], (
            f"Scores are tied or zero: {scores}. "
            "The keyword router would fall through to LLM, which is non-deterministic."
        )

    def test_underwriting_keywords_present_in_question(self):
        """Confirm which underwriting keywords actually fire."""
        q = self.POLICY_QUESTION.lower()
        matched = [kw for kw in ROUTING_RULES["underwriting"] if kw in q]
        assert matched, "No underwriting keywords matched — routing will fail or go to LLM."

    def test_claims_keywords_absent(self):
        """Confirm no claims keywords accidentally fire and create a tie."""
        q = self.POLICY_QUESTION.lower()
        matched = [kw for kw in ROUTING_RULES["claims"] if kw in q]
        assert not matched, f"Claims keywords unexpectedly matched: {matched}"

    def test_analytics_keywords_absent(self):
        """Confirm no analytics keywords fire."""
        q = self.POLICY_QUESTION.lower()
        matched = [kw for kw in ROUTING_RULES["analytics"] if kw in q]
        assert not matched, f"Analytics keywords unexpectedly matched: {matched}"


# ─────────────────────────────────────────────────────────────
# Step 2 — DB connectivity
# A failure here means the SQLite file is missing, corrupt, or the
# DATABASE_URL points to an unreachable host.
# ─────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "insurance_dev.db")
REAL_DB_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"


class TestDBConnectivity:
    def test_dev_db_file_exists(self):
        """The SQLite file must be present for the app to work."""
        assert os.path.exists(DB_PATH), (
            f"insurance_dev.db not found at {DB_PATH}. "
            "Run the Streamlit app or `python -m api.main` once to seed it."
        )

    def test_engine_creates_without_error(self):
        """SQLAlchemy engine creation must not raise."""
        from db.database import get_engine
        engine = get_engine(REAL_DB_URL)
        assert engine is not None

    def test_session_opens_without_error(self):
        """SQLAlchemy session must open successfully."""
        from db.database import get_engine, get_session
        engine = get_engine(REAL_DB_URL)
        session = get_session(engine)
        assert session is not None
        session.close()

    def test_auto_policies_table_exists_and_has_rows(self):
        """auto_policies table must exist and contain at least one row."""
        from db.database import get_engine
        from sqlalchemy import text
        engine = get_engine(REAL_DB_URL)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM auto_policies")).scalar()
        assert count > 0, (
            "auto_policies table is empty — seed data is missing. "
            "Call db.database.seed_sample_data() or start the API."
        )

    def test_policy_a10234_exists(self):
        """The specific policy from the failing question must exist in the DB."""
        from db.database import get_engine
        from sqlalchemy import text
        engine = get_engine(REAL_DB_URL)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT policy_id, risk_score FROM auto_policies WHERE policy_id = 'A-10234'")
            ).fetchone()
        assert row is not None, (
            "Policy A-10234 not found in insurance_dev.db. "
            "The DB may need to be re-seeded."
        )


# ─────────────────────────────────────────────────────────────
# Step 3 — Tool functions
# Uses an in-memory DB so results are deterministic regardless of dev DB state.
# A failure here means the SQL query or tool logic is broken.
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    Session = sessionmaker(bind=e)
    session = Session()
    session.add_all([
        AutoPolicy(policy_id="A-10234", person_id="P-001", holder_name="James T.",
                   state="CA", risk_score=92, status="active",
                   start_date=date(2021, 3, 15), premium=1850.0,
                   carrier_name="GEICO",
                   expiry_date=date(2026, 3, 15),
                   renewal_status="renewed"),
        AutoPolicy(policy_id="A-10235", person_id="P-002", holder_name="Maria G.",
                   state="CA", risk_score=45, status="inactive",
                   start_date=date(2020, 7, 1), premium=1600.0,
                   carrier_name="StateFarm",
                   expiry_date=date(2026, 1, 1),
                   renewal_status="non-renewed"),
    ])
    session.commit()
    session.close()
    return e


@pytest.fixture(autouse=True)
def patch_underwriting_db(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr("tools.underwriting_tools.get_session", lambda: Session())


class TestUnderwritingTools:
    def test_get_risk_score_known_policy(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("A-10234")
        assert "error" not in result
        assert result["risk_score"] == 92

    def test_get_risk_score_returns_all_required_fields(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("A-10234")
        for field in ("policy_id", "holder_name", "state", "carrier", "risk_score", "risk_tier"):
            assert field in result, f"Missing field: {field}"

    def test_get_risk_score_tier_high(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("A-10234")  # risk_score=92
        assert result["risk_tier"] == "High"

    def test_get_risk_score_tier_low(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("A-10235")  # risk_score=45
        assert result["risk_tier"] == "Low"

    def test_get_risk_score_unknown_policy_returns_error_key(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("A-99999")
        assert "error" in result
        assert "A-99999" in result["error"]

    def test_get_risk_score_strips_whitespace(self):
        from tools.underwriting_tools import get_risk_score
        result = get_risk_score("  A-10234  ")
        assert result.get("risk_score") == 92

    def test_get_churn_rate_returns_dict(self):
        from tools.underwriting_tools import get_churn_rate
        result = get_churn_rate("carrier=StateFarm period=Q1 2026")
        assert isinstance(result, dict)

    def test_get_churn_rate_known_carrier_period(self):
        from tools.underwriting_tools import get_churn_rate
        # A-10235 is StateFarm, expires 2026-01-01, non-renewed → Q1 2026
        result = get_churn_rate("carrier=StateFarm period=Q1 2026")
        assert "message" not in result, f"Expected data, got: {result}"
        assert result["carrier"] == "StateFarm"
        assert result["not_renewed"] == 1
        assert result["total_expiring"] == 1


# ─────────────────────────────────────────────────────────────
# Step 4 — Agent initialization
# A failure here means LangChain can't wire up tools + LLM + memory.
# Uses a MagicMock LLM so no real API call is made.
# ─────────────────────────────────────────────────────────────

def _stub_llm():
    """
    A real ChatGroq instance with an invalid key.
    initialize_agent() only wires up chains — it makes NO network calls,
    so a fake key is fine for testing agent construction.
    The network call only happens on agent.run(), which we don't invoke here.
    """
    from langchain_groq import ChatGroq
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key="gsk_test_invalid_key_for_init_testing_only",
    )


class TestAgentInit:
    def test_agent_builds_without_db_url(self):
        """Agent must initialize with only the two static tools (no NL→SQL tool)."""
        from agents.underwriting_agent import build_underwriting_agent
        agent = build_underwriting_agent(db_url=None, llm=_stub_llm())
        assert agent is not None

    def test_agent_builds_with_sqlite_db_url(self):
        """Agent must initialize and attach the NL→SQL tool when db_url is given."""
        from agents.underwriting_agent import build_underwriting_agent
        agent = build_underwriting_agent(db_url="sqlite:///:memory:", llm=_stub_llm())
        tool_names = [t.name for t in agent.tools]
        assert "query_policy_db" in tool_names, (
            f"NL→SQL tool missing. Tools found: {tool_names}"
        )

    def test_agent_has_underwriting_tools(self):
        """Both static underwriting tools must be registered."""
        from agents.underwriting_agent import build_underwriting_agent
        agent = build_underwriting_agent(db_url=None, llm=_stub_llm())
        tool_names = [t.name for t in agent.tools]
        assert "get_risk_score" in tool_names
        assert "get_churn_rate" in tool_names

    def test_agent_memory_is_configured(self):
        """ConversationBufferWindowMemory must be attached."""
        from agents.underwriting_agent import build_underwriting_agent
        agent = build_underwriting_agent(db_url=None, llm=_stub_llm())
        assert agent.memory is not None


# ─────────────────────────────────────────────────────────────
# Step 5 — LLM connectivity (requires live GROQ_API_KEY + network)
# If steps 1-4 all pass, the "Connection error" originates here.
# These tests are skipped when GROQ_API_KEY is not set.
# ─────────────────────────────────────────────────────────────

GROQ_KEY = os.getenv("GROQ_API_KEY", "")

@pytest.mark.skipif(
    not (GROQ_KEY and GROQ_KEY.startswith("gsk_")),
    reason="GROQ_API_KEY not set or invalid — skipping live LLM connectivity tests"
)
class TestLLMConnectivity:
    def test_groq_client_can_invoke(self):
        """A minimal ChatGroq call must complete without ConnectionError."""
        from langchain_groq import ChatGroq
        from langchain.schema import HumanMessage
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            groq_api_key=GROQ_KEY,
        )
        response = llm.invoke([HumanMessage(content="Reply with the single word: ok")])
        assert response.content.strip().lower().startswith("ok"), (
            f"Unexpected LLM response: {response.content!r}"
        )

    def test_supervisor_agent_runs_policy_question(self):
        """Full end-to-end: supervisor must route and answer without ConnectionError."""
        from agents.supervisor_agent import SupervisorAgent
        supervisor = SupervisorAgent(db_url=REAL_DB_URL)
        result = supervisor.run("What is the risk score for policy A-10234?")
        assert "error" not in result["answer"].lower(), (
            f"Supervisor returned an error: {result['answer']}"
        )
        assert result["routed_to"] == "underwriting"
