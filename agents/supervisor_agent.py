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
from agents.claims_agent import build_claims_agent
from agents.analytics_agent import build_analytics_agent
from agents.greeting_agent import build_greeting_agent
from agents.output_validator import (
    enforce_tabular_format,
    unwrap_raw_action_json,
    extract_deferral_target,
)
from agents.actor import Actor


# -----------------------------------------------------------
# Routing keywords
# -----------------------------------------------------------

# Keywords are grounded in which database table the question queries:
#   underwriting → auto_policies columns only  (risk_score, premium, renewal_status, …)
#   claims       → claims table columns only    (claim_date, claim_type, amount, status, …)
#   analytics    → aggregates across both tables, or time-trend questions
# Carrier/company names are NOT routing signals — the same carrier can appear in
# any domain question ("Geico's churn rate" → underwriting, "Geico claims" → claims).
ROUTING_RULES = {
    "underwriting": [
        "policy",
        "policies",
        "risk score",
        "risk tier",
        "churn",
        "non-renew",
        "renewal rate",
        "renewal status",
        "attrition",
        "premium",
        "expir",
        "coverage",
        "quote",
        "bind",
        "holder",
        "policyholder",
    ],
    "claims": [
        "claims history",
        "claims for",
        "claim filed",
        "filed a claim",
        "accident",
        "collision",
        "theft",
        "liability",
        "suspicious",
        "siu",
        "frequent claimant",
        "person id",
        "person_id",
        "person",
        "claimant",
        "claim frequency",
        "claims frequency",
        "claim amount",
        "claim type",
        "open claim",
        "closed claim",
    ],
    "analytics": [
        "loss ratio",
        "loss sum",
        "claims trend",
        "trend",
        "portfolio",
        "summary",
        "overview",
        "dashboard",
        "monthly",
        "quarterly",
        "annual",
        "season",
        "pattern",
        "kpi",
        "performance",
        "profitab",
        "total premium",
        "aggregate",
        "all persons",
        "per person",
        "list all",
        "policy count",
        "premium sum",
        "claims count",
        "fraud flag",
        "person summary",
        "carrier breakdown",
        "policies per carrier",
        "number of policies",
        "number of claims",
        "how many claims",
        "claims per carrier",
        "claims by carrier",
        "insurance companies",
        "insurance company",
        "claim volume",
    ],
    "greeting": [
        "hello",
        "good morning",
        "good afternoon",
        "good evening",
        "what can you do",
        "who are you",
        "what are you",
        "how can you help",
        "get started",
        "thank you",
        "thanks",
        "goodbye",
        "see you",
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
    response = llm.invoke(
        [
            SystemMessage(
                content="""You are a routing assistant for an insurance chatbot.
Classify the user question into exactly one category:

- underwriting: queries the policy table only — policy lookup, risk scores, premiums,
  churn/renewal rates, coverage, expiry, policyholder details.
- claims: queries the claims table for a specific person or policy — claims history,
  frequent claimants by person, fraud risk for a person, SIU referrals.
- analytics: aggregates or joins BOTH tables, OR asks about carrier/company-level totals,
  OR asks about trends over time — loss ratios, portfolio summaries, monthly/quarterly/annual
  trends, KPIs. "Number of claims per carrier", "claims by company", "how many claims did
  Geico have in 2025" → analytics (requires joining claims + policies to get carrier_name,
  which is not in the claims table).
- greeting: NOT a data question at all — smalltalk, introductions ("what can you do",
  "who are you"), thanks, or goodbyes. Only use this when there is no actual policy/claims/
  analytics data being requested.

Key rules:
- Carrier/company names (Geico, StateFarm, Allstate, …) are NOT routing signals on their own.
  Route based on the data being requested, not the company name.
- Trend questions always go to analytics even if the word "claims" appears.
- If there is ANY real data question buried in the message, route to the data domain, not
  greeting — greeting is only for messages with no data question at all.

Reply with ONLY one word: underwriting, claims, analytics, or greeting."""
            ),
            HumanMessage(content=question),
        ]
    )
    answer = response.content.strip().lower()
    if answer in ("underwriting", "claims", "analytics", "greeting"):
        return answer
    return "underwriting"  # safe default for ambiguous data questions


# -----------------------------------------------------------
# Supervisor
# -----------------------------------------------------------


class SupervisorAgent:
    """
    Entry point for all user questions.
    Routes to the appropriate specialist agent and returns the response.
    """

    MAX_SESSIONS = 100  # evict oldest session's agents beyond this

    def __init__(self, db_url: str = None):
        self.llm = ChatGroq(
            model="openai/gpt-oss-120b", temperature=0, groq_api_key=os.getenv("GROQ_API_KEY")
        )
        self.db_url = db_url

        # Specialist agents are built per session (shared LLM instance) so
        # conversation memory is never shared between users.
        self._session_agents: dict[str, dict] = {}

        self.routing_log = []  # track routing decisions for debugging

    def _get_agents(self, session_id: str, actor: Actor = None) -> dict:
        """Get (or lazily build) the specialist agents for one session.

        Agents are rebuilt if a different actor shows up under the same session_id —
        this should never happen in practice (actor is derived server-side from a
        verified token per request, not trusted from the client), but caching by actor
        identity rather than session_id alone avoids silently serving one actor's
        agents (and their toolset) to another.
        """
        actor = actor or Actor.staff()
        cached = self._session_agents.get(session_id)
        if cached is None or cached["actor"] != actor:
            if len(self._session_agents) >= self.MAX_SESSIONS:
                self._session_agents.pop(next(iter(self._session_agents)))
            self._session_agents[session_id] = {
                "actor": actor,
                "agents": {
                    "underwriting": build_underwriting_agent(
                        db_url=self.db_url, llm=self.llm, actor=actor
                    ),
                    "claims": build_claims_agent(llm=self.llm, actor=actor),
                    "analytics": build_analytics_agent(llm=self.llm, actor=actor),
                    "greeting": build_greeting_agent(llm=self.llm, actor=actor),
                },
            }
        return self._session_agents[session_id]["agents"]

    @property
    def agents(self) -> dict:
        return self._get_agents("default")

    def route(self, question: str) -> str:
        """Determine which specialist should handle the question."""
        domain = _keyword_route(question) or _llm_route(question, self.llm)
        self.routing_log.append({"question": question, "routed_to": domain})
        return domain

    def run(self, question: str, session_id: str = "default", actor: Actor = None) -> dict:
        """
        Main entry point.
        Returns: { answer, routed_to, question }
        """
        actor = actor or Actor.staff()

        # Route every turn the same way, first or not — a clear, answerable question
        # on message #1 gets answered, not deferred behind a forced intro. The greeting
        # agent still naturally handles a session's first turn when it's actually
        # smalltalk (routing/_llm_route already classify "hello"-shaped messages as
        # "greeting"); it just doesn't get forced onto a real data question.
        domain = self.route(question)
        agent = self._get_agents(session_id, actor)[domain]

        try:
            answer = agent.invoke({"input": question})["output"]
            answer = unwrap_raw_action_json(answer)

            # A specialist's own prompt sometimes recognizes a question is out of its
            # scope and defers ("Please ask the Claims Agent") — that means the initial
            # routing missed. Transparently re-route to the named sibling once rather
            # than surfacing the deferral text as if it were the final answer; the user
            # already asked a complete question and shouldn't have to re-ask it.
            redirect_domain = extract_deferral_target(answer)
            if redirect_domain and redirect_domain != domain:
                domain = redirect_domain
                self.routing_log.append({"question": question, "routed_to": domain})
                agent = self._get_agents(session_id, actor)[domain]
                answer = agent.invoke({"input": question})["output"]
                answer = unwrap_raw_action_json(answer)

            answer = enforce_tabular_format(answer, self.llm, skip=(domain == "greeting"))
        except Exception as e:
            answer = f"Error in {domain} agent: {str(e)}"

        return {
            "question": question,
            "routed_to": domain,
            "answer": answer,
        }

    def get_routing_log(self) -> list:
        return self.routing_log


# -----------------------------------------------------------
# Convenience runner for testing
# -----------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    supervisor = SupervisorAgent(db_url=os.getenv("DATABASE_URL"))

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
