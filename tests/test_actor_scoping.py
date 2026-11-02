"""
Unit tests for tools/scoped_tools.py — the carrier-account access-control boundary.

All tests run against an in-memory SQLite DB, no LLM needed. The key property under test:
a carrier actor's tools must enforce their own carrier_name in code, regardless of what
argument an (adversarial or confused) LLM tool call supplies.

Test data design
-----------------
P-SHARED  holds one GEICO policy (A-G1) and one StateFarm policy (A-S1), with one claim
          under each carrier — this is the adversarial case: a GEICO actor asking about
          P-SHARED must only ever see the GEICO claim.
P-OTHER   holds only a StateFarm policy (A-S2) with one claim — used to confirm a GEICO
          actor gets the generic "no claims found" message, not an error that reveals the
          person exists under a different carrier.
P-GEICO2  holds only a GEICO policy (A-G2), no claims — used to confirm get_person_summary
          scoped to StateFarm excludes GEICO-only persons.
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AutoPolicy, Claim
from agents.actor import Actor
from tools.scoped_tools import (
    scope_underwriting_tools,
    scope_claims_tools,
    scope_analytics_tools,
)
from tools.analytics_tools import ANALYTICS_TOOLS
from tools.underwriting_tools import UNDERWRITING_TOOLS


# ── Test DB fixture ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    Session = sessionmaker(bind=e)
    session = Session()

    session.add_all(
        [
            AutoPolicy(
                policy_id="A-G1",
                person_id="P-SHARED",
                holder_name="Shared Person",
                state="CA",
                risk_score=80,
                status="active",
                start_date=date(2022, 1, 1),
                premium=1200.0,
                carrier_name="GEICO",
            ),
            AutoPolicy(
                policy_id="A-S1",
                person_id="P-SHARED",
                holder_name="Shared Person",
                state="CA",
                risk_score=80,
                status="active",
                start_date=date(2022, 1, 1),
                premium=1300.0,
                carrier_name="StateFarm",
            ),
            AutoPolicy(
                policy_id="A-S2",
                person_id="P-OTHER",
                holder_name="Other Person",
                state="TX",
                risk_score=60,
                status="active",
                start_date=date(2022, 1, 1),
                premium=900.0,
                carrier_name="StateFarm",
            ),
            AutoPolicy(
                policy_id="A-G2",
                person_id="P-GEICO2",
                holder_name="Geico Only Person",
                state="FL",
                risk_score=40,
                status="active",
                start_date=date(2022, 1, 1),
                premium=700.0,
                carrier_name="GEICO",
            ),
        ]
    )
    session.add_all(
        [
            Claim(
                claim_id="C-G1",
                policy_id="A-G1",
                person_id="P-SHARED",
                claim_date=date(2024, 1, 1),
                claim_type="Collision",
                amount=1000,
                status="Closed",
                carrier_name="GEICO",
            ),
            Claim(
                claim_id="C-S1",
                policy_id="A-S1",
                person_id="P-SHARED",
                claim_date=date(2024, 6, 1),
                claim_type="Theft",
                amount=2000,
                status="Open",
                carrier_name="StateFarm",
            ),
            Claim(
                claim_id="C-S2",
                policy_id="A-S2",
                person_id="P-OTHER",
                claim_date=date(2024, 3, 1),
                claim_type="Liability",
                amount=3000,
                status="Open",
                carrier_name="StateFarm",
            ),
        ]
    )
    session.commit()
    session.close()
    return e


@pytest.fixture(autouse=True)
def patch_db(engine, monkeypatch):
    """Redirect get_session() in every module scoped_tools.py calls through."""
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("tools.scoped_tools.get_session", lambda: Session())
    monkeypatch.setattr("tools.underwriting_tools.get_session", lambda: Session())
    monkeypatch.setattr("tools.claims_tools.get_session", lambda: Session())
    monkeypatch.setattr("tools.analytics_tools.get_session", lambda: Session())


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


# ── get_claims_by_person ─────────────────────────────────────────────────────


class TestScopedGetClaimsByPerson:
    def test_adversarial_person_returns_only_own_carrier_claims(self):
        """P-SHARED has claims under both GEICO and StateFarm — a GEICO actor must only
        ever see the GEICO one, even though the person_id itself is a valid argument."""
        tools = scope_claims_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "get_claims_by_person").func(person_id="P-SHARED")

        assert result["total_claims"] == 1
        assert result["claims"][0]["claim_id"] == "C-G1"
        assert result["total_amount"] == 1000

    def test_person_with_no_claims_under_own_carrier_gets_generic_message(self):
        """P-OTHER only has a StateFarm claim — a GEICO actor must get the same generic
        'no claims found' message a real miss would produce, not a different error that
        would confirm the person exists under a competitor."""
        tools = scope_claims_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "get_claims_by_person").func(person_id="P-OTHER")

        assert "message" in result
        assert "No claims found" in result["message"]

    def test_own_carrier_data_is_returned_in_full(self):
        tools = scope_claims_tools(Actor.carrier("StateFarm"))
        result = _tool(tools, "get_claims_by_person").func(person_id="P-SHARED")

        assert result["total_claims"] == 1
        assert result["claims"][0]["claim_id"] == "C-S1"


# ── flag_fraud_risk ───────────────────────────────────────────────────────────


class TestScopedFlagFraudRisk:
    def test_fraud_score_computed_only_from_own_carrier_claims(self):
        """P-SHARED has 1 claim under each carrier; fraud scoring for a GEICO actor must
        be based on the 1 GEICO claim only, not both."""
        tools = scope_claims_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "flag_fraud_risk").func(person_id="P-SHARED")

        assert result["total_claims"] == 1
        assert result["total_amount"] == 1000


# ── get_risk_score ────────────────────────────────────────────────────────────


class TestScopedGetRiskScore:
    def test_own_carrier_policy_returns_real_data(self):
        tools = scope_underwriting_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "get_risk_score").func(policy_id="A-G1")

        assert result["risk_score"] == 80
        assert "error" not in result

    def test_other_carrier_policy_refused_like_a_real_miss(self):
        """A-S2 belongs to StateFarm — a GEICO actor must get the exact same shape a
        genuinely nonexistent policy_id would produce."""
        tools = scope_underwriting_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "get_risk_score").func(policy_id="A-S2")

        assert result == {"error": "Policy A-S2 not found."}

    def test_churn_rate_tool_is_passed_through_unwrapped(self):
        """get_churn_rate is an aggregate rate, not an individual record — confirm it's
        literally the same tool object staff gets, not accidentally missed from wrapping."""
        tools = scope_underwriting_tools(Actor.carrier("GEICO"))
        staff_tool = _tool(UNDERWRITING_TOOLS, "get_churn_rate")
        scoped_tool = _tool(tools, "get_churn_rate")

        assert scoped_tool is staff_tool


# ── list_policies ─────────────────────────────────────────────────────────────


class TestScopedListPolicies:
    def test_adversarial_carrier_argument_is_ignored(self):
        """A GEICO actor passing carrier='StateFarm' must still only get GEICO
        policies back — the argument is forced server-side, not trusted from the LLM."""
        tools = scope_underwriting_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "list_policies").func(carrier="StateFarm", limit=10)

        assert len(result) > 0
        assert all(row["carrier_name"] == "GEICO" for row in result)

    def test_no_carrier_argument_still_scopes_to_own_carrier(self):
        """The whole point of the bug report this fixes: 'show me 3 policies' with
        no carrier mentioned at all must still only return the actor's own carrier."""
        tools = scope_underwriting_tools(Actor.carrier("StateFarm"))
        result = _tool(tools, "list_policies").func(limit=3)

        assert 0 < len(result) <= 3
        assert all(row["carrier_name"] == "StateFarm" for row in result)


# ── find_frequent_claimants ───────────────────────────────────────────────────


class TestScopedFindFrequentClaimants:
    def test_adversarial_carrier_argument_is_ignored(self):
        """A StateFarm actor passing carrier='GEICO' must still only get StateFarm
        claimants back — the argument is forced server-side, not trusted from the LLM."""
        tools = scope_claims_tools(Actor.carrier("StateFarm"))
        result = _tool(tools, "find_frequent_claimants").func(
            min_claims=1, years=5, carrier="GEICO"
        )

        assert len(result) > 0
        assert all(row["carrier_name"] == "StateFarm" for row in result)


# ── list_claims ───────────────────────────────────────────────────────────────


class TestScopedListClaims:
    def test_adversarial_carrier_argument_is_ignored(self):
        """A GEICO actor passing carrier='StateFarm' must still only get the
        GEICO claim back — the argument is forced server-side, not trusted
        from the LLM. Also the original bug report's shape: filtering by year."""
        tools = scope_claims_tools(Actor.carrier("GEICO"))
        result = _tool(tools, "list_claims").func(carrier="StateFarm", year=2024)

        assert len(result) == 1
        assert result[0]["claim_id"] == "C-G1"

    def test_no_carrier_argument_still_scopes_to_own_carrier(self):
        """StateFarm has two claims in the fixture (C-S1 via P-SHARED, C-S2 via
        P-OTHER) — both must come back, and nothing from GEICO."""
        tools = scope_claims_tools(Actor.carrier("StateFarm"))
        result = _tool(tools, "list_claims").func(year=2024)

        claim_ids = {row["claim_id"] for row in result}
        assert claim_ids == {"C-S1", "C-S2"}
        assert all(row["carrier_name"] == "StateFarm" for row in result)


# ── get_person_summary ────────────────────────────────────────────────────────


class TestScopedGetPersonSummary:
    def test_only_own_carrier_persons_are_listed(self):
        tools = scope_analytics_tools(Actor.carrier("StateFarm"))
        result = _tool(tools, "get_person_summary").func()

        person_ids = {row["person_id"] for row in result}
        assert "P-SHARED" in person_ids  # has a StateFarm policy
        assert "P-OTHER" in person_ids  # StateFarm-only
        assert "P-GEICO2" not in person_ids  # GEICO-only, must be excluded

    def test_other_open_analytics_tools_are_passed_through_unwrapped(self):
        """get_loss_ratio, get_claims_trend, get_portfolio_summary, get_carrier_summary,
        get_carrier_claims_summary are aggregate-only — confirm they're the exact same
        tool objects staff gets, deliberately left open rather than accidentally missed."""
        tools = scope_analytics_tools(Actor.carrier("StateFarm"))
        for name in (
            "get_loss_ratio",
            "get_claims_trend",
            "get_portfolio_summary",
            "get_carrier_summary",
            "get_carrier_claims_summary",
        ):
            assert _tool(tools, name) is _tool(ANALYTICS_TOOLS, name)
