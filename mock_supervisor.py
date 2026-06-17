"""
Mock supervisor for demo mode (no API key required).
Returns pre-canned responses based on keyword routing.
All responses use proper markdown-table format so render_agent_response()
can convert them to st.dataframe widgets in the UI.
"""

import random


MOCK_RESPONSES = {
    "underwriting": [
        """\
**Risk Score — Policy A-10234**

| Field | Value |
|-------|-------|
| Policy ID | A-10234 |
| Holder | John Smith |
| State | CA |
| Carrier | StateFarm |
| Risk Score | 72 / 100 |
| Risk Tier | 🟡 Medium |
| Status | Active |
| Premium | $1,450 / yr |

**Comment**
- Risk score of 72 places this policy in the Medium tier (50–74 range).
- Premium of $1,450/yr is consistent with medium-risk profiles for California.
- No immediate renewal action required; recommend review at next expiry date.""",
        """\
**Churn Rate — StateFarm, Q1 2026**

| Field | Value |
|-------|-------|
| Carrier | StateFarm |
| Period | Q1 2026 (Jan 1 – Mar 31) |
| Total Expiring Policies | 142 |
| Non-Renewed | 12 |
| Churn Rate | 8.5% |
| Industry Benchmark | 7.0% |

**Comment**
- Churn rate of 8.5% is 1.5 pp above the 7% industry benchmark — warrants attention.
- 12 non-renewals in a single quarter may indicate pricing or service competitiveness issues.
- Recommend reviewing renewal offers and proactive outreach for at-risk policyholders.""",
        """\
**Active Policies — Texas**

| Metric | Value |
|--------|-------|
| Active Policies | 34 |
| Average Risk Score | 64 / 100 |
| Average Premium | $1,280 / yr |
| Total Annual Premium | $43,520 |
| High-Risk Policies (≥75) | 8 |

**Comment**
- Texas portfolio is mid-risk with an average score of 64 (Medium tier).
- 8 high-risk policies (≥75) account for roughly 24% of the book; closer monitoring advised.
- Average premium of $1,280 is below the national average — review pricing adequacy.""",
        """\
**Risk Score — Policy A-10567**

| Field | Value |
|-------|-------|
| Policy ID | A-10567 |
| Holder | Robert K. |
| State | FL |
| Risk Score | 91 / 100 |
| Risk Tier | 🔴 High |
| Status | Active |
| Premium | $2,340 / yr |

**Comment**
- Score of 91 is firmly in the High-risk tier (≥75); immediate review recommended.
- Consider non-renewal or rate adjustment at next renewal cycle.
- Flag for underwriting committee review before binding any additional coverage.""",
    ],
    "claims": [
        """\
**Claims History — P-001 (Last 3 Years)**

| Claim ID | Date | Type | Amount | Status |
|----------|------|------|--------|--------|
| C-4421 | 2024-03-15 | Collision | $8,200 | ✅ Closed |
| C-5103 | 2025-01-22 | Theft | $15,000 | ✅ Closed |
| C-5891 | 2025-11-08 | Liability | $4,500 | 🔴 Open |

**Comment**
- 3 claims totalling $27,700 in 3 years — above average frequency.
- Open liability claim of $4,500 requires follow-up; reserve may need adjustment.
- Fraud risk is 🔴 High — recommend SIU referral given claim volume and amounts.""",
        """\
**Frequent Claimants — 2+ Claims, Past Year**

| Person ID | Claims | Total Amount | State | Fraud Flag |
|-----------|--------|-------------|-------|------------|
| P-008 | 3 | $31,200 | CA | ⚠️ Yes |
| P-001 | 2 | $19,500 | TX | No |

**Comment**
- P-008 has 3 claims totalling $31,200 — exceeds the High-risk threshold; SIU referral advised.
- P-001's 2 claims are within acceptable range but should be monitored closely.
- Consider placing both claimants on a watchlist for the next policy year.""",
        """\
**Fraud Risk Assessment — P-002**

| Field | Value |
|-------|-------|
| Person ID | P-002 |
| Fraud Risk | 🟢 Low |
| Risk Score | 1 / 10 |
| Total Claims (3 yrs) | 1 |
| Total Amount | $3,400 |
| Open Claims | 0 |
| Recommendation | No action needed |

**Comment**
- Single claim of $3,400 over 3 years is well within normal range.
- No open claims; no simultaneous claim patterns detected.
- No SIU action required — routine monitoring sufficient.""",
        """\
**Claims History — Policy A-10234**

| Claim ID | Date | Type | Amount | Status |
|----------|------|------|--------|--------|
| C-6201 | 2025-06-14 | Collision | $6,800 | ✅ Closed |

**Comment**
- Single closed collision claim of $6,800 — within expected range for this risk tier.
- Claim is fully resolved; no open liability exposure on this policy.
- Risk profile remains stable; no changes to renewal recommendation at this time.""",
    ],
    "analytics": [
        """\
**Portfolio Summary**

| Metric | Value |
|--------|-------|
| Total Policies | 6 |
| Active | 5 |
| Inactive / Cancelled | 1 |
| Total Annual Premium | $8,640 |
| Total Claims Paid | $5,200 |
| Loss Ratio | 60.2% |
| Portfolio Status | ✅ Healthy |

**Comment**
- Loss ratio of 60.2% is below the 70% industry threshold — portfolio is profitable.
- 5 of 6 policies are active; 1 inactive policy should be reviewed for reinstatement.
- Recommend focusing growth efforts in states with lower loss ratios to maintain margins.""",
        """\
**Loss Ratio — California**

| Metric | Value |
|--------|-------|
| State | California |
| Total Premiums Collected | $4,530 |
| Total Claims Paid | $3,100 |
| Loss Ratio | 68.4% |
| Benchmark | 70.0% |
| Status | 🟡 Acceptable |

**Comment**
- Loss ratio of 68.4% is within acceptable range but close to the 70% threshold.
- Close monitoring is advised — any increase in claims frequency could push into unprofitable territory.
- Consider tightening underwriting criteria for high-risk applicants in California.""",
        """\
**Monthly Claims Trend — Past 12 Months**

| Month | Claims Filed | Total Amount |
|-------|-------------|-------------|
| Jul 2025 | 2 | $10,400 |
| Aug 2025 | 1 | $3,200 |
| Sep 2025 | 3 | $18,700 |
| Oct 2025 | 5 | $31,500 |
| Nov 2025 | 2 | $9,800 |
| Dec 2025 | 1 | $4,100 |
| Jan 2026 | 4 | $22,300 |
| Feb 2026 | 3 | $15,600 |
| Mar 2026 | 2 | $8,900 |
| Apr 2026 | 1 | $5,200 |
| May 2026 | 2 | $7,400 |
| Jun 2026 | 2 | $6,800 |

**Comment**
- October 2025 and January 2026 show the highest claim volumes — seasonal weather and post-holiday patterns.
- Summer months (Jul–Aug) are the lowest-risk period across the portfolio.
- Oct spike driven by 2 large liability claims; recommend pre-winter risk advisories to policyholders.""",
        """\
**Claims by Insurance Company — 2024 / 2025 / 2026**

| Carrier | 2024 Claims | 2024 Amount | 2025 Claims | 2025 Amount | 2026 Claims | 2026 Amount | Total Claims |
|---------|------------|------------|------------|------------|------------|------------|-------------|
| GEICO | 8 | $64,200 | 11 | $89,500 | 4 | $31,000 | 23 |
| StateFarm | 6 | $48,700 | 9 | $73,200 | 3 | $22,400 | 18 |
| Allstate | 5 | $39,100 | 7 | $58,300 | 2 | $15,600 | 14 |
| Progressive | 4 | $31,500 | 6 | $49,800 | 2 | $12,900 | 12 |
| Nationwide | 3 | $24,200 | 4 | $33,100 | 1 | $8,200 | 8 |

**Comment**
- GEICO leads in total claim volume (23 claims) — warrants portfolio-level risk review.
- Claims are trending upward year-over-year across all carriers; 2025 is the peak year.
- Nationwide has the lowest claim volume (8 total), suggesting either a smaller book or lower-risk policyholders.""",
        """\
**Overall Portfolio Loss Ratio**

| Metric | Value |
|--------|-------|
| Total Policies | 6 |
| Gross Written Premium | $8,640 |
| Total Losses Paid | $5,200 |
| Loss Ratio | 60.2% |
| Industry Threshold | 70.0% |
| Margin vs. Threshold | +9.8 pp |

**Comment**
- Portfolio loss ratio of 60.2% is 9.8 percentage points below the 70% threshold — strong performance.
- Growth capacity exists within current risk parameters without threatening profitability.
- Recommend quarterly review to catch any upward trend before it approaches the threshold.""",
    ],
}


class MockSupervisorAgent:
    """Returns canned markdown-table responses for demo purposes."""

    def __init__(self):
        self.routing_log = []

    def _route(self, question: str) -> str:
        q = question.lower()
        # Analytics: aggregate / cross-carrier / trend questions (check first — highest priority)
        if any(
            w in q
            for w in [
                "loss ratio",
                "loss sum",
                "claims trend",
                "trend",
                "portfolio",
                "summary",
                "kpi",
                "monthly",
                "quarterly",
                "aggregate",
                "all persons",
                "per person",
                "list all",
                "policy count",
                "premium sum",
                "claims count",
                "fraud flag",
                "person summary",
                "number of claims",
                "claims per carrier",
                "claims by carrier",
                "insurance companies",
                "insurance company",
                "claim volume",
            ]
        ):
            return "analytics"
        # Claims: person/policy-level claim lookups
        if any(
            w in q
            for w in [
                "claims history",
                "claims for",
                "claim filed",
                "filed a claim",
                "fraud",
                "siu",
                "frequent claimant",
                "person id",
                "person_id",
                "claimant",
                "accident",
                "collision",
                "theft",
                "liability",
            ]
        ):
            return "claims"
        return "underwriting"

    def run(self, question: str) -> dict:
        domain = self._route(question)
        self.routing_log.append({"question": question, "routed_to": domain})
        answer = random.choice(MOCK_RESPONSES[domain])
        return {"question": question, "routed_to": domain, "answer": answer}

    def get_routing_log(self) -> list:
        return self.routing_log
