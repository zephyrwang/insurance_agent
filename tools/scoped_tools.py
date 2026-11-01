"""
Carrier-scoped tool wrappers.

For a carrier actor, every tool here must either:
  (a) refuse/filter based on the actor's OWN carrier_name, enforced in code — never by asking
      the LLM to pass the "right" argument, since the LLM's tool call can't be trusted, or
  (b) be passed through completely unmodified, for tools that only ever return aggregate
      numbers (loss ratio, churn rate, portfolio/claims trend, carrier breakdowns) rather than
      an individually identifiable record — those are intentionally left open to any carrier
      actor (cross-carrier benchmarking is in scope; cross-carrier individual records are not).

Only five tools need wrapping: get_risk_score, get_claims_by_person, flag_fraud_risk,
find_frequent_claimants, get_person_summary. Everything else a carrier actor gets is the exact
same tool object a staff actor gets.
"""

from datetime import date, timedelta
from typing import Optional

from langchain.tools import StructuredTool, Tool
from langchain_core.pydantic_v1 import BaseModel, Field
from sqlalchemy import text

from agents.actor import Actor
from db.database import get_session
from tools.claims_tools import (
    CLAIMS_TOOLS,
    PersonIdInput,
    FrequentClaimantsInput,
    _assess_fraud_risk,
    find_frequent_claimants,
)
from tools.underwriting_tools import (
    UNDERWRITING_TOOLS,
    RiskScoreInput,
    get_risk_score,
    normalize_carrier,
)
from tools.analytics_tools import ANALYTICS_TOOLS


def _get_claims_by_person_for_carrier(person_id: str, carrier_name: str) -> dict:
    """Same shape as tools.claims_tools.get_claims_by_person, filtered to one carrier."""
    session = get_session()
    cutoff = date.today() - timedelta(days=3 * 365)
    try:
        rows = (
            session.execute(
                text(
                    """
            SELECT claim_id, policy_id, claim_date, claim_type, amount, status
            FROM claims
            WHERE person_id    = :pid
              AND carrier_name = :carrier
              AND claim_date  >= :cutoff
            ORDER BY claim_date DESC
        """
                ),
                {
                    "pid": person_id.strip(),
                    "carrier": carrier_name,
                    "cutoff": cutoff,
                },
            )
            .mappings()
            .fetchall()
        )

        if not rows:
            return {"message": f"No claims found for person {person_id} in the past 3 years."}

        return {
            "person_id": person_id,
            "period": f"{cutoff} to {date.today()}",
            "total_claims": len(rows),
            "total_amount": sum(r["amount"] for r in rows),
            "claims": [
                {
                    "claim_id": r["claim_id"],
                    "policy_id": r["policy_id"],
                    "date": str(r["claim_date"]),
                    "type": r["claim_type"],
                    "amount": r["amount"],
                    "status": r["status"],
                }
                for r in rows
            ],
        }
    finally:
        session.close()


def _get_person_summary_for_carrier(carrier_name: str) -> list:
    """Same shape as tools.analytics_tools.get_person_summary, filtered to one carrier."""
    session = get_session()
    try:
        rows = (
            session.execute(
                text(
                    """
            SELECT
                p.person_id,
                MAX(p.holder_name)                                              AS holder_name,
                MAX(p.state)                                                    AS state,
                COUNT(DISTINCT p.policy_id)                                     AS policy_count,
                ROUND(SUM(p.premium), 2)                                        AS total_premium,
                MAX(p.risk_score)                                               AS max_risk_score,
                CASE WHEN MAX(p.risk_score) >= 75 THEN '🔴 High'
                     WHEN MAX(p.risk_score) >= 50 THEN '🟡 Medium'
                     ELSE '🟢 Low' END                                          AS risk_tier,
                COALESCE(MAX(c.claims_count), 0)                                AS claims_count,
                ROUND(COALESCE(MAX(c.total_amount), 0), 2)                      AS total_claims,
                ROUND(
                    100.0 * COALESCE(MAX(c.closed_amount), 0)
                    / NULLIF(SUM(p.premium), 0), 2
                )                                                               AS loss_ratio_pct,
                CASE WHEN COALESCE(MAX(c.claims_count), 0) >= 4 THEN '🔴 High'
                     WHEN COALESCE(MAX(c.claims_count), 0) >= 2 THEN '🟡 Medium'
                     ELSE '🟢 Low' END                                          AS fraud_flag
            FROM auto_policies p
            LEFT JOIN (
                SELECT
                    person_id,
                    COUNT(claim_id) AS claims_count,
                    SUM(amount)     AS total_amount,
                    SUM(CASE WHEN status = 'Closed' THEN amount ELSE 0 END) AS closed_amount
                FROM claims
                WHERE carrier_name = :carrier
                GROUP BY person_id
            ) c ON c.person_id = p.person_id
            WHERE p.status = 'active'
              AND p.carrier_name = :carrier
            GROUP BY p.person_id
            ORDER BY total_claims DESC
        """
                ),
                {"carrier": carrier_name},
            )
            .mappings()
            .fetchall()
        )

        return [dict(r) for r in rows]
    finally:
        session.close()


def scope_underwriting_tools(actor: Actor) -> list:
    """Underwriting toolset for a carrier actor: get_risk_score is own-carrier-only,
    get_churn_rate is passed through unchanged (an aggregate rate, not a record)."""

    def _scoped_get_risk_score(policy_id: str) -> dict:
        result = get_risk_score(policy_id)
        if "error" in result:
            return result
        if normalize_carrier(result.get("carrier") or "") != normalize_carrier(
            actor.carrier_name
        ):
            # Same shape as a real miss — don't confirm the policy exists under another carrier.
            return {"error": f"Policy {policy_id} not found."}
        return result

    scoped_risk_score = StructuredTool.from_function(
        func=_scoped_get_risk_score,
        name="get_risk_score",
        description="""Get risk score and risk tier for a specific policy.
        Output: risk score (0-100) and tier (Low/Medium/High).""",
        args_schema=RiskScoreInput,
    )

    churn_rate_tool = next(t for t in UNDERWRITING_TOOLS if t.name == "get_churn_rate")
    return [scoped_risk_score, churn_rate_tool]


def scope_claims_tools(actor: Actor) -> list:
    """Claims toolset for a carrier actor: person-level tools are own-carrier-only;
    find_frequent_claimants is forced to the actor's own carrier."""

    def _scoped_get_claims_by_person(person_id: str) -> dict:
        return _get_claims_by_person_for_carrier(person_id, actor.carrier_name)

    def _scoped_flag_fraud_risk(person_id: str) -> dict:
        return _assess_fraud_risk(
            person_id, _get_claims_by_person_for_carrier(person_id, actor.carrier_name)
        )

    def _scoped_find_frequent_claimants(
        min_claims: int = 2, years: int = 1, carrier: Optional[str] = None
    ) -> list:
        # Ignore whatever carrier the LLM passed — always force the actor's own.
        return find_frequent_claimants(
            min_claims=min_claims, years=years, carrier=actor.carrier_name
        )

    return [
        StructuredTool.from_function(
            func=_scoped_get_claims_by_person,
            name="get_claims_by_person",
            description="""Get full claims history for ONE specific person, limited to claims
            under your own carrier.
            Use when a person_id is mentioned (e.g. 'claims for P-001', 'history for P-003').
            Do NOT use this to find multiple persons or list all claimants.
            Output: list of claims with dates, types, amounts, and statuses.""",
            args_schema=PersonIdInput,
        ),
        StructuredTool.from_function(
            func=_scoped_find_frequent_claimants,
            name="find_frequent_claimants",
            description="""Find ALL persons under your own carrier who have filed multiple claims.
            Use when asked to LIST or FIND persons with N or more claims — e.g.:
            'find all persons with 2 or more claims', 'who has multiple claims', 'frequent claimants'.
            Output: ranked list of matching persons (your carrier only) with claim counts and fraud flags.""",
            args_schema=FrequentClaimantsInput,
        ),
        StructuredTool.from_function(
            func=_scoped_flag_fraud_risk,
            name="flag_fraud_risk",
            description="""Assess fraud risk score for ONE specific person, based only on claims
            under your own carrier.
            Use ONLY when a specific person_id is given AND fraud/risk is asked about.
            Do NOT use this to find multiple persons or answer listing questions.
            Output: fraud risk level (Low/Medium/High), score, and recommendation.""",
            args_schema=PersonIdInput,
        ),
    ]


def scope_analytics_tools(actor: Actor) -> list:
    """Analytics toolset for a carrier actor: get_person_summary is own-carrier-only
    (individual policyholder detail); every other analytics tool is passed through
    unchanged since it only ever returns aggregate counts/trends, not individual records."""

    def _scoped_get_person_summary(input_str: str = "") -> list:
        return _get_person_summary_for_carrier(actor.carrier_name)

    scoped_person_summary = Tool(
        name="get_person_summary",
        func=_scoped_get_person_summary,
        description="""Get a combined per-person summary across policies and claims, limited to
        your own carrier's policyholders.
        Use when asked to list persons/customers with their policy count, premiums, claims, loss
        ratio, risk score, or fraud flag.
        No input required.
        Output: one row per person with policy_count, total_premium, risk_tier, claims_count,
        total_claims, loss_ratio_pct, fraud_flag.""",
    )

    passthrough = [t for t in ANALYTICS_TOOLS if t.name != "get_person_summary"]
    return passthrough + [scoped_person_summary]
