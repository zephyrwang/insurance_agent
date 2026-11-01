"""
FastAPI backend — exposes the multi-agent system as a REST API.
Run with: uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
import os

load_dotenv()

from agents.supervisor_agent import SupervisorAgent
from agents.actor import Actor
from db.database import seed_sample_data, get_engine
from api.auth import (
    sign_actor,
    verify_token,
    check_staff_passcode,
    check_carrier_login,
    InvalidToken,
)

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
    session_id: str = "default"  # scopes conversation memory per client session
    token: str  # signed Actor token from /auth/staff-login or /auth/carrier-login


class ChatResponse(BaseModel):
    question: str
    answer: str
    routed_to: str


class RoutingLogResponse(BaseModel):
    log: list


class StaffLoginRequest(BaseModel):
    passcode: str


class CarrierLoginRequest(BaseModel):
    carrier_name: str
    access_code: str


class LoginResponse(BaseModel):
    token: str
    mode: str
    carrier_name: Optional[str] = None


# -----------------------------------------------------------
# Endpoints
# -----------------------------------------------------------


@app.post("/auth/staff-login", response_model=LoginResponse)
def staff_login(req: StaffLoginRequest):
    """Issue a signed staff token. Demo-grade: a single shared passcode, not per-user SSO."""
    if not check_staff_passcode(req.passcode):
        raise HTTPException(status_code=401, detail="Invalid passcode.")

    return LoginResponse(token=sign_actor(Actor.staff()), mode="staff")


@app.post("/auth/carrier-login", response_model=LoginResponse)
def carrier_login(req: CarrierLoginRequest):
    """Issue a signed carrier token scoped to one insurance company's own data."""
    carrier_name = check_carrier_login(req.carrier_name, req.access_code)
    if not carrier_name:
        raise HTTPException(status_code=401, detail="Invalid carrier name or access code.")

    return LoginResponse(
        token=sign_actor(Actor.carrier(carrier_name)), mode="carrier", carrier_name=carrier_name
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Main chat endpoint — routes to the correct specialist agent.

    The actor (staff vs. carrier, and which carrier) comes ONLY from the verified
    token payload — never from a client-editable field — so a request can't claim a
    different identity just by changing the JSON body.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        actor = verify_token(req.token)
    except InvalidToken as e:
        raise HTTPException(status_code=401, detail=str(e))

    result = supervisor.run(req.question, session_id=req.session_id, actor=actor)
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
        "greeting": {
            "description": "Introduces the assistant and hands off to the right specialist",
            "tools": [],
        },
    }
