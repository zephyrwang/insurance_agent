import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, AutoPolicy, Claim
from tools.analytics_tools import get_loss_ratio


@pytest.fixture(scope="module")
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    Session = sessionmaker(bind=e)
    session = Session()

    session.add_all([
        AutoPolicy(policy_id="L-01", person_id="P-A", holder_name="A", state="CA",
                    risk_score=50, status="active", start_date=date(2024, 1, 1),
                    premium=1000.0, carrier_name="GEICO"),
        AutoPolicy(policy_id="L-02", person_id="P-B", holder_name="B", state="CA",
                    risk_score=50, status="active", start_date=date(2024, 1, 1),
                    premium=2000.0, carrier_name="GEICO"),
        AutoPolicy(policy_id="L-03", person_id="P-C", holder_name="C", state="TX",
                    risk_score=50, status="active", start_date=date(2024, 1, 1),
                    premium=500.0, carrier_name="StateFarm"),
    ])
    session.add_all([
        Claim(claim_id="LC-01", policy_id="L-01", person_id="P-A",
              claim_date=date(2024, 6, 1), claim_type="Collision",
              amount=600, status="Closed"),
        Claim(claim_id="LC-02", policy_id="L-03", person_id="P-C",
              claim_date=date(2024, 6, 1), claim_type="Collision",
              amount=650, status="Closed"),
    ])
    session.commit()
    session.close()
    return e


@pytest.fixture(autouse=True)
def patch_db(engine, monkeypatch):
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("tools.analytics_tools.get_session", lambda: Session())

def test_healthy_carrier_loss_ratio():
    result = get_loss_ratio("carrier=GEICO")
    assert result["total_premium"] == 3000
    assert result["total_claims"] == 600
    assert result["loss_ratio_pct"] == 20.0
    assert result["assessment"] == "Healthy"


def test_unprofitable_carrier_loss_ratio():
    result = get_loss_ratio("carrier=StateFarm")
    assert result["loss_ratio_pct"] == 130.0
    assert result["assessment"] == "Unprofitable"


def test_unknown_carrier_returns_zero_not_error():
    result = get_loss_ratio("carrier=Nonexistent")
    assert result["total_premium"] == 0
    assert result["loss_ratio_pct"] == 0