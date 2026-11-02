"""
Analytics tools — loss ratio, trend analysis, portfolio summary.
"""

from datetime import date, timedelta
from typing import List, Optional

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import text

from db.database import get_session
from tools.underwriting_tools import normalize_carrier


def _session():
    return get_session()


def get_loss_ratio(
    carrier: Optional[str] = None, state: Optional[str] = None, year: Optional[int] = None
) -> dict:
    carrier_norm = normalize_carrier(carrier) if carrier else None
    state_norm = state.strip().upper() if state else None

    policy_where = ["1=1"]
    claim_where = ["c.status = 'Closed'"]
    params = {}

    if carrier_norm:
        policy_where.append("p.carrier_name = :carrier")
        params["carrier"] = carrier_norm
    if state_norm:
        policy_where.append("p.state = :state")
        params["state"] = state_norm
    if year:
        # Filter claims to that year
        claim_where.append("strftime('%Y', c.claim_date) = :year")
        # Filter policies active during that year (start_date <= year-end AND expiry_date >= year-start)
        policy_where.append("strftime('%Y', p.start_date) <= :year")
        policy_where.append("(p.expiry_date IS NULL OR strftime('%Y', p.expiry_date) >= :year)")
        params["year"] = str(year)

    pw = " AND ".join(policy_where)
    cw = " AND ".join(claim_where)

    session = _session()
    try:
        # Claims are pre-aggregated per policy so a policy with N claims
        # contributes its premium once, not N times.
        result = (
            session.execute(
                text(
                    f"""
            SELECT
                SUM(p.premium)                  AS total_premium,
                SUM(COALESCE(cl.claims_amt, 0)) AS total_claims,
                ROUND(
                    100.0 * SUM(COALESCE(cl.claims_amt, 0)) / NULLIF(SUM(p.premium), 0), 2
                )                               AS loss_ratio_pct
            FROM auto_policies p
            LEFT JOIN (
                SELECT c.policy_id, SUM(c.amount) AS claims_amt
                FROM claims c
                WHERE {cw}
                GROUP BY c.policy_id
            ) cl ON cl.policy_id = p.policy_id
            WHERE {pw}
        """
                ),
                params,
            )
            .mappings()
            .fetchone()
        )

        loss_ratio = result["loss_ratio_pct"] or 0
        period = str(year) if year else "All time"
        return {
            "carrier": carrier_norm or "All",
            "state": state_norm or "All",
            "period": period,
            "total_premium": round(result["total_premium"] or 0, 2),
            "total_claims": round(result["total_claims"] or 0, 2),
            "loss_ratio_pct": loss_ratio,
            "assessment": (
                "Unprofitable"
                if loss_ratio > 100
                else "Borderline" if loss_ratio > 70 else "Healthy"
            ),
        }
    finally:
        session.close()


def get_portfolio_summary() -> dict:
    session = _session()
    try:
        policies = (
            session.execute(
                text(
                    """
            SELECT
                COUNT(*)                  AS total_policies,
                SUM(premium)              AS total_premium,
                AVG(risk_score)           AS avg_risk_score,
                COUNT(DISTINCT person_id) AS unique_persons
            FROM auto_policies
            WHERE status = 'active'
        """
                )
            )
            .mappings()
            .fetchone()
        )

        claims = (
            session.execute(
                text(
                    """
            SELECT
                COUNT(*)    AS total_claims,
                SUM(amount) AS total_claims_amount,
                AVG(amount) AS avg_claim_amount
            FROM claims
            WHERE claim_date >= :cutoff
        """
                ),
                {"cutoff": date.today() - timedelta(days=365)},
            )
            .mappings()
            .fetchone()
        )

        by_state = (
            session.execute(
                text(
                    """
            SELECT state, COUNT(*) AS cnt
            FROM auto_policies
            WHERE status = 'active'
            GROUP BY state
            ORDER BY cnt DESC
            LIMIT 5
        """
                )
            )
            .mappings()
            .fetchall()
        )

        return {
            "active_policies": policies["total_policies"],
            "unique_persons": policies["unique_persons"],
            "total_premium": round(policies["total_premium"] or 0, 2),
            "avg_risk_score": round(policies["avg_risk_score"] or 0, 1),
            "claims_last_year": claims["total_claims"],
            "claims_amount": round(claims["total_claims_amount"] or 0, 2),
            "avg_claim_amount": round(claims["avg_claim_amount"] or 0, 2),
            "top_states": [{"state": r["state"], "policies": r["cnt"]} for r in by_state],
        }
    finally:
        session.close()


def get_claims_trend(state: Optional[str] = None, carrier: Optional[str] = None) -> list:
    state_norm = state.strip().upper() if state else None
    carrier_norm = normalize_carrier(carrier) if carrier else None

    where_clauses = ["c.claim_date >= :cutoff"]
    params = {"cutoff": date.today() - timedelta(days=365)}
    if state_norm:
        where_clauses.append("p.state = :state")
        params["state"] = state_norm
    if carrier_norm:
        where_clauses.append("p.carrier_name = :carrier")
        params["carrier"] = carrier_norm

    where = " AND ".join(where_clauses)
    session = _session()
    try:
        # strftime works for SQLite; swap to DATE_FORMAT for MySQL
        rows = (
            session.execute(
                text(
                    f"""
            SELECT
                strftime('%Y-%m', c.claim_date) AS month,
                COUNT(*)                        AS claim_count,
                SUM(c.amount)                   AS total_amount
            FROM claims c
            JOIN auto_policies p ON c.policy_id = p.policy_id
            WHERE {where}
            GROUP BY month
            ORDER BY month
        """
                ),
                params,
            )
            .mappings()
            .fetchall()
        )

        return [
            {
                "month": r["month"],
                "claim_count": r["claim_count"],
                "total_amount": round(r["total_amount"], 2),
            }
            for r in rows
        ]
    finally:
        session.close()


# -----------------------------------------------------------
# Tool 4: Carrier summary — policy counts by carrier and year
# -----------------------------------------------------------

_DEFAULT_YEARS = [2024, 2025, 2026]


def get_carrier_summary(years: Optional[List[int]] = None) -> list:
    """Policy counts per carrier, pivoted by year."""
    years = years or _DEFAULT_YEARS

    # Build a CASE column per year. `years` is pydantic-validated List[int], so these
    # are always plain integers — safe to format directly into the SQL text.
    year_cols = "\n".join(
        f"SUM(CASE WHEN start_date <= '{y}-12-31' AND "
        f"(expiry_date IS NULL OR expiry_date >= '{y}-01-01') THEN 1 ELSE 0 END) AS \"{y}\","
        for y in years
    )

    session = _session()
    try:
        rows = (
            session.execute(
                text(
                    f"""
            SELECT
                carrier_name,
                {year_cols}
                COUNT(*) AS total_policies
            FROM auto_policies
            GROUP BY carrier_name
            ORDER BY total_policies DESC
        """
                )
            )
            .mappings()
            .fetchall()
        )

        return [dict(r) for r in rows]
    finally:
        session.close()


# -----------------------------------------------------------
# Tool 5: Per-person summary (policies + claims + fraud flag)
# -----------------------------------------------------------


def get_person_summary(limit: int = 25) -> list:
    """Aggregate view per person: policy count, premiums, claims, loss ratio, fraud flag.

    Capped at `limit` (default 25, max 100) — with thousands of seeded persons,
    returning every one of them would blow past the model's token budget on the
    next turn (hit a 413 "request too large" error during testing without a cap).
    Ordered by total_claims DESC, so the default view is the highest-exposure
    people first, not an arbitrary truncation.
    """
    limit = max(1, min(limit, 100))
    session = _session()
    try:
        # Claims are pre-aggregated per person before joining, otherwise a person
        # with M policies and N claims fans out to M×N rows and every SUM/COUNT
        # is multiplied.
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
                GROUP BY person_id
            ) c ON c.person_id = p.person_id
            WHERE p.status = 'active'
            GROUP BY p.person_id
            ORDER BY total_claims DESC
            LIMIT :limit
        """
                ),
                {"limit": limit},
            )
            .mappings()
            .fetchall()
        )

        return [dict(r) for r in rows]
    finally:
        session.close()


# -----------------------------------------------------------
# Tool 6: Carrier claims summary — claim counts + amounts by carrier and year
# -----------------------------------------------------------


def get_carrier_claims_summary(years: Optional[List[int]] = None) -> list:
    """Claim counts and total amounts per carrier, pivoted by year."""
    years = years or _DEFAULT_YEARS

    year_count_cols = "\n".join(
        f"SUM(CASE WHEN strftime('%Y', c.claim_date) = '{y}' THEN 1 ELSE 0 END) AS \"{y}_claims\","
        for y in years
    )
    year_amount_cols = "\n".join(
        f"ROUND(SUM(CASE WHEN strftime('%Y', c.claim_date) = '{y}' THEN c.amount ELSE 0 END), 2) AS \"{y}_amount\","
        for y in years
    )

    session = _session()
    try:
        rows = (
            session.execute(
                text(
                    f"""
            SELECT
                p.carrier_name,
                {year_count_cols}
                {year_amount_cols}
                COUNT(c.claim_id)           AS total_claims,
                ROUND(SUM(c.amount), 2)     AS total_amount
            FROM auto_policies p
            LEFT JOIN claims c ON c.policy_id = p.policy_id
            GROUP BY p.carrier_name
            ORDER BY total_claims DESC
        """
                )
            )
            .mappings()
            .fetchall()
        )

        return [dict(r) for r in rows]
    finally:
        session.close()


class LossRatioInput(BaseModel):
    carrier: Optional[str] = Field(default=None, description="Carrier name, e.g. GEICO, StateFarm")
    state: Optional[str] = Field(default=None, description="2-letter state code, e.g. CA")
    year: Optional[int] = Field(default=None, description="4-digit year, e.g. 2026")


class NoInput(BaseModel):
    pass


class PersonSummaryInput(BaseModel):
    limit: int = Field(
        default=25, description="Max number of persons to return (default 25, max 100)"
    )


class ClaimsTrendInput(BaseModel):
    state: Optional[str] = Field(default=None, description="2-letter state code, e.g. CA")
    carrier: Optional[str] = Field(default=None, description="Carrier name, e.g. GEICO, StateFarm")


class YearsInput(BaseModel):
    years: Optional[List[int]] = Field(
        default=None,
        description="List of 4-digit years, e.g. [2024, 2025, 2026]. Defaults to 2024-2026 if omitted.",
    )


ANALYTICS_TOOLS = [
    StructuredTool.from_function(
        func=get_loss_ratio,
        name="get_loss_ratio",
        description="""Calculate loss ratio (claims paid / premiums collected).
        Use for ANY question about loss ratio — overall, by state, by carrier, or by year.
        Examples: 'overall loss ratio', 'loss ratio for CA', 'StateFarm 2025', 'loss ratio in OH in 2026'.
        Leave all fields empty for the overall all-time portfolio loss ratio.
        Output: carrier, state, period, total premium, total claims, loss ratio %, assessment.""",
        args_schema=LossRatioInput,
    ),
    StructuredTool.from_function(
        func=get_portfolio_summary,
        name="get_portfolio_summary",
        description="""Get a high-level summary of the entire policy portfolio.
        Use when asked for: portfolio overview, dashboard, total policies, total premiums, top states, KPIs.
        Do NOT use this for loss ratio questions — use get_loss_ratio instead.
        No input required.
        Output: active policies, unique persons, total premium, avg risk score, top states.""",
        args_schema=NoInput,
    ),
    StructuredTool.from_function(
        func=get_claims_trend,
        name="get_claims_trend",
        description="""Get monthly claims trend for the past 12 months.
        Use ONLY when asked about trends over time, monthly patterns, or seasonal analysis.
        Do NOT use for loss ratio or portfolio summary questions.
        Output: month-by-month claim count and total amount.""",
        args_schema=ClaimsTrendInput,
    ),
    StructuredTool.from_function(
        func=get_carrier_summary,
        name="get_carrier_summary",
        description="""Get POLICY counts per insurance carrier broken down by year.
        Use when asked about: number of policies per company/carrier, carrier breakdown by year,
        'list all insurance companies with policy count', 'how many policies per carrier in 2024/2025/2026'.
        Defaults to years 2024, 2025, 2026 if not specified.
        Output: one row per carrier with a column for each year and a total.""",
        args_schema=YearsInput,
    ),
    StructuredTool.from_function(
        func=get_carrier_claims_summary,
        name="get_carrier_claims_summary",
        description="""Get CLAIM counts and total claim amounts per insurance carrier broken down by year.
        Use when asked about: number of claims per company/carrier, claims by carrier by year,
        'list all insurance companies with number of claims', 'how many claims per carrier in 2024/2025/2026',
        'claims frequency by carrier', 'claim volume per company'.
        Defaults to years 2024, 2025, 2026 if not specified.
        Output: one row per carrier with claim count and total amount per year plus overall totals.""",
        args_schema=YearsInput,
    ),
    StructuredTool.from_function(
        func=get_person_summary,
        name="get_person_summary",
        description="""Get a combined per-person summary across policies and claims, ranked by
        total claims descending (highest-exposure people first).
        Use when asked to list persons/customers with their policy count, premiums, claims, loss ratio, risk score, or fraud flag.
        Examples: 'list all persons with policy and claims info', 'customer overview', 'who has the highest loss ratio'.
        Optional limit (default 25, max 100) — there are thousands of persons, so this is never
        truly "all" of them; it returns the top N by claims.
        Output: one row per person with policy_count, total_premium, risk_tier, claims_count, total_claims, loss_ratio_pct, fraud_flag.""",
        args_schema=PersonSummaryInput,
    ),
]
