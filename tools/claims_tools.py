"""
Claims tools — claims history, frequent claimants, fraud flagging.
"""

from datetime import date, timedelta
from langchain.tools import Tool
from sqlalchemy import text
from db.database import get_session


def _session():
    return get_session()


def get_claims_by_person(person_id: str) -> dict:
    session = _session()
    cutoff = date.today() - timedelta(days=3 * 365)
    try:
        rows = session.execute(text("""
            SELECT claim_id, policy_id, claim_date, claim_type, amount, status
            FROM claims
            WHERE person_id  = :pid
              AND claim_date >= :cutoff
            ORDER BY claim_date DESC
        """), {"pid": person_id.strip(), "cutoff": cutoff}).mappings().fetchall()

        if not rows:
            return {"message": f"No claims found for person {person_id} in the past 3 years."}

        return {
            "person_id":    person_id,
            "period":       f"{cutoff} to {date.today()}",
            "total_claims": len(rows),
            "total_amount": sum(r["amount"] for r in rows),
            "claims": [
                {
                    "claim_id":  r["claim_id"],
                    "policy_id": r["policy_id"],
                    "date":      str(r["claim_date"]),
                    "type":      r["claim_type"],
                    "amount":    r["amount"],
                    "status":    r["status"],
                }
                for r in rows
            ]
        }
    finally:
        session.close()


def find_frequent_claimants(input_str: str = "") -> list:
    import re
    min_claims = int((re.search(r"min_claims[= ]+(\d+)", input_str) or [None, 2])[1])
    years      = int((re.search(r"years[= ]+(\d+)",      input_str) or [None, 1])[1])
    cutoff     = date.today() - timedelta(days=years * 365)

    session = _session()
    try:
        rows = session.execute(text("""
            SELECT
                c.person_id,
                COUNT(c.claim_id)  AS claims_count,
                SUM(c.amount)      AS total_amount,
                p.state,
                p.risk_score
            FROM claims c
            JOIN auto_policies p ON c.person_id = p.person_id
            WHERE c.claim_date >= :cutoff
            GROUP BY c.person_id, p.state, p.risk_score
            HAVING COUNT(c.claim_id) >= :min_claims
            ORDER BY claims_count DESC
            LIMIT 50
        """), {"cutoff": cutoff, "min_claims": min_claims}).mappings().fetchall()

        return [
            {
                "person_id":    r["person_id"],
                "claims_count": r["claims_count"],
                "total_amount": r["total_amount"],
                "state":        r["state"],
                "risk_score":   r["risk_score"],
                "fraud_flag":   r["claims_count"] >= 3,
            }
            for r in rows
        ]
    finally:
        session.close()


def flag_fraud_risk(person_id: str) -> dict:
    result = get_claims_by_person(person_id)

    if "message" in result:
        return {"person_id": person_id, "fraud_risk": "Low", "reason": "No recent claims."}

    total    = result["total_claims"]
    amount   = result["total_amount"]
    open_cnt = sum(1 for c in result["claims"] if c["status"] == "Open")

    score = 0
    reasons = []
    if total >= 4:    score += 3; reasons.append(f"{total} claims in 3 years")
    elif total >= 2:  score += 1; reasons.append(f"{total} claims in 3 years")
    if amount > 30000: score += 2; reasons.append(f"High total amount ${amount:,.0f}")
    if open_cnt >= 2:  score += 2; reasons.append(f"{open_cnt} open claims simultaneously")

    risk = "High" if score >= 4 else "Medium" if score >= 2 else "Low"

    return {
        "person_id":    person_id,
        "fraud_risk":   risk,
        "score":        score,
        "total_claims": total,
        "total_amount": amount,
        "reasons":      reasons,
        "recommendation": "Refer to SIU for investigation" if risk == "High"
                          else "Monitor closely" if risk == "Medium"
                          else "No action needed"
    }


CLAIMS_TOOLS = [
    Tool(
        name="get_claims_by_person",
        func=get_claims_by_person,
        description="""Get full claims history for ONE specific person.
        Use when a person_id is mentioned (e.g. 'claims for P-001', 'history for P-003').
        Do NOT use this to find multiple persons or list all claimants.
        Input: a person_id string (e.g. 'P-001').
        Output: list of claims with dates, types, amounts, and statuses."""
    ),
    Tool(
        name="find_frequent_claimants",
        func=find_frequent_claimants,
        description="""Find ALL persons who have filed multiple claims.
        Use when asked to LIST or FIND persons with N or more claims — e.g.:
        'find all persons with 2 or more claims', 'who has multiple claims',
        'frequent claimants', 'persons with more than 1 claim in the past year'.
        Input: 'min_claims=2 years=1' — set min_claims and years from the question.
        Output: ranked list of all matching persons with claim counts and fraud flags."""
    ),
    Tool(
        name="flag_fraud_risk",
        func=flag_fraud_risk,
        description="""Assess fraud risk score for ONE specific person.
        Use ONLY when a specific person_id is given AND fraud/risk is asked about.
        Examples: 'fraud risk for P-002', 'is P-005 suspicious', 'SIU referral for P-001'.
        Do NOT use this to find multiple persons or answer listing questions.
        Input: a person_id string.
        Output: fraud risk level (Low/Medium/High), score, and recommendation."""
    ),
]
