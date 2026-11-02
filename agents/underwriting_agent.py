"""
Underwriting Specialist Agent
Handles: policy lookup, risk scoring, churn/renewal rate analysis.
"""

from langchain.schema import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain.tools import Tool
from sqlalchemy import create_engine, text as sa_text

from agents.base import build_specialist_agent
from agents.actor import Actor
from tools.underwriting_tools import UNDERWRITING_TOOLS
from tools.scoped_tools import scope_underwriting_tools
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

Tool selection rules — follow these strictly:
- Question gives a specific policy_id → use get_risk_score
- Question asks to LIST, SHOW, or SAMPLE N policies WITHOUT a specific policy_id → use list_policies
- Question asks about churn, attrition, non-renewal, or retention rate → use get_churn_rate
- If the user says they don't know a policy_id, or asks for examples/samples, use list_policies
  — do NOT just ask them to supply IDs

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


MAX_SQL_ROWS = 200


def _is_single_select(sql: str) -> bool:
    """Allow only one SELECT (or WITH … SELECT) statement — the LLM output is
    executed verbatim, so anything else (DELETE, UPDATE, stacked statements) is refused."""
    stripped = sql.strip().rstrip(";").strip()
    if ";" in stripped:
        return False
    return re.match(r"(?i)^(select|with)\b", stripped) is not None


def _build_nl_sql_tool(db_url: str, llm):
    """Replace SQLDatabaseChain with a clean NL→SQL executor."""
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)

    def query_fn(question: str) -> str:
        response = llm.invoke(
            [
                SystemMessage(
                    content=f"""You are a SQL expert. Generate a valid SQLite query.

Schema:
{DB_SCHEMA}

Rules:
- Return ONLY the raw SQL — no markdown, no code fences, no explanation
- Do NOT add LIMIT unless the user explicitly asks for a limited number of results
- Use SQLite-compatible syntax (strftime, not DATE_FORMAT)
"""
                ),
                HumanMessage(content=question),
            ]
        )

        sql = response.content.strip()
        # Strip any markdown code fences the LLM may add
        sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).replace("```", "").strip()

        if not _is_single_select(sql):
            return (
                "Refused: only a single read-only SELECT query is allowed.\n"
                f"Generated SQL was: {sql}"
            )

        try:
            with engine.connect() as conn:
                if engine.dialect.name == "sqlite":
                    conn.exec_driver_sql("PRAGMA query_only = ON")
                result = conn.execute(sa_text(sql)).mappings()
                rows = result.fetchmany(MAX_SQL_ROWS + 1)
            truncated = len(rows) > MAX_SQL_ROWS
            rows = rows[:MAX_SQL_ROWS]
            if not rows:
                return "No results found."
            cols = list(rows[0].keys())
            header = " | ".join(cols)
            divider = " | ".join("---" for _ in cols)
            body = "\n".join(" | ".join(str(r[c]) for c in cols) for r in rows)
            note = f"\n(Showing first {MAX_SQL_ROWS} rows.)" if truncated else ""
            return f"{header}\n{divider}\n{body}{note}"
        except Exception as e:
            return f"SQL error: {e}\nGenerated SQL was: {sql}"

    return query_fn


def build_underwriting_agent(db_url: str = None, llm=None, actor: Actor = None):
    llm = llm or ChatGroq(
        model="openai/gpt-oss-120b", temperature=0, groq_api_key=os.getenv("GROQ_API_KEY")
    )

    is_carrier = actor is not None and actor.mode == "carrier"
    tools = scope_underwriting_tools(actor) if is_carrier else list(UNDERWRITING_TOOLS)

    # The NL→SQL tool has no fixed WHERE-clause seam to enforce carrier scoping through —
    # the LLM writes the entire query — so it's staff-only regardless of any other scoping.
    if db_url and not is_carrier:
        tools.append(
            Tool(
                name="query_policy_db",
                func=_build_nl_sql_tool(db_url, llm),
                description="""Query the auto policy database with natural language.
            Use for complex lookups: filtering by state, carrier, status, risk score, count, etc.
            Input: a natural language question about policies.
            Examples: 'How many active policies are there?', 'Find all policies in CA with risk score above 80'""",
            )
        )

    agent = build_specialist_agent(tools, SYSTEM_PROMPT, llm)

    return agent
