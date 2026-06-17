"""
FastAPI backend — exposes the multi-agent system as a REST API.
Run with: uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

from agents.supervisor_agent import SupervisorAgent
from db.database import seed_sample_data, get_engine

app = FastAPI(
    title="Insurance Policy Chatbot API",
    description="Multi-agent LLM chatbot for insurance carriers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize supervisor once at startup
supervisor: SupervisorAgent = None


@app.on_event("startup")
def startup():
    global supervisor
    db_url = os.getenv("DATABASE_URL", "sqlite:///./insurance_dev.db")

    # Seed sample data for dev/testing
    if "sqlite" in db_url:
        engine = get_engine(db_url)
        seed_sample_data(engine)

    supervisor = SupervisorAgent(db_url=db_url)
    print("Insurance Agent system ready.")


# -----------------------------------------------------------
# Request / Response models
# -----------------------------------------------------------


class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"  # future: per-session memory


class ChatResponse(BaseModel):
    question: str
    answer: str
    routed_to: str


class RoutingLogResponse(BaseModel):
    log: list


# -----------------------------------------------------------
# Endpoints
# -----------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Main chat endpoint — routes to the correct specialist agent."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    result = supervisor.run(req.question)
    return ChatResponse(
        question=result["question"],
        answer=result["answer"],
        routed_to=result["routed_to"],
    )


@app.get("/routing-log", response_model=RoutingLogResponse)
def routing_log():
    """Return the routing log for debugging."""
    return RoutingLogResponse(log=supervisor.get_routing_log())


@app.get("/health")
def health():
    return {"status": "ok", "agents": list(supervisor.agents.keys())}


@app.get("/agents")
def list_agents():
    """List all available agents and their tools."""
    return {
        "underwriting": {
            "description": "Policy lookup, risk scoring, churn/renewal rates",
            "tools": ["query_policy_db", "get_risk_score", "get_churn_rate"],
        },
        "claims": {
            "description": "Claims history, frequent claimants, fraud detection",
            "tools": ["get_claims_by_person", "find_frequent_claimants", "flag_fraud_risk"],
        },
        "analytics": {
            "description": "Loss ratios, portfolio summaries, trend analysis",
            "tools": ["get_loss_ratio", "get_portfolio_summary", "get_claims_trend"],
        },
    }
