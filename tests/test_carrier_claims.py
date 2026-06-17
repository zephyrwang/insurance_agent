"""
Tests for the carrier claims summary feature:
  1. Routing — "list all insurance companies with number of claims" must go to analytics
  2. get_carrier_claims_summary tool — correct aggregation against an in-memory DB
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AutoPolicy, Claim
from agents.supervisor_agent import _keyword_route, ROUTING_RULES


# ── In-memory test DB ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    Session = sessionmaker(bind=e)
    session = Session()

    session.add_all(
        [
            AutoPolicy(
                policy_id="C-001",
                person_id="P-A",
                holder_name="Alice",
                state="CA",
                risk_score=70,
                status="active",
                start_date=date(2023, 1, 1),
                premium=1200.0,
                carrier_name="GEICO",
            ),
            AutoPolicy(
                policy_id="C-002",
                person_id="P-B",
                holder_name="Bob",
                state="TX",
                risk_score=55,
                status="active",
                start_date=date(2023, 1, 1),
                premium=900.0,
                carrier_name="StateFarm",
            ),
            AutoPolicy(
                policy_id="C-003",
                person_id="P-C",
                holder_name="Carol",
                state="FL",
                risk_score=40,
                status="active",
                start_date=date(2023, 1, 1),
                premium=700.0,
                carrier_name="GEICO",
            ),
        ]
    )
    session.add_all(
        [
            # GEICO: 2 claims in 2024, 1 in 2025
            Claim(
                claim_id="X-001",
                policy_id="C-001",
                person_id="P-A",
                claim_date=date(2024, 3, 1),
                claim_type="Collision",
                amount=5000,
                status="Closed",
            ),
            Claim(
                claim_id="X-002",
                policy_id="C-003",
                person_id="P-C",
                claim_date=date(2024, 7, 1),
                claim_type="Theft",
                amount=3000,
                status="Closed",
            ),
            Claim(
                claim_id="X-003",
                policy_id="C-001",
                person_id="P-A",
                claim_date=date(2025, 2, 1),
                claim_type="Liability",
                amount=4000,
                status="Open",
            ),
            # StateFarm: 1 claim in 2025
            Claim(
                claim_id="X-004",
                policy_id="C-002",
                person_id="P-B",
                claim_date=date(2025, 6, 1),
                claim_type="Weather",
                amount=2000,
                status="Closed",
            ),
        ]
    )
    session.commit()
    session.close()
    return e


@pytest.fixture(autouse=True)
def patch_analytics_db(engine, monkeypatch):
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("tools.analytics_tools.get_session", lambda: Session())


# ── Routing tests ────────────────────────────────────────────────────────────


class TestCarrierClaimsRouting:
    QUESTION = "List all insurance companies with the number of claims in 2024, 2025, 2026"

    def test_routes_to_analytics(self):
        assert _keyword_route(self.QUESTION) == "analytics"

    def test_does_not_route_to_claims(self):
        assert _keyword_route(self.QUESTION) != "claims"

    def test_analytics_keywords_fire(self):
        q = self.QUESTION.lower()
        matched = [kw for kw in ROUTING_RULES["analytics"] if kw in q]
        assert matched, f"No analytics keywords matched: {ROUTING_RULES['analytics']}"

    def test_claims_keywords_do_not_fire(self):
        q = self.QUESTION.lower()
        matched = [kw for kw in ROUTING_RULES["claims"] if kw in q]
        assert not matched, f"Claims keywords unexpectedly matched: {matched}"

    def test_geico_claims_routes_to_analytics(self):
        """Carrier-level claim count query → analytics regardless of carrier name."""
        assert _keyword_route("how many claims did Geico have in 2025?") == "analytics"

    def test_person_claims_still_routes_to_claims(self):
        """Person-level claim history must still go to claims agent."""
        assert _keyword_route("show claims history for person P-001") == "claims"

    def test_frequent_claimants_still_routes_to_claims(self):
        assert _keyword_route("find all frequent claimants with 2 or more claims") == "claims"


# ── get_carrier_claims_summary tool tests ────────────────────────────────────


class TestGetCarrierClaimsSummary:
    def test_returns_list(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        assert isinstance(result, list)

    def test_one_row_per_carrier(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        carriers = [r["carrier_name"] for r in result]
        assert "GEICO" in carriers
        assert "StateFarm" in carriers

    def test_geico_2024_claim_count(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        geico = next(r for r in result if r["carrier_name"] == "GEICO")
        assert geico["2024_claims"] == 2

    def test_geico_2025_claim_count(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        geico = next(r for r in result if r["carrier_name"] == "GEICO")
        assert geico["2025_claims"] == 1

    def test_geico_2026_claim_count_zero(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        geico = next(r for r in result if r["carrier_name"] == "GEICO")
        assert geico["2026_claims"] == 0

    def test_statefarm_2025_claim_count(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        sf = next(r for r in result if r["carrier_name"] == "StateFarm")
        assert sf["2025_claims"] == 1

    def test_total_claims_correct(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        geico = next(r for r in result if r["carrier_name"] == "GEICO")
        assert geico["total_claims"] == 3  # 2 in 2024 + 1 in 2025

    def test_amount_columns_present(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        row = result[0]
        assert "2024_amount" in row and "2025_amount" in row and "2026_amount" in row

    def test_geico_2024_amount(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        geico = next(r for r in result if r["carrier_name"] == "GEICO")
        assert geico["2024_amount"] == pytest.approx(8000)  # 5000 + 3000

    def test_ordered_by_total_claims_desc(self):
        """GEICO (3 total) must appear before StateFarm (1 total)."""
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("2024 2025 2026")
        carriers = [r["carrier_name"] for r in result]
        assert carriers.index("GEICO") < carriers.index("StateFarm")

    def test_defaults_to_2024_2025_2026_when_no_years_given(self):
        from tools.analytics_tools import get_carrier_claims_summary

        result = get_carrier_claims_summary("")
        row = result[0]
        assert "2024_claims" in row and "2025_claims" in row and "2026_claims" in row
