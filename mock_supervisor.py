"""
Mock supervisor for demo mode (no API key required).
Returns pre-canned responses based on keyword routing.
"""

import random


MOCK_RESPONSES = {
    "underwriting": [
        "**Policy A-10234** — Holder: John Smith | State: CA | Risk Score: 72 (Medium) | Status: Active | Premium: $1,450/yr",
        "**Churn Rate (StateFarm, Q1 2026):** 8.3% non-renewal rate across 142 policies. Slightly above the 7% industry benchmark.",
        "**Active policies in Texas:** 34 policies. Average risk score: 64. Average premium: $1,280/yr.",
        "**Risk Score for policy A-10567:** 91 — High Risk tier. Recommend review before renewal.",
    ],
    "claims": [
        "**Claims for P-001 (last 3 years):** 3 claims found.\n- 2024-03: Collision — $8,200 (Closed)\n- 2025-01: Theft — $15,000 (Closed)\n- 2025-11: Liability — $4,500 (Open)\n\n⚠️ Fraud Risk: **High** — recommend SIU referral.",
        "**Frequent claimants (2+ claims, past year):** 2 persons flagged.\n- P-001: 2 claims, $19,500 total\n- P-008: 3 claims, $31,200 total ⚠️",
        "**Fraud Risk for P-002:** Low. 1 claim in past 3 years, amount within normal range.",
        "**Claims history for A-10234:** 1 claim on record.\n- 2025-06: Collision — $6,800 (Closed)",
    ],
    "analytics": [
        "**Portfolio Summary:**\n- Total Policies: 6 | Active: 5 | Cancelled: 1\n- Total Premium: $8,640/yr\n- Total Claims Paid: $5,200\n- Loss Ratio: 60.2% ✅ (Healthy — under 70%)",
        "**Loss Ratio — California:** 68.4% (Acceptable). Claims paid: $3,100 vs premiums collected: $4,530.",
        "**Monthly Claims Trend (past 12 months):** Peak in Jan–Feb (winter weather). Steady decline through summer. Oct spike due to 2 large liability claims.",
        "**Overall Portfolio Loss Ratio:** 60.2% — below the 70% industry threshold. Portfolio is performing well.",
    ],
}


class MockSupervisorAgent:
    """Returns canned responses for demo purposes."""

    def __init__(self):
        self.routing_log = []

    def _route(self, question: str) -> str:
        q = question.lower()
        # Analytics keywords checked first to avoid "claims trend" → claims
        if any(w in q for w in ["loss ratio", "loss sum", "claims trend", "trend", "portfolio",
                                  "summary", "kpi", "monthly", "quarterly", "aggregate",
                                  "all persons", "per person", "list all", "policy count",
                                  "premium sum", "claims count", "fraud flag", "person summary"]):
            return "analytics"
        if any(w in q for w in ["fraud", "siu", "frequent claimant",
                                  "person id", "person_id", "claimant"]):
            return "claims"
        if any(w in q for w in ["claim", "accident", "collision", "theft", "liability"]):
            return "claims"
        return "underwriting"

    def run(self, question: str) -> dict:
        domain = self._route(question)
        self.routing_log.append({"question": question, "routed_to": domain})
        answer = random.choice(MOCK_RESPONSES[domain])
        return {"question": question, "routed_to": domain, "answer": answer}

    def get_routing_log(self) -> list:
        return self.routing_log
