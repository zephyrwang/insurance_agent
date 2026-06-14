"""
Analytics tools — loss ratio, trend analysis, portfolio summary.
"""

from datetime import date, timedelta
from langchain.tools import Tool
from sqlalchemy import text
from db.database import get_session


def _session():
    return get_session()


def get_loss_ratio(input_str: str) -> dict:
    import re
    carrier = (re.search(r"carrier[= ]+([A-Za-z]+)", input_str) or [None, None])[1]
    state   = (re.search(r"state[= ]+([A-Z]{2})",   input_str) or [None, None])[1]
    year_m  = re.search(r"\b(20\d{2})\b", input_str)
    year    = int(year_m.group(1)) if year_m else None

    policy_where = ["1=1"]
    claim_where  = ["c.status = 'Closed'"]
    params = {}

    if carrier:
        policy_where.append("p.carrier_name = :carrier")
        params["carrier"] = carrier
    if state:
        policy_where.append("p.state = :state")
        params["state"] = state
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
        result = session.execute(text(f"""
            SELECT
                SUM(p.premium)  AS total_premium,
                SUM(c.amount)   AS total_claims,
                ROUND(100.0 * SUM(c.amount) / NULLIF(SUM(p.premium), 0), 2) AS loss_ratio_pct
            FROM auto_policies p
            LEFT JOIN claims c ON p.policy_id = c.policy_id AND {cw}
            WHERE {pw}
        """), params).mappings().fetchone()

        loss_ratio = result["loss_ratio_pct"] or 0
        period = str(year) if year else "All time"
        return {
            "carrier":        carrier or "All",
            "state":          state   or "All",
            "period":         period,
            "total_premium":  round(result["total_premium"] or 0, 2),
            "total_claims":   round(result["total_claims"]  or 0, 2),
            "loss_ratio_pct": loss_ratio,
            "assessment":     "Unprofitable" if loss_ratio > 100
                              else "Borderline" if loss_ratio > 70
                              else "Healthy"
        }
    finally:
        session.close()


def get_portfolio_summary(input_str: str = "") -> dict:
    session = _session()
    try:
        policies = session.execute(text("""
            SELECT
                COUNT(*)                  AS total_policies,
                SUM(premium)              AS total_premium,
                AVG(risk_score)           AS avg_risk_score,
                COUNT(DISTINCT person_id) AS unique_persons
            FROM auto_policies
            WHERE status = 'active'
        """)).mappings().fetchone()

        claims = session.execute(text("""
            SELECT
                COUNT(*)    AS total_claims,
                SUM(amount) AS total_claims_amount,
                AVG(amount) AS avg_claim_amount
            FROM claims
            WHERE claim_date >= :cutoff
        """), {"cutoff": date.today() - timedelta(days=365)}).mappings().fetchone()

        by_state = session.execute(text("""
            SELECT state, COUNT(*) AS cnt
            FROM auto_policies
            WHERE status = 'active'
            GROUP BY state
            ORDER BY cnt DESC
            LIMIT 5
        """)).mappings().fetchall()

        return {
            "active_policies":  policies["total_policies"],
            "unique_persons":   policies["unique_persons"],
            "total_premium":    round(policies["total_premium"] or 0, 2),
            "avg_risk_score":   round(policies["avg_risk_score"] or 0, 1),
            "claims_last_year": claims["total_claims"],
            "claims_amount":    round(claims["total_claims_amount"] or 0, 2),
            "avg_claim_amount": round(claims["avg_claim_amount"] or 0, 2),
            "top_states":       [{"state": r["state"], "policies": r["cnt"]} for r in by_state],
        }
    finally:
        session.close()


def get_claims_trend(input_str: str = "") -> list:
    import re
    state   = (re.search(r"state[= ]+([A-Z]{2})",   input_str) or [None, None])[1]
    carrier = (re.search(r"carrier[= ]+([A-Za-z]+)", input_str) or [None, None])[1]

    where_clauses = ["c.claim_date >= :cutoff"]
    params = {"cutoff": date.today() - timedelta(days=365)}
    if state:
        where_clauses.append("p.state = :state"); params["state"] = state
    if carrier:
        where_clauses.append("p.carrier_name = :carrier"); params["carrier"] = carrier

    where = " AND ".join(where_clauses)
    session = _session()
    try:
        # strftime works for SQLite; swap to DATE_FORMAT for MySQL
        rows = session.execute(text(f"""
            SELECT
                strftime('%Y-%m', c.claim_date) AS month,
                COUNT(*)                        AS claim_count,
                SUM(c.amount)                   AS total_amount
            FROM claims c
            JOIN auto_policies p ON c.policy_id = p.policy_id
            WHERE {where}
            GROUP BY month
            ORDER BY month
        """), params).mappings().fetchall()

        return [
            {
                "month":        r["month"],
                "claim_count":  r["claim_count"],
                "total_amount": round(r["total_amount"], 2),
            }
            for r in rows
        ]
    finally:
        session.close()


# -----------------------------------------------------------
# Tool 4: Carrier summary — policy counts by carrier and year
# -----------------------------------------------------------

def get_carrier_summary(input_str: str = "") -> list:
    """Policy counts per carrier, pivoted by year."""
    import re
    years = re.findall(r"\b(20\d{2})\b", input_str) or ["2024", "2025", "2026"]

    # Build a CASE column per year
    year_cols = "\n".join([
        f"SUM(CASE WHEN start_date <= '{y}-12-31' AND "
        f"(expiry_date IS NULL OR expiry_date >= '{y}-01-01') THEN 1 ELSE 0 END) AS \"{y}\","
        for y in years
    ])

    session = _session()
    try:
        rows = session.execute(text(f"""
            SELECT
                carrier_name,
                {year_cols}
                COUNT(*) AS total_policies
            FROM auto_policies
            GROUP BY carrier_name
            ORDER BY total_policies DESC
        """)).mappings().fetchall()

        return [dict(r) for r in rows]
    finally:
        session.close()


# -----------------------------------------------------------
# Tool 5: Per-person summary (policies + claims + fraud flag)
# -----------------------------------------------------------

def get_person_summary(input_str: str = "") -> list:
    """Aggregate view per person: policy count, premiums, claims, loss ratio, fraud flag."""
    session = _session()
    try:
        rows = session.execute(text("""
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
                COUNT(c.claim_id)                                               AS claims_count,
                ROUND(COALESCE(SUM(c.amount), 0), 2)                           AS total_claims,
                ROUND(
                    100.0 * COALESCE(SUM(CASE WHEN c.status='Closed' THEN c.amount ELSE 0 END), 0)
                    / NULLIF(SUM(p.premium), 0), 2
                )                                                               AS loss_ratio_pct,
                CASE WHEN COUNT(c.claim_id) >= 4 THEN '🔴 High'
                     WHEN COUNT(c.claim_id) >= 2 THEN '🟡 Medium'
                     ELSE '🟢 Low' END                                          AS fraud_flag
            FROM auto_policies p
            LEFT JOIN claims c ON p.person_id = c.person_id
            WHERE p.status = 'active'
            GROUP BY p.person_id
            ORDER BY total_claims DESC
        """)).mappings().fetchall()

        return [dict(r) for r in rows]
    finally:
        session.close()


ANALYTICS_TOOLS = [
    Tool(
        name="get_loss_ratio",
        func=get_loss_ratio,
        description="""Calculate loss ratio (claims paid / premiums collected).
        Use for ANY question about loss ratio — overall, by state, by carrier, or by year.
        Examples: 'overall loss ratio', 'loss ratio for CA', 'StateFarm 2025', 'loss ratio in OH in 2026'.
        Input: combine any of — 'carrier=StateFarm', 'state=CA', and/or a 4-digit year like '2025'.
        Example inputs: 'carrier=StateFarm 2025', 'state=OH 2026', 'carrier=GEICO state=CA 2025'.
        Leave empty for overall all-time portfolio loss ratio.
        Output: carrier, state, period, total premium, total claims, loss ratio %, assessment."""
    ),
    Tool(
        name="get_portfolio_summary",
        func=get_portfolio_summary,
        description="""Get a high-level summary of the entire policy portfolio.
        Use when asked for: portfolio overview, dashboard, total policies, total premiums, top states, KPIs.
        Do NOT use this for loss ratio questions — use get_loss_ratio instead.
        No input required.
        Output: active policies, unique persons, total premium, avg risk score, top states."""
    ),
    Tool(
        name="get_claims_trend",
        func=get_claims_trend,
        description="""Get monthly claims trend for the past 12 months.
        Use ONLY when asked about trends over time, monthly patterns, or seasonal analysis.
        Do NOT use for loss ratio or portfolio summary questions.
        Input: optional 'state=CA' or 'carrier=StateFarm'.
        Output: month-by-month claim count and total amount."""
    ),
    Tool(
        name="get_carrier_summary",
        func=get_carrier_summary,
        description="""Get policy counts per insurance carrier broken down by year.
        Use when asked about: number of policies per company/carrier, carrier breakdown by year,
        'list all insurance companies with policy count', 'how many policies per carrier in 2024/2025/2026'.
        Input: list the years needed, e.g. '2024 2025 2026'. Defaults to 2024, 2025, 2026 if blank.
        Output: one row per carrier with a column for each year and a total."""
    ),
    Tool(
        name="get_person_summary",
        func=get_person_summary,
        description="""Get a combined per-person summary across policies and claims.
        Use when asked to list all persons/customers with their policy count, premiums, claims, loss ratio, risk score, or fraud flag.
        Examples: 'list all persons with policy and claims info', 'customer overview', 'who has the highest loss ratio'.
        No input required.
        Output: one row per person with policy_count, total_premium, risk_tier, claims_count, total_claims, loss_ratio_pct, fraud_flag."""
    ),
]
