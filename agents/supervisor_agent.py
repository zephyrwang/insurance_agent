"""
Supervisor Agent
Routes incoming questions to the correct specialist agent:
  - Underwriting Agent  → policy lookup, risk scores, churn rates
  - Claims Agent        → claims history, fraud detection
  - Analytics Agent     → loss ratio, trends, portfolio summary
"""

from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage
from typing import Optional
import os
import re

from agents.underwriting_agent import build_underwriting_agent
from agents.claims_agent        import build_claims_agent
from agents.analytics_agent     import build_analytics_agent


# -----------------------------------------------------------
# Routing keywords
# -----------------------------------------------------------

ROUTING_RULES = {
    "underwriting": [
        "policy", "policies", "risk score", "risk tier", "churn", "non-renew",
        "renewal rate", "attrition", "premium", "expir", "carrier", "coverage",
        "state farm", "allstate", "geico", "quote", "bind"
    ],
    "claims": [
        "claim", "claims", "filed", "accident", "collision", "theft",
        "liability", "suspicious", "siu", "frequent claimant",
        "person id", "person_id", "claimant"
    ],
    "analytics": [
        "loss ratio", "loss sum", "claims trend", "trend", "portfolio", "summary",
        "overview", "dashboard", "monthly", "quarterly", "annual", "season",
        "pattern", "kpi", "performance", "profitab", "total premium", "aggregate",
        "all persons", "per person", "list all", "policy count", "premium sum",
        "claims count", "fraud flag", "person summary",
        "insurance compan", "carrier breakdown", "policies per carrier", "number of policies"
    ],
}


def _keyword_route(question: str) -> Optional[str]:
    """Fast keyword-based routing before calling the LLM."""
    q = question.lower()
    scores = {domain: 0 for domain in ROUTING_RULES}
    for domain, keywords in ROUTING_RULES.items():
        for kw in keywords:
            if kw in q:
                scores[domain] += 1
    sorted_scores = sorted(scores.values(), reverse=True)
    best = max(scores, key=scores.get)
    # Only route by keyword when there is a clear winner — ties go to LLM
    if sorted_scores[0] > 0 and sorted_scores[0] > sorted_scores[1]:
        return best
    return None


def _llm_route(question: str, llm) -> str:
    """LLM-based routing fallback for ambiguous questions."""
    response = llm.invoke([
        SystemMessage(content="""You are a routing assistant for an insurance chatbot.
Classify the user question into exactly one category:
- underwriting: policy lookup, risk scores, churn/renewal rates, premiums
- claims: claims history for a specific person, fraud risk for a specific person, frequent claimants list, SIU referrals
- analytics: loss ratios, portfolio summaries, monthly/quarterly TRENDS over time, KPIs, aggregate statistics

Key rule: questions about TRENDS over time (monthly, seasonal, yearly patterns) always go to analytics,
even if the word "claims" appears in the question.

Reply with ONLY one word: underwriting, claims, or analytics."""),
        HumanMessage(content=question)
    ])
    answer = response.content.strip().lower()
    if answer in ("underwriting", "claims", "analytics"):
        return answer
    return "underwriting"  # safe default


# -----------------------------------------------------------
# Supervisor
# -----------------------------------------------------------

class SupervisorAgent:
    """
    Entry point for all user questions.
    Routes to the appropriate specialist agent and returns the response.
    """

    def __init__(self, db_url: str = None):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            groq_api_key=os.getenv("GROQ_API_KEY")
        )

        # Build all specialist agents (shared LLM instance)
        self.agents = {
            "underwriting": build_underwriting_agent(db_url=db_url, llm=self.llm),
            "claims":       build_claims_agent(llm=self.llm),
            "analytics":    build_analytics_agent(llm=self.llm),
        }

        self.routing_log = []   # track routing decisions for debugging

    def route(self, question: str) -> str:
        """Determine which specialist should handle the question."""
        domain = _keyword_route(question) or _llm_route(question, self.llm)
        self.routing_log.append({"question": question, "routed_to": domain})
        return domain

    def run(self, question: str) -> dict:
        """
        Main entry point.
        Returns: { answer, routed_to, question }
        """
        domain = self.route(question)
        agent  = self.agents[domain]

        try:
            answer = agent.run(question)
        except Exception as e:
            answer = f"Error in {domain} agent: {str(e)}"

        return {
            "question":   question,
            "routed_to":  domain,
            "answer":     answer,
        }

    def get_routing_log(self) -> list:
        return self.routing_log


# -----------------------------------------------------------
# Convenience runner for testing
# -----------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    supervisor = SupervisorAgent(
        db_url=os.getenv("DATABASE_URL")
    )

    test_questions = [
        "What is the risk score for policy A-10234?",
        "How many claims does person P-001 have in the past 3 years?",
        "What is the churn rate for StateFarm in Q1 2026?",
        "Give me a portfolio summary",
        "Are there any high fraud risk customers?",
        "What is the loss ratio for California?",
    ]

    for q in test_questions:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        result = supervisor.run(q)
        print(f"Routed to: {result['routed_to'].upper()} AGENT")
        print(f"A: {result['answer']}")
