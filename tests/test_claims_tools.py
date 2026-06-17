"""
Unit tests for tools/claims_tools.py.

All tests run against an in-memory SQLite DB — no live database or LLM needed.
The DB is seeded once per test session via the `engine` fixture; each test gets
a fresh session via the `patch_db` fixture that monkeypatches get_session.

Test data design
----------------
P-HIGH  4 claims, $35k total, 2 open  → fraud score 7 → High
P-MED   2 claims, $7k total,  2 open  → fraud score 3 → Medium
P-LOW   no claims                      → fraud score 0 → Low
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AutoPolicy, Claim
from tools.claims_tools import get_claims_by_person, find_frequent_claimants, flag_fraud_risk
from agents.supervisor_agent import _keyword_route


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
                policy_id="T-001",
                person_id="P-HIGH",
                holder_name="High Risk",
                state="CA",
                risk_score=90,
                status="active",
                start_date=date(2020, 1, 1),
                premium=1500.0,
                carrier_name="Geico",
            ),
            AutoPolicy(
                policy_id="T-002",
                person_id="P-MED",
                holder_name="Med Risk",
                state="TX",
                risk_score=60,
                status="active",
                start_date=date(2020, 1, 1),
                premium=1000.0,
                carrier_name="StateFarm",
            ),
            AutoPolicy(
                policy_id="T-003",
                person_id="P-LOW",
                holder_name="Low Risk",
                state="FL",
                risk_score=30,
                status="active",
                start_date=date(2020, 1, 1),
                premium=700.0,
                carrier_name="Allstate",
            ),
        ]
    )

    # P-HIGH: 4 claims within last 3 years, $35k total, 2 open
    session.add_all(
        [
            Claim(
                claim_id="TC-001",
                policy_id="T-001",
                person_id="P-HIGH",
                claim_date=date(2024, 1, 1),
                claim_type="Collision",
                amount=12000,
                status="Open",
            ),
            Claim(
                claim_id="TC-002",
                policy_id="T-001",
                person_id="P-HIGH",
                claim_date=date(2024, 6, 1),
                claim_type="Theft",
                amount=10000,
                status="Open",
            ),
            Claim(
                claim_id="TC-003",
                policy_id="T-001",
                person_id="P-HIGH",
                claim_date=date(2025, 1, 1),
                claim_type="Liability",
                amount=8000,
                status="Closed",
            ),
            Claim(
                claim_id="TC-004",
                policy_id="T-001",
                person_id="P-HIGH",
                claim_date=date(2025, 6, 1),
                claim_type="Weather",
                amount=5000,
                status="Closed",
            ),
            # P-MED: 2 claims, 2 open → score 3 → Medium
            Claim(
                claim_id="TC-005",
                policy_id="T-002",
                person_id="P-MED",
                claim_date=date(2025, 3, 1),
                claim_type="Collision",
                amount=4000,
                status="Open",
            ),
            Claim(
                claim_id="TC-006",
                policy_id="T-002",
                person_id="P-MED",
                claim_date=date(2025, 9, 1),
                claim_type="Liability",
                amount=3000,
                status="Open",
            ),
            # P-LOW: no claims seeded
        ]
    )
    session.commit()
    session.close()
    return e


@pytest.fixture(autouse=True)
def patch_db(engine, monkeypatch):
    """Redirect all get_session() calls inside claims_tools to the test DB."""
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("tools.claims_tools.get_session", lambda: Session())


# ── get_claims_by_person ─────────────────────────────────────────────────────


class TestGetClaimsByPerson:
    def test_known_person_returns_dict_with_claims(self):
        result = get_claims_by_person("P-HIGH")
        assert isinstance(result, dict)
        assert "claims" in result

    def test_known_person_claim_count(self):
        result = get_claims_by_person("P-HIGH")
        assert result["total_claims"] == 4

    def test_known_person_total_amount(self):
        result = get_claims_by_person("P-HIGH")
        assert result["total_amount"] == pytest.approx(35000)

    def test_claim_fields_present(self):
        result = get_claims_by_person("P-HIGH")
        claim = result["claims"][0]
        assert all(k in claim for k in ("claim_id", "date", "type", "amount", "status"))

    def test_unknown_person_returns_message(self):
        result = get_claims_by_person("P-NOBODY")
        assert "message" in result
        assert "P-NOBODY" in result["message"]

    def test_strips_whitespace_from_input(self):
        result = get_claims_by_person("  P-HIGH  ")
        assert result["total_claims"] == 4


# ── find_frequent_claimants ──────────────────────────────────────────────────


class TestFindFrequentClaimants:
    def test_returns_list(self):
        result = find_frequent_claimants("min_claims=1 years=5")
        assert isinstance(result, list)

    def test_min_claims_2_returns_both(self):
        result = find_frequent_claimants("min_claims=2 years=5")
        ids = {r["person_id"] for r in result}
        assert "P-HIGH" in ids
        assert "P-MED" in ids

    def test_min_claims_4_returns_only_high(self):
        result = find_frequent_claimants("min_claims=4 years=5")
        ids = {r["person_id"] for r in result}
        assert "P-HIGH" in ids
        assert "P-MED" not in ids

    def test_fraud_flag_set_for_3_plus_claims(self):
        result = find_frequent_claimants("min_claims=1 years=5")
        high = next(r for r in result if r["person_id"] == "P-HIGH")
        assert high["fraud_flag"] is True

    def test_fraud_flag_not_set_for_2_claims(self):
        result = find_frequent_claimants("min_claims=1 years=5")
        med = next(r for r in result if r["person_id"] == "P-MED")
        assert med["fraud_flag"] is False

    def test_carrier_filter_returns_only_matching_carrier(self):
        # P-HIGH is Geico, P-MED is StateFarm — carrier=Geico should return only P-HIGH
        result = find_frequent_claimants("carrier=Geico min_claims=1 years=5")
        ids = {r["person_id"] for r in result}
        assert "P-HIGH" in ids
        assert "P-MED" not in ids

    def test_carrier_filter_case_insensitive(self):
        result_upper = find_frequent_claimants("carrier=GEICO min_claims=1 years=5")
        result_lower = find_frequent_claimants("carrier=geico min_claims=1 years=5")
        assert {r["person_id"] for r in result_upper} == {r["person_id"] for r in result_lower}

    def test_no_carrier_filter_returns_all_carriers(self):
        result = find_frequent_claimants("min_claims=1 years=5")
        ids = {r["person_id"] for r in result}
        assert "P-HIGH" in ids and "P-MED" in ids

    def test_carrier_name_in_result(self):
        result = find_frequent_claimants("min_claims=1 years=5")
        high = next(r for r in result if r["person_id"] == "P-HIGH")
        assert high["carrier_name"] == "Geico"


# ── flag_fraud_risk ──────────────────────────────────────────────────────────


class TestFlagFraudRisk:
    def test_high_risk_score(self):
        # P-HIGH: 4 claims (+3) + $35k>$30k (+2) + 2 open claims (+2) = score 7
        result = flag_fraud_risk("P-HIGH")
        assert result["fraud_risk"] == "High"
        assert result["score"] >= 4

    def test_medium_risk_score(self):
        # P-MED: 2 claims (+1) + 2 open claims (+2) = score 3 → Medium
        result = flag_fraud_risk("P-MED")
        assert result["fraud_risk"] == "Medium"

    def test_low_risk_for_no_claims(self):
        result = flag_fraud_risk("P-LOW")
        assert result["fraud_risk"] == "Low"

    def test_high_risk_recommends_siu(self):
        result = flag_fraud_risk("P-HIGH")
        assert "SIU" in result["recommendation"]

    def test_result_has_required_fields(self):
        result = flag_fraud_risk("P-HIGH")
        assert all(
            k in result
            for k in (
                "person_id",
                "fraud_risk",
                "score",
                "total_claims",
                "total_amount",
                "reasons",
                "recommendation",
            )
        )

    def test_unknown_person_returns_low(self):
        result = flag_fraud_risk("P-NOBODY")
        assert result["fraud_risk"] == "Low"


# ── Routing: claims frequency for Geico ─────────────────────────────────────


class TestRoutingForGeico:
    def test_geico_frequency_routes_to_claims(self):
        """
        "claims frequency for Geico" should route to claims because the question
        asks about claims data. Carrier names are no longer routing keywords, so
        'Geico' does not push the score toward underwriting. Claims wins on
        'claim' + 'claims' + 'claim frequency' keywords, and the claims tool
        now supports carrier filtering so the answer is complete and correct.
        """
        result = _keyword_route("what is the claims frequency for Geico from 2025 to 2026?")
        assert result == "claims"

    def test_carrier_name_alone_does_not_route_to_underwriting(self):
        """Carrier names should never be the deciding routing signal."""
        # No policy/underwriting concept — just a carrier name → LLM decides (None)
        result = _keyword_route("tell me about Geico")
        assert result is None  # tie or no match → falls to LLM

    def test_pure_claims_question_routes_to_claims(self):
        assert _keyword_route("claims history for person P-001") == "claims"

    def test_pure_underwriting_question_routes_correctly(self):
        assert _keyword_route("what is the risk score for policy A-10234") == "underwriting"

    def test_trend_question_routes_to_analytics(self):
        assert _keyword_route("show me the quarterly loss ratio trend") == "analytics"
