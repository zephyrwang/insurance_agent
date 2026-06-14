"""
Underwriting tools — policy lookup, risk scoring, churn rate.
"""

from datetime import date, timedelta
from langchain.tools import Tool
from sqlalchemy import text
from db.database import get_session


def _session():
    return get_session()


def get_risk_score(policy_id: str) -> dict:
    session = _session()
    try:
        row = session.execute(
            text("SELECT policy_id, holder_name, risk_score, state, carrier_name "
                 "FROM auto_policies WHERE policy_id = :pid"),
            {"pid": policy_id.strip()}
        ).mappings().fetchone()

        if not row:
            return {"error": f"Policy {policy_id} not found."}

        return {
            "policy_id":   row["policy_id"],
            "holder_name": row["holder_name"],
            "state":       row["state"],
            "carrier":     row["carrier_name"],
            "risk_score":  row["risk_score"],
            "risk_tier":   "High"   if row["risk_score"] >= 75
                           else "Medium" if row["risk_score"] >= 50
                           else "Low"
        }
    finally:
        session.close()


def _parse_quarter(text_str: str):
    import re
    t = text_str.lower()
    quarter_map = {
        "q1": (1, 1, 3, 31), "first":  (1, 1, 3, 31),
        "q2": (4, 1, 6, 30), "second": (4, 1, 6, 30),
        "q3": (7, 1, 9, 30), "third":  (7, 1, 9, 30),
        "q4": (10, 1, 12, 31), "fourth": (10, 1, 12, 31),
    }
    year_match = re.search(r"\b(20\d{2})\b", t)
    year = int(year_match.group(1)) if year_match else date.today().year
    for key, (sm, sd, em, ed) in quarter_map.items():
        if key in t:
            return date(year, sm, sd), date(year, em, ed)
    today = date.today()
    return today - timedelta(days=90), today


def get_churn_rate(input_str: str) -> dict:
    import re

    carrier_match = re.search(
        r"carrier[= ]+([A-Za-z ]+?)(?:\s+period|$|\s+Q[1-4]|\s+20\d{2})",
        input_str, re.I
    )
    carrier = carrier_match.group(1).strip() if carrier_match else input_str.split()[0]
    carrier_norm = {
        "state farm": "StateFarm", "statefarm": "StateFarm",
        "allstate": "Allstate", "geico": "GEICO",
        "progressive": "Progressive", "nationwide": "Nationwide",
    }.get(carrier.lower(), carrier)

    start_date, end_date = _parse_quarter(input_str)

    session = _session()
    try:
        result = session.execute(text("""
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
        """), {"carrier": carrier_norm, "start": start_date, "end": end_date}).mappings().fetchone()

        if not result:
            return {"message": f"No expiring policies found for {carrier_norm} "
                               f"between {start_date} and {end_date}."}

        return {
            "carrier":        result["carrier_name"],
            "period":         f"{start_date} to {end_date}",
            "total_expiring": result["total_expiring"],
            "not_renewed":    result["not_renewed"],
            "churn_rate_pct": result["churn_rate_pct"],
        }
    finally:
        session.close()


UNDERWRITING_TOOLS = [
    Tool(
        name="get_risk_score",
        func=get_risk_score,
        description="""Get risk score and risk tier for a specific policy.
        Input: a policy_id string (e.g. 'A-10234').
        Output: risk score (0-100) and tier (Low/Medium/High)."""
    ),
    Tool(
        name="get_churn_rate",
        func=get_churn_rate,
        description="""Calculate churn or non-renewal rate for a carrier in a time period.
        Use when asked about: churn rate, attrition, non-renewal rate, retention rate.
        Input: string containing carrier name and period, e.g. 'carrier=StateFarm period=Q1 2026'.
        Understands: Q1/Q2/Q3/Q4, 'first quarter', year references."""
    ),
]
