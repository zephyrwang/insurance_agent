# Insurance Policy Multi-Agent Chatbot

A multi-agent LLM chatbot for insurance carriers, built with LangChain, FastAPI, and Streamlit.

## Architecture

```
SupervisorAgent
├── UnderwritingAgent  — policy lookup, risk scores, churn rates
├── ClaimsAgent        — claims history, fraud detection, SIU flags
└── AnalyticsAgent     — loss ratios, portfolio summary, trend analysis
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and set:
#   OPENAI_API_KEY=sk-...
#   DATABASE_URL=mysql+pymysql://user:password@host:3306/insurance_db
#
# For local dev, leave DATABASE_URL unset to use SQLite automatically.
```

### 3. Run the Streamlit UI
```bash
streamlit run streamlit_app.py
```
Open http://localhost:8501 in your browser.

### 4. (Optional) Run the FastAPI backend
```bash
uvicorn api.main:app --reload --port 8000
```
API docs at http://localhost:8000/docs

---

## Project Structure

```
insurance_agent/
├── streamlit_app.py          # Streamlit demo UI
├── requirements.txt
├── .env.example
│
├── db/
│   └── database.py           # SQLAlchemy models + seed data
│
├── tools/
│   ├── underwriting_tools.py # get_risk_score, get_churn_rate
│   ├── claims_tools.py       # get_claims_by_person, flag_fraud_risk
│   └── analytics_tools.py    # get_loss_ratio, get_portfolio_summary
│
├── agents/
│   ├── supervisor_agent.py   # Routes questions to specialists
│   ├── underwriting_agent.py
│   ├── claims_agent.py
│   └── analytics_agent.py
│
└── api/
    └── main.py               # FastAPI REST endpoints
```

---

## Sample Questions to Try

**Underwriting**
- "What is the risk score for policy A-10234?"
- "Show all active California policies with risk score above 80"
- "What is the churn rate for StateFarm in Q1 2026?"

**Claims**
- "How many claims does person P-001 have in the past 3 years?"
- "Find all persons with 2 or more claims in the past year"
- "What is the fraud risk for person P-002?"

**Analytics**
- "Give me a portfolio summary"
- "What is the loss ratio for California?"
- "Show monthly claims trends for the past year"

---

## Production Deployment

1. Switch DATABASE_URL to your MySQL connection string
2. Set up role-based access control so each carrier only sees their own data
3. Consider replacing OpenAI with a self-hosted LLaMA 2 model for data privacy
4. Deploy FastAPI on AWS/Azure and Streamlit on Streamlit Cloud or internal portal
