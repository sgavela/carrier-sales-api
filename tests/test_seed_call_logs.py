"""Tests for scripts/seed_call_logs.py."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import Base
from app.models import CallLog, CallOutcome, Load, LoadStatus
from scripts.seed_call_logs import (
    NEAR_MISS_COUNT,
    OUTCOME_TARGETS_FULL,
    TOTAL_COUNT,
    seed_call_logs,
)

# ── In-memory DB fixture ──────────────────────────────────────────────────────

LOADS_SAMPLE = [
    {
        "load_id": "LD-00001",
        "origin": "Chicago, IL",
        "destination": "Atlanta, GA",
        "pickup_datetime": datetime(2026, 4, 19, 8, 0),
        "delivery_datetime": datetime(2026, 4, 20, 18, 0),
        "equipment_type": "Dry Van",
        "loadboard_rate": 1500.0,
        "weight": 38000,
        "commodity_type": "Electronics",
        "num_of_pieces": 22,
        "miles": 716,
        "dimensions": "48x40x60 in",
        "status": "available",
    },
    {
        "load_id": "LD-00002",
        "origin": "Los Angeles, CA",
        "destination": "Dallas, TX",
        "pickup_datetime": datetime(2026, 4, 20, 6, 0),
        "delivery_datetime": datetime(2026, 4, 21, 22, 0),
        "equipment_type": "Reefer",
        "loadboard_rate": 4200.0,
        "weight": 34000,
        "commodity_type": "Produce",
        "num_of_pieces": 18,
        "miles": 1435,
        "dimensions": "48x40x50 in",
        "status": "available",
    },
    {
        "load_id": "LD-00005",
        "origin": "Houston, TX",
        "destination": "Chicago, IL",
        "pickup_datetime": datetime(2026, 4, 22, 9, 0),
        "delivery_datetime": datetime(2026, 4, 24, 8, 0),
        "equipment_type": "Dry Van",
        "loadboard_rate": 2100.0,
        "weight": 40000,
        "commodity_type": "Auto Parts",
        "num_of_pieces": 16,
        "miles": 1092,
        "dimensions": "48x40x72 in",
        "status": "available",
    },
    {
        "load_id": "LD-00010",
        "origin": "Chicago, IL",
        "destination": "Dallas, TX",
        "pickup_datetime": datetime(2026, 4, 25, 8, 0),
        "delivery_datetime": datetime(2026, 4, 26, 22, 0),
        "equipment_type": "Reefer",
        "loadboard_rate": 2700.0,
        "weight": 28000,
        "commodity_type": "Frozen Foods",
        "num_of_pieces": 20,
        "miles": 921,
        "dimensions": "48x40x60 in",
        "status": "available",
    },
]


@pytest.fixture(scope="module")
def db_session():
    """Fresh in-memory SQLite with loads pre-seeded."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    for row in LOADS_SAMPLE:
        load = Load(
            load_id=row["load_id"],
            origin=row["origin"],
            destination=row["destination"],
            pickup_datetime=row["pickup_datetime"],
            delivery_datetime=row["delivery_datetime"],
            equipment_type=row["equipment_type"],
            loadboard_rate=row["loadboard_rate"],
            weight=row["weight"],
            commodity_type=row["commodity_type"],
            num_of_pieces=row["num_of_pieces"],
            miles=row["miles"],
            dimensions=row["dimensions"],
            status=LoadStatus.available,
        )
        session.add(load)
    session.commit()

    # Monkey-patch engine/SessionLocal used by seed_call_logs
    import app.db as app_db
    original_engine = app_db.engine
    original_session = app_db.SessionLocal

    app_db.engine = engine
    app_db.SessionLocal = Session

    yield session

    # Restore
    app_db.engine = original_engine
    app_db.SessionLocal = original_session
    session.close()


@pytest.fixture(autouse=True)
def clean_call_logs(db_session):
    """Wipe call_logs before every test."""
    db_session.query(CallLog).delete()
    db_session.commit()
    yield


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_idempotent_no_duplicate(db_session):
    """Running seed twice without --force must not add rows."""
    seed_call_logs(count=TOTAL_COUNT, force=False)
    count_after_first = db_session.query(CallLog).count()

    seed_call_logs(count=TOTAL_COUNT, force=False)
    count_after_second = db_session.query(CallLog).count()

    assert count_after_first == count_after_second
    assert count_after_first == TOTAL_COUNT


def test_outcome_distribution_within_tolerance(db_session):
    """Each outcome's share must be within ±5% of its target."""
    seed_call_logs(count=TOTAL_COUNT, force=True)
    calls = db_session.query(CallLog).all()
    total = len(calls)
    counts = Counter(c.outcome.value for c in calls)

    for outcome, target_n in OUTCOME_TARGETS_FULL.items():
        target_pct = target_n / TOTAL_COUNT
        actual_pct = counts[outcome] / total
        assert abs(actual_pct - target_pct) <= 0.05, (
            f"{outcome}: expected {target_pct:.0%}, got {actual_pct:.0%}"
        )


def test_near_miss_deals_detectable(db_session):
    """Exactly NEAR_MISS_COUNT no_agreement calls must have last carrier_offer <3% above our_counter."""
    seed_call_logs(count=TOTAL_COUNT, force=True)
    calls = db_session.query(CallLog).filter(
        CallLog.outcome == CallOutcome.no_agreement
    ).all()

    near_miss = [
        c for c in calls
        if c.rounds_detail
        and (c.rounds_detail[-1]["carrier_offer"] - c.rounds_detail[-1]["our_counter"])
        / c.rounds_detail[-1]["our_counter"]
        < 0.03
    ]
    assert len(near_miss) == NEAR_MISS_COUNT, (
        f"Expected {NEAR_MISS_COUNT} near-miss deals, found {len(near_miss)}"
    )


def test_booked_final_rate_bounds(db_session):
    """All booked final_rates must be between loadboard_rate * 0.95 and loadboard_rate * 1.15."""
    seed_call_logs(count=TOTAL_COUNT, force=True)
    booked = db_session.query(CallLog).filter(
        CallLog.outcome == CallOutcome.booked
    ).all()

    assert len(booked) > 0, "No booked calls found"

    for call in booked:
        assert call.final_rate is not None, f"booked call {call.id} has null final_rate"
        assert call.loadboard_rate is not None, f"booked call {call.id} has null loadboard_rate"
        lo = call.loadboard_rate * 0.95
        hi = call.loadboard_rate * 1.15
        assert lo <= call.final_rate <= hi, (
            f"Call {call.id}: final_rate={call.final_rate} out of [{lo:.2f}, {hi:.2f}] "
            f"for loadboard={call.loadboard_rate}"
        )
