"""
Run this once to populate the database with a large synthetic dataset.
Usage:  python seed_rich_data.py

Policies and claims are generated programmatically (not hand-written) because of the
volume involved. Generation is seeded for reproducibility — re-running this script
produces the same dataset every time.
"""

import random
from datetime import date, timedelta

from db.database import get_engine, init_db, AutoPolicy, Claim, get_session

random.seed(42)

N_PERSONS = 1500
N_POLICIES = 2000
N_CLAIMS = 300

CARRIERS = ["GEICO", "StateFarm", "Allstate", "Progressive", "Nationwide"]
STATES = ["CA", "TX", "FL", "NY", "WA", "IL", "GA", "OH"]

FIRST_NAMES = [
    "James", "Maria", "Kevin", "Susan", "David", "Rachel", "Daniel", "Sophia",
    "Carlos", "Ashley", "Marcus", "Linda", "Robert", "Emily", "Frank", "Grace",
    "Henry", "Irene", "Jason", "Karen", "Liam", "Mia", "Noah", "Olivia", "Peter",
    "Quinn", "Rosa", "Samuel", "Tina", "Victor", "Wendy", "Xavier", "Yolanda", "Zachary",
]
LAST_NAMES = [
    "Thornton", "Gonzalez", "Liu", "Park", "Chen", "Kim", "Wu", "Reyes", "Mendez",
    "Brown", "Johnson", "Torres", "Davis", "Nguyen", "Miller", "Lee", "Scott",
    "Adams", "Wright", "Hall", "Carter", "Robinson", "Wilson", "Bennett", "Patel",
    "Cooper", "Russell", "Hayes", "Price", "Simmons", "Foster", "Powell", "Barnes",
]

_STATUS_CHOICES = ["active", "inactive", "cancelled"]
_STATUS_WEIGHTS = [0.85, 0.08, 0.07]
_RENEWAL_CHOICES = ["renewed", "non-renewed"]
_RENEWAL_WEIGHTS = [0.75, 0.25]
_CLAIM_TYPE_CHOICES = ["Collision", "Liability", "Theft", "Weather", "Other"]
_CLAIM_TYPE_WEIGHTS = [0.40, 0.25, 0.15, 0.15, 0.05]
_CLAIM_TYPE_BASE_AMOUNT = {
    "Collision": 7000,
    "Liability": 6000,
    "Theft": 9000,
    "Weather": 4000,
    "Other": 3000,
}
_CLAIM_STATUS_CHOICES = ["Closed", "Open", "Denied"]
_CLAIM_STATUS_WEIGHTS = [0.55, 0.35, 0.10]


def _random_date(start: date, end: date) -> date:
    span = (end - start).days
    return start + timedelta(days=random.randint(0, max(span, 0)))


def generate_policies(n_persons: int = N_PERSONS, n_policies: int = N_POLICIES) -> list:
    """Generate policies for a pool of synthetic persons (some persons hold >1 policy)."""
    persons = [
        (f"P-{i:04d}", f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}")
        for i in range(1, n_persons + 1)
    ]

    policies = []
    for seq in range(1, n_policies + 1):
        person_id, holder_name = random.choice(persons)
        risk_score = random.randint(20, 99)
        start_date = _random_date(date(2019, 1, 1), date(2025, 6, 1))
        premium = round(500 + risk_score * 14 + random.uniform(-150, 150), 2)

        policies.append(
            AutoPolicy(
                policy_id=f"A-2{seq:05d}",
                person_id=person_id,
                holder_name=holder_name,
                state=random.choice(STATES),
                risk_score=risk_score,
                status=random.choices(_STATUS_CHOICES, weights=_STATUS_WEIGHTS)[0],
                start_date=start_date,
                premium=max(premium, 100.0),
                carrier_name=random.choice(CARRIERS),
                expiry_date=start_date + timedelta(days=365),
                renewal_status=random.choices(_RENEWAL_CHOICES, weights=_RENEWAL_WEIGHTS)[0],
            )
        )
    return policies


def generate_claims(policies: list, n_claims: int = N_CLAIMS) -> list:
    """Generate claims against randomly-sampled existing policies.

    Each claim's carrier_name is copied from its owning policy — Claim.carrier_name is a
    denormalized convenience column, never an independent source of truth.
    """
    claims = []
    for seq in range(1, n_claims + 1):
        policy = random.choice(policies)
        claim_type = random.choices(_CLAIM_TYPE_CHOICES, weights=_CLAIM_TYPE_WEIGHTS)[0]
        base_amount = _CLAIM_TYPE_BASE_AMOUNT[claim_type]
        amount = round(max(300.0, random.gauss(base_amount, base_amount * 0.4)), 2)

        claims.append(
            Claim(
                claim_id=f"C-9{seq:05d}",
                policy_id=policy.policy_id,
                person_id=policy.person_id,
                claim_date=_random_date(policy.start_date, policy.expiry_date),
                claim_type=claim_type,
                amount=amount,
                status=random.choices(_CLAIM_STATUS_CHOICES, weights=_CLAIM_STATUS_WEIGHTS)[0],
                carrier_name=policy.carrier_name,
            )
        )
    return claims


def run():
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    policies = generate_policies()
    claims = generate_claims(policies)

    for p in policies:
        existing = session.get(AutoPolicy, p.policy_id)
        if existing:
            session.delete(existing)
        session.add(p)

    for c in claims:
        existing = session.get(Claim, c.claim_id)
        if existing:
            session.delete(existing)
        session.add(c)

    session.commit()
    print(f"Done. Upserted {len(policies)} policies, {len(claims)} claims.")
    print(
        f"Total: {session.query(AutoPolicy).count()} policies, {session.query(Claim).count()} claims."
    )


if __name__ == "__main__":
    run()
