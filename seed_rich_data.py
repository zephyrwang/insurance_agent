"""
Run this once to populate the database with rich synthetic data.
Usage:  python seed_rich_data.py
"""

from datetime import date
from db.database import get_engine, init_db, AutoPolicy, Claim, get_session

POLICIES = [
    # --- California ---
    AutoPolicy(policy_id="A-10234", person_id="P-001", holder_name="James Thornton",
               state="CA", risk_score=92, status="active",    start_date=date(2021,3,15),
               premium=1850.0, carrier_name="GEICO",       expiry_date=date(2025,3,15),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10239", person_id="P-001", holder_name="James Thornton",
               state="CA", risk_score=92, status="active",    start_date=date(2023,3,15),
               premium=1950.0, carrier_name="StateFarm",    expiry_date=date(2026,3,15),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10235", person_id="P-002", holder_name="Maria Gonzalez",
               state="CA", risk_score=88, status="active",    start_date=date(2020,7,1),
               premium=1600.0, carrier_name="GEICO",        expiry_date=date(2025,7,1),   renewal_status="renewed"),
    AutoPolicy(policy_id="A-10240", person_id="P-006", holder_name="Rachel Kim",
               state="CA", risk_score=61, status="active",    start_date=date(2022,9,10),
               premium=1120.0, carrier_name="GEICO",        expiry_date=date(2025,9,10),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10241", person_id="P-007", holder_name="Daniel Wu",
               state="CA", risk_score=77, status="active",    start_date=date(2021,11,1),
               premium=1480.0, carrier_name="StateFarm",    expiry_date=date(2026,2,1),   renewal_status="non-renewed"),
    AutoPolicy(policy_id="A-10242", person_id="P-008", holder_name="Sophia Reyes",
               state="CA", risk_score=95, status="active",    start_date=date(2020,4,20),
               premium=2200.0, carrier_name="Nationwide",   expiry_date=date(2025,4,20),  renewal_status="renewed"),

    # --- Texas ---
    AutoPolicy(policy_id="A-10236", person_id="P-003", holder_name="Kevin Liu",
               state="TX", risk_score=55, status="active",    start_date=date(2022,1,10),
               premium=980.0,  carrier_name="Progressive",  expiry_date=date(2026,1,10),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10243", person_id="P-009", holder_name="Carlos Mendez",
               state="TX", risk_score=44, status="active",    start_date=date(2023,6,1),
               premium=820.0,  carrier_name="StateFarm",    expiry_date=date(2026,6,1),   renewal_status="renewed"),
    AutoPolicy(policy_id="A-10244", person_id="P-010", holder_name="Ashley Brown",
               state="TX", risk_score=70, status="active",    start_date=date(2021,8,15),
               premium=1150.0, carrier_name="StateFarm",    expiry_date=date(2026,1,15),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10245", person_id="P-011", holder_name="Marcus Johnson",
               state="TX", risk_score=33, status="inactive",  start_date=date(2022,3,1),
               premium=700.0,  carrier_name="Progressive",  expiry_date=date(2025,3,1),   renewal_status="non-renewed"),

    # --- Florida ---
    AutoPolicy(policy_id="A-10237", person_id="P-004", holder_name="Susan Park",
               state="FL", risk_score=81, status="active",    start_date=date(2019,11,20),
               premium=2100.0, carrier_name="Allstate",     expiry_date=date(2025,11,20), renewal_status="renewed"),
    AutoPolicy(policy_id="A-10246", person_id="P-012", holder_name="Linda Torres",
               state="FL", risk_score=68, status="active",    start_date=date(2023,2,14),
               premium=1300.0, carrier_name="Allstate",     expiry_date=date(2026,2,14),  renewal_status="non-renewed"),
    AutoPolicy(policy_id="A-10247", person_id="P-013", holder_name="Robert Davis",
               state="FL", risk_score=85, status="cancelled", start_date=date(2020,6,30),
               premium=1750.0, carrier_name="Nationwide",   expiry_date=date(2025,6,30),  renewal_status="non-renewed"),

    # --- New York ---
    AutoPolicy(policy_id="A-10238", person_id="P-005", holder_name="David Chen",
               state="NY", risk_score=42, status="inactive",  start_date=date(2023,5,5),
               premium=750.0,  carrier_name="Nationwide",   expiry_date=date(2025,5,5),   renewal_status="non-renewed"),
    AutoPolicy(policy_id="A-10248", person_id="P-014", holder_name="Emily Nguyen",
               state="NY", risk_score=58, status="active",    start_date=date(2022,10,1),
               premium=1050.0, carrier_name="GEICO",        expiry_date=date(2026,4,1),   renewal_status="renewed"),
    AutoPolicy(policy_id="A-10249", person_id="P-015", holder_name="Frank Miller",
               state="NY", risk_score=79, status="active",    start_date=date(2021,7,4),
               premium=1550.0, carrier_name="Allstate",     expiry_date=date(2026,1,4),   renewal_status="renewed"),

    # --- Washington ---
    AutoPolicy(policy_id="A-10250", person_id="P-016", holder_name="Grace Lee",
               state="WA", risk_score=37, status="active",    start_date=date(2023,1,20),
               premium=680.0,  carrier_name="Progressive",  expiry_date=date(2026,1,20),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10251", person_id="P-017", holder_name="Henry Scott",
               state="WA", risk_score=63, status="active",    start_date=date(2022,5,15),
               premium=1010.0, carrier_name="Nationwide",   expiry_date=date(2026,5,15),  renewal_status="renewed"),

    # --- Illinois ---
    AutoPolicy(policy_id="A-10252", person_id="P-018", holder_name="Irene Adams",
               state="IL", risk_score=50, status="active",    start_date=date(2021,9,1),
               premium=890.0,  carrier_name="StateFarm",    expiry_date=date(2026,3,1),   renewal_status="non-renewed"),
    AutoPolicy(policy_id="A-10253", person_id="P-019", holder_name="Jason Wright",
               state="IL", risk_score=74, status="active",    start_date=date(2020,12,1),
               premium=1280.0, carrier_name="Nationwide",   expiry_date=date(2026,12,1),  renewal_status="renewed"),

    # --- Georgia ---
    AutoPolicy(policy_id="A-10254", person_id="P-020", holder_name="Karen Hall",
               state="GA", risk_score=48, status="active",    start_date=date(2023,4,10),
               premium=840.0,  carrier_name="GEICO",        expiry_date=date(2026,4,10),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10255", person_id="P-008", holder_name="Sophia Reyes",
               state="GA", risk_score=90, status="active",    start_date=date(2024,1,5),
               premium=2050.0, carrier_name="Progressive",  expiry_date=date(2026,1,5),   renewal_status="non-renewed"),

    # --- Ohio ---
    AutoPolicy(policy_id="A-10256", person_id="P-021", holder_name="Liam Carter",
               state="OH", risk_score=29, status="active",    start_date=date(2022,7,22),
               premium=610.0,  carrier_name="Nationwide",   expiry_date=date(2026,7,22),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10257", person_id="P-022", holder_name="Mia Robinson",
               state="OH", risk_score=56, status="active",    start_date=date(2021,2,18),
               premium=940.0,  carrier_name="StateFarm",    expiry_date=date(2026,2,18),  renewal_status="renewed"),
    AutoPolicy(policy_id="A-10258", person_id="P-023", holder_name="Noah Wilson",
               state="OH", risk_score=83, status="cancelled", start_date=date(2019,8,8),
               premium=1680.0, carrier_name="Allstate",     expiry_date=date(2025,8,8),   renewal_status="non-renewed"),
]

CLAIMS = [
    # --- P-001 (James Thornton) — HIGH fraud risk ---
    Claim(claim_id="C-4421", policy_id="A-10234", person_id="P-001",
          claim_date=date(2023,4,12),  claim_type="Collision", amount=8200,  status="Closed"),
    Claim(claim_id="C-5103", policy_id="A-10234", person_id="P-001",
          claim_date=date(2024,1,8),   claim_type="Liability", amount=3400,  status="Closed"),
    Claim(claim_id="C-5891", policy_id="A-10239", person_id="P-001",
          claim_date=date(2025,9,15),  claim_type="Collision", amount=12700, status="Open"),
    Claim(claim_id="C-6310", policy_id="A-10239", person_id="P-001",
          claim_date=date(2026,2,3),   claim_type="Theft",     amount=18500, status="Open"),

    # --- P-002 (Maria Gonzalez) ---
    Claim(claim_id="C-6012", policy_id="A-10235", person_id="P-002",
          claim_date=date(2025,2,20),  claim_type="Theft",     amount=5500,  status="Closed"),
    Claim(claim_id="C-6100", policy_id="A-10235", person_id="P-002",
          claim_date=date(2025,8,3),   claim_type="Weather",   amount=2200,  status="Closed"),

    # --- P-004 (Susan Park) ---
    Claim(claim_id="C-6200", policy_id="A-10237", person_id="P-004",
          claim_date=date(2025,11,10), claim_type="Collision", amount=9800,  status="Open"),
    Claim(claim_id="C-6211", policy_id="A-10237", person_id="P-004",
          claim_date=date(2026,3,1),   claim_type="Liability", amount=4100,  status="Open"),

    # --- P-007 (Daniel Wu) ---
    Claim(claim_id="C-6305", policy_id="A-10241", person_id="P-007",
          claim_date=date(2025,5,22),  claim_type="Collision", amount=6700,  status="Closed"),

    # --- P-008 (Sophia Reyes) — HIGH fraud risk, 5 claims ---
    Claim(claim_id="C-5500", policy_id="A-10242", person_id="P-008",
          claim_date=date(2024,3,14),  claim_type="Theft",     amount=14000, status="Closed"),
    Claim(claim_id="C-5610", policy_id="A-10242", person_id="P-008",
          claim_date=date(2024,7,29),  claim_type="Collision", amount=9500,  status="Closed"),
    Claim(claim_id="C-5780", policy_id="A-10242", person_id="P-008",
          claim_date=date(2025,1,17),  claim_type="Liability", amount=21000, status="Open"),
    Claim(claim_id="C-6400", policy_id="A-10255", person_id="P-008",
          claim_date=date(2025,10,5),  claim_type="Theft",     amount=17500, status="Open"),
    Claim(claim_id="C-6450", policy_id="A-10255", person_id="P-008",
          claim_date=date(2026,1,22),  claim_type="Collision", amount=11200, status="Open"),

    # --- P-009 (Carlos Mendez) ---
    Claim(claim_id="C-6501", policy_id="A-10243", person_id="P-009",
          claim_date=date(2025,6,18),  claim_type="Weather",   amount=3100,  status="Closed"),

    # --- P-010 (Ashley Brown) ---
    Claim(claim_id="C-6550", policy_id="A-10244", person_id="P-010",
          claim_date=date(2025,3,7),   claim_type="Collision", amount=7800,  status="Closed"),
    Claim(claim_id="C-6560", policy_id="A-10244", person_id="P-010",
          claim_date=date(2026,1,15),  claim_type="Liability", amount=5200,  status="Open"),

    # --- P-012 (Linda Torres) ---
    Claim(claim_id="C-6600", policy_id="A-10246", person_id="P-012",
          claim_date=date(2025,7,30),  claim_type="Weather",   amount=4400,  status="Closed"),

    # --- P-014 (Emily Nguyen) ---
    Claim(claim_id="C-6650", policy_id="A-10248", person_id="P-014",
          claim_date=date(2025,12,5),  claim_type="Collision", amount=6100,  status="Open"),

    # --- P-015 (Frank Miller) ---
    Claim(claim_id="C-6700", policy_id="A-10249", person_id="P-015",
          claim_date=date(2025,4,14),  claim_type="Theft",     amount=8900,  status="Closed"),

    # --- P-016 (Grace Lee) ---
    Claim(claim_id="C-6750", policy_id="A-10250", person_id="P-016",
          claim_date=date(2025,9,1),   claim_type="Weather",   amount=1800,  status="Closed"),

    # --- P-017 (Henry Scott) ---
    Claim(claim_id="C-6800", policy_id="A-10251", person_id="P-017",
          claim_date=date(2025,11,20), claim_type="Collision", amount=5500,  status="Open"),

    # --- P-019 (Jason Wright) ---
    Claim(claim_id="C-6850", policy_id="A-10253", person_id="P-019",
          claim_date=date(2026,2,28),  claim_type="Liability", amount=9300,  status="Open"),

    # --- P-022 (Mia Robinson) ---
    Claim(claim_id="C-6900", policy_id="A-10257", person_id="P-022",
          claim_date=date(2025,8,12),  claim_type="Other",     amount=2700,  status="Closed"),

    # --- Monthly spread for trend analysis ---
    Claim(claim_id="C-7001", policy_id="A-10240", person_id="P-006",
          claim_date=date(2025,6,3),   claim_type="Collision", amount=4300,  status="Closed"),
    Claim(claim_id="C-7002", policy_id="A-10252", person_id="P-018",
          claim_date=date(2025,7,11),  claim_type="Weather",   amount=3600,  status="Closed"),
    Claim(claim_id="C-7003", policy_id="A-10256", person_id="P-021",
          claim_date=date(2025,8,25),  claim_type="Collision", amount=2900,  status="Closed"),
    Claim(claim_id="C-7004", policy_id="A-10254", person_id="P-020",
          claim_date=date(2025,9,14),  claim_type="Liability", amount=5100,  status="Closed"),
    Claim(claim_id="C-7005", policy_id="A-10243", person_id="P-009",
          claim_date=date(2025,10,2),  claim_type="Weather",   amount=1950,  status="Closed"),
    Claim(claim_id="C-7006", policy_id="A-10248", person_id="P-014",
          claim_date=date(2025,10,19), claim_type="Collision", amount=7200,  status="Closed"),
    Claim(claim_id="C-7007", policy_id="A-10250", person_id="P-016",
          claim_date=date(2025,11,8),  claim_type="Other",     amount=1400,  status="Closed"),
    Claim(claim_id="C-7008", policy_id="A-10244", person_id="P-010",
          claim_date=date(2025,12,20), claim_type="Theft",     amount=6600,  status="Closed"),
    Claim(claim_id="C-7009", policy_id="A-10246", person_id="P-012",
          claim_date=date(2026,1,6),   claim_type="Collision", amount=5800,  status="Open"),
    Claim(claim_id="C-7010", policy_id="A-10253", person_id="P-019",
          claim_date=date(2026,2,14),  claim_type="Liability", amount=8100,  status="Open"),
    Claim(claim_id="C-7011", policy_id="A-10240", person_id="P-006",
          claim_date=date(2026,3,5),   claim_type="Collision", amount=4900,  status="Open"),
    Claim(claim_id="C-7012", policy_id="A-10249", person_id="P-015",
          claim_date=date(2026,4,1),   claim_type="Weather",   amount=3300,  status="Open"),
    Claim(claim_id="C-7013", policy_id="A-10241", person_id="P-007",
          claim_date=date(2026,5,10),  claim_type="Collision", amount=7700,  status="Open"),
]


def run():
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    added_p = added_c = 0
    for p in POLICIES:
        existing = session.get(AutoPolicy, p.policy_id)
        if existing:
            session.delete(existing)
        session.add(p)
        added_p += 1

    for c in CLAIMS:
        existing = session.get(Claim, c.claim_id)
        if existing:
            session.delete(existing)
        session.add(c)
        added_c += 1

    session.commit()
    print(f"Done. Upserted {added_p} policies, {added_c} claims.")
    print(f"Total: {session.query(AutoPolicy).count()} policies, {session.query(Claim).count()} claims.")


if __name__ == "__main__":
    run()
