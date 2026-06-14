"""
Underwriting Specialist Agent
Handles: policy lookup, risk scoring, churn/renewal rate analysis.
"""

from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain.tools import Tool
from sqlalchemy import create_engine, text as sa_text

from tools.underwriting_tools import UNDERWRITING_TOOLS
import os
import re


SYSTEM_PROMPT = """You are an Underwriting Specialist Agent for an insurance company.
You have deep expertise in auto insurance policy analysis, risk assessment, and renewal rates.

Your responsibilities:
- Look up and analyze individual policies
- Assess risk scores and explain risk tiers
- Calculate churn and non-renewal rates by carrier and period
- Answer questions about policy status, premiums, and coverage

Output format rules — ALWAYS use a markdown table, never prose:
- Start with a bold title, e.g. **Risk Score — Policy A-10234**
- Single record: vertical two-column table | Field | Value |
- Multiple records: horizontal table with one column per field
- After the table, add a **Comment** section with 2-3 bullet point insights
- NEVER output data as a numbered list, bullet list, or prose — always a markdown table
- Risk tier: 🔴 High | 🟡 Medium | 🟢 Low
- Premium format: $1,850 / yr  |  Risk score format: 92 / 100
- Churn rate format: 8.3% (X of Y policies non-renewed)

Rules:
- Only answer underwriting-related questions
- If a question is about claims or fraud, say: "Please ask the Claims Agent"
- If a question is about trends or portfolio analytics, say: "Please ask the Analytics Agent"
"""

DB_SCHEMA = """
Table: auto_policies
  policy_id, person_id, holder_name, state (2-letter), risk_score (0-100),
  status (active/inactive/cancelled), start_date, premium,
  carrier_name (StateFarm/GEICO/Allstate/Progressive/Nationwide),
  expiry_date, renewal_status (renewed/non-renewed)

Table: claims
  claim_id, policy_id, person_id, claim_date,
  claim_type (Collision/Liability/Theft/Weather/Other),
  amount, status (Open/Closed/Denied)
"""


def _build_nl_sql_tool(db_url: str, llm):
    """Replace SQLDatabaseChain with a clean NL→SQL executor."""
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)

    def query_fn(question: str) -> str:
        response = llm.invoke([
            SystemMessage(content=f"""You are a SQL expert. Generate a valid SQLite query.

Schema:
{DB_SCHEMA}

Rules:
- Return ONLY the raw SQL — no markdown, no code fences, no explanation
- Do NOT add LIMIT unless the user explicitly asks for a limited number of results
- Use SQLite-compatible syntax (strftime, not DATE_FORMAT)
"""),
            HumanMessage(content=question)
        ])

        sql = response.content.strip()
        # Strip any markdown code fences the LLM may add
        sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).replace("```", "").strip()

        try:
            with engine.connect() as conn:
                rows = conn.execute(sa_text(sql)).mappings().fetchall()
            if not rows:
                return "No results found."
            cols = list(rows[0].keys())
            header = " | ".join(cols)
            divider = " | ".join("---" for _ in cols)
            body = "\n".join(" | ".join(str(r[c]) for c in cols) for r in rows)
            return f"{header}\n{divider}\n{body}"
        except Exception as e:
            return f"SQL error: {e}\nGenerated SQL was: {sql}"

    return query_fn


def build_underwriting_agent(db_url: str = None, llm=None):
    llm = llm or ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

    tools = list(UNDERWRITING_TOOLS)

    if db_url:
        tools.append(Tool(
            name="query_policy_db",
            func=_build_nl_sql_tool(db_url, llm),
            description="""Query the auto policy database with natural language.
            Use for complex lookups: filtering by state, carrier, status, risk score, count, etc.
            Input: a natural language question about policies.
            Examples: 'How many active policies are there?', 'Find all policies in CA with risk score above 80'"""
        ))

    memory = ConversationBufferWindowMemory(
        memory_key="chat_history",
        return_messages=True,
        k=5
    )

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        verbose=True,
        agent_kwargs={"system_message": SYSTEM_PROMPT},
        handle_parsing_errors=True,
    )

    return agent
