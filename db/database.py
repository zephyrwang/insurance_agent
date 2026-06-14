"""
Database connection module using SQLAlchemy.
Supports MySQL (production) and SQLite (local dev/testing).
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Integer, Float, Date, Enum, text
from datetime import date
import os

Base = declarative_base()

# -----------------------------------------------------------
# 1. ORM Models
# -----------------------------------------------------------

class AutoPolicy(Base):
    __tablename__ = "auto_policies"
    policy_id   = Column(String(20),  primary_key=True)
    person_id   = Column(String(20),  nullable=False, index=True)
    holder_name = Column(String(100), nullable=False)
    state       = Column(String(2),   nullable=False, index=True)
    risk_score      = Column(Integer,     nullable=False)
    status          = Column(Enum("active", "inactive", "cancelled"), default="active")
    start_date      = Column(Date,        nullable=False)
    premium         = Column(Float,       nullable=False)
    carrier_name    = Column(String(50),  nullable=True)
    expiry_date     = Column(Date,        nullable=True)
    renewal_status  = Column(Enum("renewed", "non-renewed"), nullable=True)

class Claim(Base):
    __tablename__ = "claims"
    claim_id    = Column(String(20),  primary_key=True)
    policy_id   = Column(String(20),  nullable=False, index=True)
    person_id   = Column(String(20),  nullable=False, index=True)
    claim_date  = Column(Date,        nullable=False, index=True)
    claim_type  = Column(Enum("Collision", "Liability", "Theft", "Weather", "Other"))
    amount      = Column(Float,       nullable=False)
    status      = Column(Enum("Open", "Closed", "Denied"), default="Open")


# -----------------------------------------------------------
# 2. Engine factory
# -----------------------------------------------------------

def get_engine(db_url: str = None):
    """
    Create SQLAlchemy engine.

    Production (MySQL):
        db_url = "mysql+pymysql://user:password@host:3306/insurance_db"

    Local dev (SQLite):
        db_url = "sqlite:///./insurance_dev.db"   (default if env var not set)
    """
    url = db_url or os.getenv(
        "DATABASE_URL",
        "sqlite:///./insurance_dev.db"   # fallback for local dev
    )
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, echo=False)


def get_session(engine=None):
    engine = engine or get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db(engine=None):
    """Create all tables (run once on setup)."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    print("Database tables created.")


# -----------------------------------------------------------
# 3. Seed sample data (dev/testing only)
# -----------------------------------------------------------

def seed_sample_data(engine=None):
    engine = engine or get_engine()
    init_db(engine)
    session = get_session(engine)

    if session.query(AutoPolicy).count() > 0:
        print("Sample data already exists — skipping seed.")
        return

    policies = [
        AutoPolicy(policy_id="A-10234", person_id="P-001", holder_name="James T.",
                   state="CA", risk_score=92, status="active",
                   start_date=date(2021, 3, 15), premium=1850.0),
        AutoPolicy(policy_id="A-10235", person_id="P-002", holder_name="Maria G.",
                   state="CA", risk_score=88, status="active",
                   start_date=date(2020, 7, 1), premium=1600.0),
        AutoPolicy(policy_id="A-10236", person_id="P-003", holder_name="Kevin L.",
                   state="TX", risk_score=55, status="active",
                   start_date=date(2022, 1, 10), premium=980.0),
        AutoPolicy(policy_id="A-10237", person_id="P-004", holder_name="Susan P.",
                   state="FL", risk_score=81, status="active",
                   start_date=date(2019, 11, 20), premium=2100.0),
        AutoPolicy(policy_id="A-10238", person_id="P-005", holder_name="David C.",
                   state="NY", risk_score=42, status="inactive",
                   start_date=date(2023, 5, 5), premium=750.0),
        AutoPolicy(policy_id="A-10239", person_id="P-001", holder_name="James T.",
                   state="CA", risk_score=92, status="active",
                   start_date=date(2023, 3, 15), premium=1950.0),
    ]

    claims = [
        Claim(claim_id="C-4421", policy_id="A-10234", person_id="P-001",
              claim_date=date(2023, 4, 12), claim_type="Collision",  amount=8200,  status="Closed"),
        Claim(claim_id="C-5103", policy_id="A-10234", person_id="P-001",
              claim_date=date(2024, 1, 8),  claim_type="Liability",  amount=3400,  status="Closed"),
        Claim(claim_id="C-5891", policy_id="A-10239", person_id="P-001",
              claim_date=date(2024, 9, 15), claim_type="Collision",  amount=12700, status="Open"),
        Claim(claim_id="C-6012", policy_id="A-10235", person_id="P-002",
              claim_date=date(2025, 2, 20), claim_type="Theft",      amount=5500,  status="Open"),
        Claim(claim_id="C-6100", policy_id="A-10235", person_id="P-002",
              claim_date=date(2025, 8, 3),  claim_type="Weather",    amount=2200,  status="Closed"),
        Claim(claim_id="C-6200", policy_id="A-10237", person_id="P-004",
              claim_date=date(2025, 11, 10),claim_type="Collision",  amount=9800,  status="Open"),
    ]

    session.add_all(policies + claims)
    session.commit()
    print(f"Seeded {len(policies)} policies and {len(claims)} claims.")
