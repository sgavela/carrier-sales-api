"""Tests for GET /dashboard and the underlying pure compute functions."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pytest

from app.services.dashboard import (
    compute_carriers,
    compute_overview,
    compute_pricing,
    compute_quality,
)
from tests.conftest import AUTH_HEADERS

DASHBOARD_URL = "/dashboard"


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _call(
    *,
    id: str = "c1",
    outcome: str = "booked",
    sentiment: str = "positive",
    received_at: Optional[datetime] = None,
    duration_seconds: int = 180,
    final_rate: Optional[float] = None,
    loadboard_rate: Optional[float] = None,
    initial_carrier_offer: Optional[float] = None,
    equipment_type: Optional[str] = None,
    mc_number: str = "MC-001",
    carrier_name: Optional[str] = "ACME LLC",
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    rounds_detail: Optional[list] = None,
    walk_away_reason: Optional[str] = None,
    num_rounds: int = 0,
    carrier_eligible: Optional[bool] = True,
    unresolved_topics: Optional[list] = None,
    num_user_turns: int = 4,
    num_assistant_turns: int = 5,
) -> dict:
    now = datetime(2026, 4, 19, 15, 0, 0)
    return {
        "id": id,
        "outcome": outcome,
        "sentiment": sentiment,
        "received_at": received_at or now,
        "duration_seconds": duration_seconds,
        "final_rate": final_rate,
        "loadboard_rate": loadboard_rate,
        "initial_carrier_offer": initial_carrier_offer,
        "equipment_type": equipment_type,
        "mc_number": mc_number,
        "carrier_name": carrier_name,
        "origin": origin,
        "destination": destination,
        "rounds_detail": rounds_detail or [],
        "walk_away_reason": walk_away_reason,
        "num_rounds": num_rounds,
        "carrier_eligible": carrier_eligible,
        "unresolved_topics": unresolved_topics or [],
        "num_user_turns": num_user_turns,
        "num_assistant_turns": num_assistant_turns,
        "created_at": received_at or now,
        "dot_number": None,
        "ineligible_reason": None,
        "miles": None,
        "commodity_type": None,
        "pickup_datetime": None,
        "transcript_summary": None,
        "raw_extraction": None,
    }


DATE_FROM = date(2026, 3, 20)
DATE_TO = date(2026, 4, 19)


# ── test_dashboard_empty ──────────────────────────────────────────────────────

def test_dashboard_empty(client):
    """With no calls in DB, dashboard returns all-zeros structure, not an error."""
    res = client.get(DASHBOARD_URL, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["overview"]["total_calls"] == 0
    assert data["overview"]["booking_rate"] == 0.0
    assert data["overview"]["revenue_captured"] == 0.0
    assert data["carriers"]["carriers"] == []
    assert data["carriers"]["dormant_carriers"] == []
    assert data["pricing"]["lost_near_miss"] == []
    assert data["quality"]["near_miss_count"] == 0
    assert data["recent_calls"] == []


# ── test_dashboard_booking_rate ───────────────────────────────────────────────

def test_dashboard_booking_rate():
    """10 calls, 3 booked → booking_rate = 0.3."""
    calls = (
        [_call(id=f"b{i}", outcome="booked", final_rate=1500.0, loadboard_rate=1500.0) for i in range(3)]
        + [_call(id=f"n{i}", outcome="no_agreement") for i in range(7)]
    )
    result = compute_overview(calls, DATE_FROM, DATE_TO)
    assert result["total_calls"] == 10
    assert result["booking_rate"] == 0.3


# ── test_dashboard_margin_only_booked ────────────────────────────────────────

def test_dashboard_margin_only_booked():
    """avg_margin_pct must only consider booked calls."""
    calls = [
        # booked at 10% above loadboard
        _call(id="b1", outcome="booked", final_rate=1100.0, loadboard_rate=1000.0),
        # no_agreement — should NOT affect margin
        _call(id="n1", outcome="no_agreement", final_rate=None, loadboard_rate=1000.0),
    ]
    result = compute_overview(calls, DATE_FROM, DATE_TO)
    # Only booked call counts: (1100-1000)/1000 = 0.1
    assert result["avg_margin_pct"] == pytest.approx(0.1, abs=0.001)


# ── test_dashboard_duration_from_field ───────────────────────────────────────

def test_dashboard_duration_from_field():
    """avg_call_duration_seconds reads duration_seconds directly."""
    calls = [
        _call(id="c1", duration_seconds=200),
        _call(id="c2", duration_seconds=400),
    ]
    result = compute_overview(calls, DATE_FROM, DATE_TO)
    assert result["avg_call_duration_seconds"] == pytest.approx(300.0, abs=0.1)


# ── test_dashboard_near_miss_detection ───────────────────────────────────────

def test_dashboard_near_miss_detection():
    """Gap < 3% → near-miss. Gap ≥ 3% → not a near-miss."""
    near_miss_call = _call(
        id="nm1",
        outcome="no_agreement",
        rounds_detail=[
            {"round": 1, "carrier_offer": 1520.0, "our_counter": 1500.0, "decision": "counter"},
            {"round": 2, "carrier_offer": 1510.0, "our_counter": 1500.0, "decision": "counter"},
            {"round": 3, "carrier_offer": 1515.0, "our_counter": 1500.0, "decision": "reject"},
            # last carrier_offer = 1515, our_counter = 1500 → gap = 1% < 3% ✓
        ],
        loadboard_rate=1500.0,
    )
    far_call = _call(
        id="nm2",
        outcome="no_agreement",
        rounds_detail=[
            {"round": 3, "carrier_offer": 1560.0, "our_counter": 1500.0, "decision": "reject"},
            # gap = 4% → NOT near-miss
        ],
        loadboard_rate=1500.0,
    )

    pricing = compute_pricing([near_miss_call, far_call])
    near_misses = pricing["lost_near_miss"]

    ids = [nm["call_id"] for nm in near_misses]
    assert "nm1" in ids
    assert "nm2" not in ids
    # Revenue estimate = our_counter * 1.03
    nm = next(nm for nm in near_misses if nm["call_id"] == "nm1")
    assert nm["revenue_lost_estimate"] == pytest.approx(1500.0 * 1.03, abs=0.01)


# ── test_dashboard_dormant_carriers ──────────────────────────────────────────

def test_dashboard_dormant_carriers():
    """Carrier with last call 30 days ago and ≥2 bookings must appear in dormant_carriers."""
    test_now = datetime(2026, 4, 19, 12, 0, 0)
    old_date = test_now - timedelta(days=30)  # > 25-day threshold

    calls = [
        _call(id="d1", mc_number="MC-DORMANT", outcome="booked",
              received_at=old_date, duration_seconds=200,
              final_rate=1500.0, loadboard_rate=1500.0),
        _call(id="d2", mc_number="MC-DORMANT", outcome="booked",
              received_at=old_date + timedelta(hours=1), duration_seconds=200,
              final_rate=1500.0, loadboard_rate=1500.0),
        # Active carrier (recent call) — must NOT appear in dormant
        _call(id="a1", mc_number="MC-ACTIVE", outcome="booked",
              received_at=test_now - timedelta(days=2), duration_seconds=200,
              final_rate=1500.0, loadboard_rate=1500.0),
    ]

    result = compute_carriers(calls, now=test_now)
    dormant_mcs = [d["mc_number"] for d in result["dormant_carriers"]]
    assert "MC-DORMANT" in dormant_mcs
    assert "MC-ACTIVE" not in dormant_mcs

    dormant = next(d for d in result["dormant_carriers"] if d["mc_number"] == "MC-DORMANT")
    assert dormant["historical_bookings"] == 2
    assert dormant["days_dormant"] >= 25


# ── test_dashboard_equipment_filter ──────────────────────────────────────────

def test_dashboard_equipment_filter(client, db):
    """Filtering by equipment_type=Reefer returns metrics for Reefer calls only."""
    from app.models import CallLog, CallOutcome, CallSentiment, EquipmentType, Load, LoadStatus

    now = datetime(2026, 4, 19, 15, 0)

    # Reefer load + call
    load_r = Load(
        load_id="LD-REEF",
        origin="Chicago, IL",
        destination="Dallas, TX",
        pickup_datetime=now,
        delivery_datetime=now + timedelta(days=1),
        equipment_type=EquipmentType.reefer,
        loadboard_rate=3000.0,
        weight=28000,
        commodity_type="Produce",
        num_of_pieces=20,
        miles=921,
        dimensions="48x40x60 in",
        status=LoadStatus.available,
    )
    # Dry Van load + call
    load_d = Load(
        load_id="LD-DRY",
        origin="Houston, TX",
        destination="Atlanta, GA",
        pickup_datetime=now,
        delivery_datetime=now + timedelta(days=1),
        equipment_type=EquipmentType.dry_van,
        loadboard_rate=1500.0,
        weight=38000,
        commodity_type="Electronics",
        num_of_pieces=22,
        miles=716,
        dimensions="48x40x60 in",
        status=LoadStatus.available,
    )
    db.add_all([load_r, load_d])

    call_reefer = CallLog(
        id="call-reef",
        mc_number="MC-001",
        carrier_name="REEFER CO",
        outcome=CallOutcome.booked,
        sentiment=CallSentiment.positive,
        received_at=now,
        duration_seconds=200,
        created_at=now,
        load_id="LD-REEF",
        equipment_type="Reefer",
        loadboard_rate=3000.0,
        final_rate=3120.0,
        num_negotiation_rounds=0,
    )
    call_dry = CallLog(
        id="call-dry",
        mc_number="MC-002",
        carrier_name="DRY CO",
        outcome=CallOutcome.no_agreement,
        sentiment=CallSentiment.negative,
        received_at=now - timedelta(hours=1),
        duration_seconds=400,
        created_at=now - timedelta(hours=1),
        load_id="LD-DRY",
        equipment_type="Dry Van",
        loadboard_rate=1500.0,
        num_negotiation_rounds=0,
    )
    db.add_all([call_reefer, call_dry])
    db.commit()

    res = client.get(f"{DASHBOARD_URL}?equipment_type=Reefer", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    # Only the Reefer call should appear
    assert data["overview"]["total_calls"] == 1
    assert data["overview"]["booking_rate"] == 1.0
    assert data["equipment_filter"] == "Reefer"
    # The Dry Van no_agreement call must not be counted
    assert data["overview"]["outcome_breakdown"].get("no_agreement", 0) == 0


# ── test_dashboard_turn_kpis ──────────────────────────────────────────────────

def test_dashboard_turn_kpis():
    """avg_turn_ratio and avg_total_turns should be computed correctly."""
    calls = [
        _call(id="t1", num_user_turns=4, num_assistant_turns=6),   # ratio = 1.5
        _call(id="t2", num_user_turns=2, num_assistant_turns=2),   # ratio = 1.0
    ]
    result = compute_quality(calls)
    # avg ratio = (1.5 + 1.0) / 2 = 1.25
    assert result["avg_turn_ratio"] == pytest.approx(1.25, abs=0.01)
    # avg total turns = (10 + 4) / 2 = 7
    assert result["avg_total_turns"] == pytest.approx(7.0, abs=0.1)


def test_dashboard_turn_ratio_skips_zero_user_turns():
    """Calls with num_user_turns=0 must not contribute to avg_turn_ratio."""
    calls = [
        _call(id="t1", num_user_turns=0, num_assistant_turns=3),  # excluded
        _call(id="t2", num_user_turns=4, num_assistant_turns=4),  # ratio = 1.0
    ]
    result = compute_quality(calls)
    assert result["avg_turn_ratio"] == pytest.approx(1.0, abs=0.01)
    # avg_total_turns still counts all calls: (0+3 + 4+4) / 2 = 5.5
    assert result["avg_total_turns"] == pytest.approx(5.5, abs=0.1)
