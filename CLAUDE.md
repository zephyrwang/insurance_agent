# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-agent LLM chatbot for insurance carriers, built with LangChain, FastAPI, and Streamlit. A supervisor agent routes natural-language questions to one of three domain specialists, each backed by SQL-querying tools over a shared policy/claims database.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit UI (primary entry point)
streamlit run streamlit_app.py        # http://localhost:8501

# Run the FastAPI backend
uvicorn api.main:app --reload --port 8000   # docs at /docs

# Quick CLI test of routing + agents (runs a fixed set of sample questions)
python -m agents.supervisor_agent
```

There is no test suite, linter, or build step configured in this repo.

### Environment

Configured via `.env` (see `.env.example`):
- `GROQ_API_KEY` — required for live mode (Groq-hosted Llama 3.3 70B via `langchain-groq`). If unset/invalid, the Streamlit app falls back to `MockSupervisorAgent` (canned demo responses, no LLM/DB calls).
- `DATABASE_URL` — defaults to `sqlite:///./insurance_dev.db` if unset. For production, use a MySQL URL (`mysql+pymysql://...`).

## Architecture

**Request flow:** UI/API → `SupervisorAgent.run()` → routing → specialist `agent.run()` (LangChain ReAct loop) → tool call → SQL via `db/database.py` → markdown-formatted answer back to caller.

### Supervisor routing (`agents/supervisor_agent.py`)
- Two-stage routing: fast `_keyword_route()` against `ROUTING_RULES` keyword lists per domain (underwriting/claims/analytics). If no domain has a clear lead (tie or no matches), falls back to `_llm_route()`, which asks the LLM to classify.
- Key disambiguation rule baked into the LLM router prompt: questions about **trends over time** always go to `analytics`, even if the word "claims" appears.
- All three specialist agents are built once at `SupervisorAgent.__init__` and share a single `ChatGroq` LLM instance.

### Specialist agents (`agents/*_agent.py`)
Each is a LangChain `CHAT_CONVERSATIONAL_REACT_DESCRIPTION` agent (`initialize_agent`) with:
- A domain-specific `SYSTEM_PROMPT` that dictates strict output formatting (always markdown tables + a **Comment** section with bullet insights — never prose/lists) and tool-selection rules.
- `ConversationBufferWindowMemory` (k=5).
- Each prompt explicitly tells the agent to defer out-of-scope questions to the correct sibling agent (e.g., claims agent says "Please ask the Underwriting Agent" for risk-score questions) — when adjusting routing keywords or prompts, keep these cross-references consistent across all three agents and `ROUTING_RULES`.

### Tools (`tools/*_tools.py`)
Plain Python functions wrapped as LangChain `Tool`s, each opening its own SQLAlchemy session via `db.database.get_session()`:
- **Underwriting** (`underwriting_tools.py`): `get_risk_score`, `get_churn_rate` (parses carrier name + quarter/year from free text). Also gets a dynamically built `query_policy_db` NL→SQL tool (`agents/underwriting_agent.py:_build_nl_sql_tool`) only when `db_url` is provided — this tool has the LLM generate raw SQLite directly against the `DB_SCHEMA` string and executes it.
- **Claims** (`claims_tools.py`): `get_claims_by_person` (last 3 years), `find_frequent_claimants` (parses `min_claims=N years=Y` from input), `flag_fraud_risk` (rule-based score from claim count/amount/open claims, built on top of `get_claims_by_person`).
- **Analytics** (`analytics_tools.py`): `get_loss_ratio` (parses carrier/state/year from free text, joins policies+closed claims), plus portfolio summary / trend / person-summary / carrier-summary tools referenced by the analytics system prompt.

When adding a tool, write a precise `description` — the ReAct agent picks tools by matching the question against these descriptions, and the system prompts also encode strict "use X only when Y" rules that must stay in sync.

### Database (`db/database.py`)
SQLAlchemy models `AutoPolicy` (`auto_policies`) and `Claim` (`claims`). `get_engine()`/`get_session()` read `DATABASE_URL`, defaulting to local SQLite. `seed_sample_data()` populates a small fixed dataset if the `auto_policies` table is empty (called automatically by `api/main.py` on startup for SQLite). `seed_rich_data.py` is a separate, larger seeding script.

### UI (`streamlit_app.py`)
- Caches the supervisor/mock-supervisor via `@st.cache_resource`; clearing the cache (e.g. after entering an API key in the sidebar) rebuilds it.
- `render_agent_response()` splits agent output into markdown-table vs. text sections and renders tables via `st.dataframe` — this depends on the specialist system prompts consistently producing markdown tables.
- Tracks routing decisions and per-domain query counts in `st.session_state` for the sidebar "Routing Log" and "Session Stats".

### API (`api/main.py`)
Thin FastAPI wrapper around the same `SupervisorAgent` (`/chat`, `/routing-log`, `/health`, `/agents`). Seeds the SQLite DB on startup if empty.
