"""
Streamlit UI for the Insurance Policy Multi-Agent Chatbot.

Run with:
    streamlit run streamlit_app.py

Make sure you have set GROQ_API_KEY in your .env file.
"""

import streamlit as st
import os
import json
import time
import re
import pandas as pd
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Page config ────────────────────────────────────────────
st.set_page_config(
    page_title="Insurance Policy Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────
st.markdown("""
<style>
/* Main background */
.main { background-color: #f8f9fb; }

/* Chat message bubbles */
.user-bubble {
    background: #1D9E75;
    color: white;
    padding: 12px 16px;
    border-radius: 18px 18px 4px 18px;
    margin: 4px 0;
    max-width: 80%;
    margin-left: auto;
    font-size: 14px;
    line-height: 1.5;
}
.bot-bubble {
    background: white;
    color: #1a1a1a;
    padding: 12px 16px;
    border-radius: 18px 18px 18px 4px;
    margin: 4px 0;
    max-width: 85%;
    border: 1px solid #e8eaed;
    font-size: 14px;
    line-height: 1.5;
}
.agent-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 500;
    padding: 2px 10px;
    border-radius: 12px;
    margin-bottom: 6px;
}
.badge-underwriting { background: #E1F5EE; color: #0F6E56; }
.badge-claims       { background: #E6F1FB; color: #185FA5; }
.badge-analytics    { background: #FAEEDA; color: #633806; }
.badge-supervisor   { background: #EEF0F8; color: #3C3489; }

/* Routing indicator */
.routing-box {
    background: #f1f3f9;
    border-left: 3px solid #7F77DD;
    padding: 8px 12px;
    border-radius: 0 8px 8px 0;
    font-size: 12px;
    color: #534AB7;
    margin: 4px 0 8px 0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e8eaed;
}

/* Input area */
.stTextInput > div > div > input {
    border-radius: 24px !important;
    border: 1.5px solid #e8eaed !important;
    padding: 10px 18px !important;
    font-size: 14px !important;
}

/* Metric cards */
div[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e8eaed;
    border-radius: 10px;
    padding: 12px;
}

/* Hide Streamlit branding */
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Agent color / label maps ────────────────────────────────
AGENT_META = {
    "underwriting": {"label": "Underwriting Agent", "badge": "badge-underwriting", "icon": "📋"},
    "claims":       {"label": "Claims Agent",        "badge": "badge-claims",       "icon": "📁"},
    "analytics":    {"label": "Analytics Agent",     "badge": "badge-analytics",    "icon": "📊"},
}

SAMPLE_QUESTIONS = {
    "📋 Underwriting": [
        "What is the risk score for policy A-10234?",
        "Show all active policies in California with risk score above 80",
        "What is the churn rate for StateFarm in Q1 2026?",
        "How many active policies do we have in Texas?",
    ],
    "📁 Claims": [
        "How many claims does person P-001 have in the past 3 years?",
        "Find all persons with 2 or more claims in the past year",
        "What is the fraud risk for person P-002?",
        "Show claims history for policy A-10234",
    ],
    "📊 Analytics": [
        "Give me a portfolio summary",
        "What is the loss ratio for California?",
        "Show me the monthly claims trend for the past year",
        "What is the overall portfolio loss ratio?",
        "List all persons with their policy count, premium sum, claims count, loss ratio, risk score and fraud flag",
        "List all insurance companies with the number of policies in 2024, 2025, 2026",
    ],
}


# ── Response renderer ──────────────────────────────────────

def _parse_md_table(table_lines: list) -> Optional[pd.DataFrame]:
    """Convert markdown table lines into a DataFrame."""
    rows = [l for l in table_lines if not re.match(r"^\|[\s\-:|]+\|$", l)]
    if len(rows) < 2:
        return None
    headers = [h.strip() for h in rows[0].split("|")[1:-1]]
    data = [[c.strip() for c in r.split("|")[1:-1]] for r in rows[1:] if r.strip()]
    if not data or not headers:
        return None
    # Pad rows to header length
    data = [row + [""] * (len(headers) - len(row)) for row in data]
    return pd.DataFrame(data, columns=headers)


def render_agent_response(content: str):
    """
    Split LLM response into table sections and text sections.
    Tables → st.dataframe (pretty, sortable).
    Text  → st.markdown (with $ escaped to avoid LaTeX).
    """
    lines = content.split("\n")
    sections = []
    current_text: List[str] = []
    current_table: List[str] = []

    for line in lines:
        if re.match(r"^\s*\|.+\|\s*$", line):
            if current_text:
                sections.append(("text", "\n".join(current_text)))
                current_text = []
            current_table.append(line.strip())
        else:
            if current_table:
                sections.append(("table", current_table))
                current_table = []
            current_text.append(line)
    if current_table:
        sections.append(("table", current_table))
    if current_text:
        sections.append(("text", "\n".join(current_text)))

    for kind, body in sections:
        if kind == "table":
            df = _parse_md_table(body)
            if df is not None:
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.markdown("\n".join(body))
        else:
            text = body.strip()
            if text:
                st.markdown(text.replace("$", r"\$"))


# ── Feedback persistence ────────────────────────────────────
FEEDBACK_LOG_PATH = os.path.join(os.path.dirname(__file__), "feedback_log.jsonl")


def log_feedback(msg_id: int, question: str, agent: Optional[str], answer: str, rating: str):
    """Append a feedback record to the local JSONL log (best-effort, never raises)."""
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "msg_id": msg_id,
        "question": question,
        "agent": agent,
        "answer": answer,
        "rating": rating,
    }
    try:
        with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ── Session state init ──────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "routing_log" not in st.session_state:
    st.session_state.routing_log = []
if "supervisor" not in st.session_state:
    st.session_state.supervisor = None
if "total_queries" not in st.session_state:
    st.session_state.total_queries = {"underwriting": 0, "claims": 0, "analytics": 0}
if "msg_id_counter" not in st.session_state:
    st.session_state.msg_id_counter = 0
if "ratings" not in st.session_state:
    st.session_state.ratings = {}  # {msg_id: "satisfied" | "basic" | "incorrect"}


def _next_msg_id() -> int:
    st.session_state.msg_id_counter += 1
    return st.session_state.msg_id_counter


# ── Load supervisor (cached) ────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_supervisor():
    """
    Load the supervisor agent.
    Uses MockSupervisorAgent by default (no API key needed).
    Switch to real SupervisorAgent once you have an OpenAI key.
    """
    try:
        api_key = os.getenv("GROQ_API_KEY", "")
        if api_key and api_key.startswith("gsk_"):
            from agents.supervisor_agent import SupervisorAgent
            db_url = os.getenv("DATABASE_URL", "sqlite:///./insurance_dev.db")
            return SupervisorAgent(db_url=db_url), None
        else:
            from mock_supervisor import MockSupervisorAgent
            return MockSupervisorAgent(), None
    except Exception as e:
        return None, str(e)


# ── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ Insurance Agent")
    st.markdown("*Multi-agent AI chatbot for policy analysis*")
    st.divider()

    # Agent status
    st.markdown("#### Active Agents")
    for domain, meta in AGENT_META.items():
        st.markdown(
            f'<span class="agent-badge {meta["badge"]}">'
            f'{meta["icon"]} {meta["label"]}</span>',
            unsafe_allow_html=True
        )

    st.divider()

    # Query stats
    st.markdown("#### Session Stats")
    total = sum(st.session_state.total_queries.values())
    col1, col2 = st.columns(2)
    col1.metric("Total Queries", total)
    col2.metric("Messages", len(st.session_state.messages))

    if total > 0:
        for domain, count in st.session_state.total_queries.items():
            if count > 0:
                pct = int(100 * count / total)
                meta = AGENT_META[domain]
                st.markdown(
                    f'<div style="font-size:12px; margin:2px 0;">'
                    f'<span class="agent-badge {meta["badge"]}">'
                    f'{meta["icon"]} {meta["label"]}: {count} ({pct}%)'
                    f'</span></div>',
                    unsafe_allow_html=True
                )

    st.divider()

    # Sample questions
    st.markdown("#### Sample Questions")
    for category, questions in SAMPLE_QUESTIONS.items():
        with st.expander(category):
            for q in questions:
                if st.button(q, key=f"sample_{q[:30]}", use_container_width=True):
                    st.session_state["pending_question"] = q

    st.divider()

    # Routing log
    if st.session_state.routing_log:
        st.markdown("#### Routing Log")
        for entry in reversed(st.session_state.routing_log[-5:]):
            meta = AGENT_META.get(entry["routed_to"], {})
            icon = meta.get("icon", "🤖")
            st.markdown(
                f'<div style="font-size:11px; color:#666; margin:2px 0;">'
                f'{icon} <b>{entry["routed_to"].title()}</b><br>'
                f'<span style="color:#999">{entry["question"][:40]}...</span>'
                f'</div>',
                unsafe_allow_html=True
            )

    # Clear chat
    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.routing_log = []
        st.session_state.ratings = {}
        st.session_state.total_queries = {"underwriting": 0, "claims": 0, "analytics": 0}
        st.rerun()

    # Mode indicator + optional API key
    st.divider()
    st.markdown("#### Configuration")
    api_key = os.getenv("GROQ_API_KEY", "")
    if api_key and api_key.startswith("gsk_"):
        st.success("🤖 Live mode — Llama 3.3 70B (Groq)")
    else:
        st.info("🧪 Demo mode — mock responses")
    api_key_input = st.text_input(
        "Groq API Key (optional)",
        value="",
        type="password",
        placeholder="gsk_... (leave blank for demo mode)"
    )
    if api_key_input and api_key_input.startswith("gsk_"):
        os.environ["GROQ_API_KEY"] = api_key_input
        st.cache_resource.clear()
        st.rerun()


# ── Main area ───────────────────────────────────────────────
st.markdown("## 🛡️ Insurance Policy Chatbot")
st.markdown(
    "Ask questions about **policies**, **claims**, **fraud**, or **portfolio analytics**. "
    "The supervisor will automatically route your question to the right specialist agent."
)

# Agent capability cards
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""
    <div style="background:#E1F5EE; border:1px solid #e8eaed; border-radius:10px; padding:14px;">
        <div style="font-size:13px; font-weight:500; color:#0F6E56;">📋 Underwriting Agent</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">
        Policy lookup · Risk scores · Churn rates · Carrier analysis
        </div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div style="background:#E6F1FB; border:1px solid #e8eaed; border-radius:10px; padding:14px;">
        <div style="font-size:13px; font-weight:500; color:#185FA5;">📁 Claims Agent</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">
        Claims history · Frequent claimants · Fraud detection · SIU flags
        </div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown("""
    <div style="background:#FAEEDA; border:1px solid #e8eaed; border-radius:10px; padding:14px;">
        <div style="font-size:13px; font-weight:500; color:#633806;">📊 Analytics Agent</div>
        <div style="font-size:12px; color:#666; margin-top:4px;">
        Loss ratios · Portfolio summary · Trend analysis · KPIs
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Chat history display
chat_container = st.container()
with chat_container:
    if not st.session_state.messages:
        st.markdown(
            '<div style="text-align:center; color:#aaa; padding:40px 0; font-size:14px;">'
            '💬 Ask a question to get started, or pick one from the sidebar.'
            '</div>',
            unsafe_allow_html=True
        )

    for idx, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            st.markdown(
                f'<div style="display:flex; justify-content:flex-end; margin:8px 0;">'
                f'<div class="user-bubble">{msg["content"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            meta = AGENT_META.get(msg.get("agent", ""), {})
            badge_class = meta.get("badge", "badge-supervisor")
            label = meta.get("label", "Supervisor")
            icon  = meta.get("icon", "🤖")
            ts    = msg.get("timestamp", "")
            routing_html = (
                f'<div class="routing-box">⚡ Routed to <b>{label}</b></div>'
                if msg.get("agent") else ""
            )
            # Header (badge + routing) in HTML, content as native markdown so tables render
            st.markdown(
                f'<div style="margin:8px 0 2px 0;">'
                f'<span class="agent-badge {badge_class}">{icon} {label}</span>'
                f'<span style="font-size:11px; color:#aaa; margin-left:8px;">{ts}</span>'
                f'{routing_html}'
                f'</div>',
                unsafe_allow_html=True
            )
            with st.container():
                render_agent_response(msg["content"])

            msg_id = msg.get("id", idx)
            current_rating = st.session_state.ratings.get(msg_id)
            RATING_OPTIONS = {
                "satisfied": "👍 Satisfied",
                "basic": "🙂 Basic Good",
                "incorrect": "👎 Incorrect",
            }
            rb_cols = st.columns([1, 1, 1, 5])
            for col, (rating_key, rating_label) in zip(rb_cols[:3], RATING_OPTIONS.items()):
                with col:
                    is_selected = current_rating == rating_key
                    if st.button(
                        rating_label,
                        key=f"rate_{msg_id}_{rating_key}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.ratings[msg_id] = rating_key
                        prev_question = ""
                        if idx > 0 and st.session_state.messages[idx - 1]["role"] == "user":
                            prev_question = st.session_state.messages[idx - 1]["content"]
                        log_feedback(
                            msg_id=msg_id,
                            question=prev_question,
                            agent=msg.get("agent"),
                            answer=msg["content"],
                            rating=rating_key,
                        )
                        st.rerun()


# ── Input area ──────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
input_col, btn_col = st.columns([6, 1])

with input_col:
    user_input = st.text_input(
        label="Ask a question",
        label_visibility="collapsed",
        placeholder="e.g. What is the churn rate for StateFarm in Q1 2026?",
        key="chat_input"
    )
with btn_col:
    send_clicked = st.button("Send ➤", use_container_width=True, type="primary")

# Handle sidebar sample question clicks
pending = st.session_state.pop("pending_question", None)
question_to_process = pending or (user_input if send_clicked else None)


# ── Process question ─────────────────────────────────────────
if question_to_process and question_to_process.strip():
    question = question_to_process.strip()

    # Add user message
    st.session_state.messages.append({
        "role": "user",
        "content": question,
        "id": _next_msg_id()
    })

    # Load supervisor
    supervisor, load_error = load_supervisor()

    if load_error or not supervisor:
        error_msg = (
            f"Could not initialize the agent system: {load_error}. "
            "Please check your GROQ_API_KEY and DATABASE_URL."
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": error_msg,
            "agent": None,
            "timestamp": datetime.now().strftime("%H:%M"),
            "id": _next_msg_id()
        })
    else:
        with st.spinner("Thinking..."):
            try:
                result = supervisor.run(question)
                domain = result["routed_to"]
                answer = result["answer"]

                # Update routing log and stats
                st.session_state.routing_log.append({
                    "question": question,
                    "routed_to": domain
                })
                st.session_state.total_queries[domain] += 1

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "agent": domain,
                    "timestamp": datetime.now().strftime("%H:%M"),
                    "id": _next_msg_id()
                })

            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"An error occurred: {str(e)}. Please check your API key and database connection.",
                    "agent": None,
                    "timestamp": datetime.now().strftime("%H:%M"),
                    "id": _next_msg_id()
                })

    st.rerun()
