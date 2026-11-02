"""
Underwriting tools — policy lookup, risk scoring, churn rate.
"""

from datetime import date, timedelta
from typing import Optional

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import text

from db.database import get_session


def _session():
    return get_session()


CARRIER_ALIASES = {
    "state farm": "StateFarm",
    "statefarm": "StateFarm",
    "allstate": "Allstate",
    "geico": "GEICO",
    "progressive": "Progressive",
    "nationwide": "Nationwide",
}


def normalize_carrier(carrier: str) -> str:
    return CARRIER_ALIASES.get(carrier.strip().lower(), carrier.strip())


def get_risk_score(policy_id: str) -> dict:
    session = _session()
    try:
        row = (
            session.execute(
                text(
                    "SELECT policy_id, holder_name, risk_score, state, carrier_name "
                    "FROM auto_policies WHERE policy_id = :pid"
                ),
                {"pid": policy_id.strip()},
            )
            .mappings()
            .fetchone()
        )

        if not row:
            return {"error": f"Policy {policy_id} not found."}

        return {
            "policy_id": row["policy_id"],
            "holder_name": row["holder_name"],
            "state": row["state"],
            "carrier": row["carrier_name"],
            "risk_score": row["risk_score"],
            "risk_tier": (
                "High"
                if row["risk_score"] >= 75
                else "Medium" if row["risk_score"] >= 50 else "Low"
            ),
        }
    finally:
        session.close()


_QUARTER_BOUNDS = {
    "q1": (1, 3, 31),
    "first": (1, 3, 31),
    "q2": (4, 6, 30),
    "second": (4, 6, 30),
    "q3": (7, 9, 30),
    "third": (7, 9, 30),
    "q4": (10, 12, 31),
    "fourth": (10, 12, 31),
}


def _period_bounds(quarter: Optional[str], year: Optional[int]):
    """Resolve (start, end) dates: quarter+year > year alone > trailing 90 days."""
    if quarter:
        q = quarter.strip().lower()
        for key, (sm, em, ed) in _QUARTER_BOUNDS.items():
            if key in q:
                y = year or date.today().year
                return date(y, sm, 1), date(y, em, ed)
    if year:
        return date(year, 1, 1), date(year, 12, 31)
    today = date.today()
    return today - timedelta(days=90), today


def get_churn_rate(carrier: str, quarter: Optional[str] = None, year: Optional[int] = None) -> dict:
    carrier_norm = normalize_carrier(carrier)
    start_date, end_date = _period_bounds(quarter, year)

    session = _session()
    try:
        result = (
            session.execute(
                text(
                    """
            SELECT
                carrier_name,
                COUNT(*)                                                        AS total_expiring,
                SUM(CASE WHEN renewal_status = 'non-renewed' THEN 1 ELSE 0 END) AS not_renewed,
                ROUND(
                    100.0 * SUM(CASE WHEN renewal_status = 'non-renewed' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0), 2
                )                                                               AS churn_rate_pct
            FROM auto_policies
            WHERE carrier_name = :carrier
              AND expiry_date BETWEEN :start AND :end
            GROUP BY carrier_name
        """
                ),
                {"carrier": carrier_norm, "start": start_date, "end": end_date},
            )
            .mappings()
            .fetchone()
        )

        if not result:
            return {
                "message": f"No expiring policies found for {carrier_norm} "
                f"between {start_date} and {end_date}."
            }

        return {
            "carrier": result["carrier_name"],
            "period": f"{start_date} to {end_date}",
            "total_expiring": result["total_expiring"],
            "not_renewed": result["not_renewed"],
            "churn_rate_pct": result["churn_rate_pct"],
        }
    finally:
        session.close()


def list_policies(carrier: Optional[str] = None, state: Optional[str] = None, limit: int = 10) -> list:
    """List policies, optionally filtered by carrier and/or state."""
    limit = max(1, min(limit, 50))
    where = ["1=1"]
    params = {"limit": limit}
    if carrier:
        where.append("carrier_name = :carrier")
        params["carrier"] = normalize_carrier(carrier)
    if state:
        where.append("state = :state")
        params["state"] = state.strip().upper()
    where_sql = " AND ".join(where)

    session = _session()
    try:
        rows = (
            session.execute(
                text(
                    f"""
            SELECT policy_id, holder_name, state, carrier_name, risk_score, status, premium
            FROM auto_policies
            WHERE {where_sql}
            ORDER BY policy_id
            LIMIT :limit
        """
                ),
                params,
            )
            .mappings()
            .fetchall()
        )
        return [dict(r) for r in rows]
    finally:
        session.close()


class RiskScoreInput(BaseModel):
    policy_id: str = Field(description="Policy id, e.g. 'A-10234'")


class ChurnRateInput(BaseModel):
    carrier: str = Field(
        description="Carrier name: StateFarm, GEICO, Allstate, Progressive, or Nationwide"
    )
    quarter: Optional[str] = Field(
        default=None, description="Quarter, e.g. 'Q1', 'Q2', 'Q3', 'Q4'"
    )
    year: Optional[int] = Field(default=None, description="4-digit year, e.g. 2026")


class ListPoliciesInput(BaseModel):
    carrier: Optional[str] = Field(
        default=None, description="Optional carrier name filter, e.g. GEICO, StateFarm"
    )
    state: Optional[str] = Field(default=None, description="Optional 2-letter state filter, e.g. CA")
    limit: int = Field(default=10, description="Max number of policies to return (default 10, max 50)")


UNDERWRITING_TOOLS = [
    StructuredTool.from_function(
        func=get_risk_score,
        name="get_risk_score",
        description="""Get risk score and risk tier for a specific policy.
        Use ONLY when a specific policy_id is given.
        Output: risk score (0-100) and tier (Low/Medium/High).""",
        args_schema=RiskScoreInput,
    ),
    StructuredTool.from_function(
        func=get_churn_rate,
        name="get_churn_rate",
        description="""Calculate churn or non-renewal rate for a carrier in a time period.
        Use when asked about: churn rate, attrition, non-renewal rate, retention rate.
        Defaults to the trailing 90 days when no quarter/year is given.""",
        args_schema=ChurnRateInput,
    ),
    StructuredTool.from_function(
        func=list_policies,
        name="list_policies",
        description="""List policies, optionally filtered by carrier and/or state.
        Use when asked to list, show, or sample N policies WITHOUT specific policy IDs
        given — e.g. 'show me 3 policies', 'list policies in CA', 'sample some GEICO policies'.
        Do NOT use this when a specific policy_id is already given — use get_risk_score instead.
        Output: a list of policies with policy_id, holder_name, state, carrier, risk_score,
        status, and premium.""",
        args_schema=ListPoliciesInput,
    ),
]
