from datetime import datetime

from app.models import CallLog, CallSentiment, EquipmentType, Load, LoadStatus
from tests.conftest import AUTH_HEADERS

LOG_URL = "/calls/log"
LOG_CALL_URL = "/calls/log-call"
METRICS_URL = "/metrics"
CALLS_URL = "/calls"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_load(db, load_id: str = "LD-00001", rate: float = 2000.0) -> Load:
    load = Load(
        load_id=load_id,
        origin="Chicago, IL",
        destination="Atlanta, GA",
        pickup_datetime=datetime(2026, 4, 25, 8, 0),
        delivery_datetime=datetime(2026, 4, 26, 18, 0),
        equipment_type=EquipmentType.dry_van,
        loadboard_rate=rate,
        weight=38000,
        commodity_type="Electronics",
        num_of_pieces=22,
        miles=716,
        dimensions="48x40x60 in",
        status=LoadStatus.available,
    )
    db.add(load)
    db.commit()
    return load


def base_payload(**overrides) -> dict:
    payload = {
        "mc_number": "123456",
        "carrier_name": "ACME TRUCKING LLC",
        "load_id": "LD-00001",
        "initial_rate": 2000.0,
        "final_rate": 2100.0,
        "num_negotiation_rounds": 2,
        "outcome": "booked",
        "sentiment": "positive",
        "transcript_summary": "Carrier agreed after two rounds.",
        "raw_extraction": {"call_duration": 180},
    }
    payload.update(overrides)
    return payload


# ── POST /calls/log ───────────────────────────────────────────────────────────

def test_log_call_returns_201(client, db):
    make_load(db)
    res = client.post(LOG_URL, json=base_payload(), headers=AUTH_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["created"] is True


def test_log_call_booked_marks_load_as_booked(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(outcome="booked", final_rate=2100.0), headers=AUTH_HEADERS)

    load = db.get(Load, "LD-00001")
    db.refresh(load)
    assert load.status == LoadStatus.booked
    assert load.booked_rate == 2100.0
    assert load.booked_mc == "123456"


def test_log_call_no_agreement_does_not_touch_load(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(outcome="no_agreement", final_rate=None), headers=AUTH_HEADERS)

    load = db.get(Load, "LD-00001")
    db.refresh(load)
    assert load.status == LoadStatus.available
    assert load.booked_rate is None


def test_log_call_without_load_id_works(client):
    res = client.post(
        LOG_URL,
        json=base_payload(load_id=None, outcome="carrier_not_eligible"),
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 201


def test_log_call_idempotent_with_same_id(client, db):
    make_load(db)
    fixed_id = "aaaaaaaa-0000-0000-0000-000000000001"

    res1 = client.post(LOG_URL, json=base_payload(id=fixed_id), headers=AUTH_HEADERS)
    assert res1.json()["created"] is True

    res2 = client.post(LOG_URL, json=base_payload(id=fixed_id, sentiment="negative"), headers=AUTH_HEADERS)
    assert res2.json()["id"] == fixed_id
    assert res2.json()["created"] is False

    # Only one record in DB
    count = db.query(CallLog).filter(CallLog.id == fixed_id).count()
    assert count == 1
    record = db.get(CallLog, fixed_id)
    assert record.sentiment == CallSentiment.negative


def test_log_call_requires_auth(client):
    res = client.post(LOG_URL, json=base_payload())
    assert res.status_code == 401


# ── GET /metrics ──────────────────────────────────────────────────────────────

def test_metrics_empty_db(client):
    res = client.get(METRICS_URL, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["total_calls"] == 0
    assert data["bookings"] == 0
    assert data["conversion_rate"] == 0.0


def test_metrics_counts_correctly(client, db):
    make_load(db, "LD-00001")
    make_load(db, "LD-00002")

    client.post(LOG_URL, json=base_payload(outcome="booked", load_id="LD-00001"), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(outcome="booked", load_id="LD-00002"), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(outcome="no_agreement", load_id=None), headers=AUTH_HEADERS)

    res = client.get(METRICS_URL, headers=AUTH_HEADERS)
    data = res.json()
    assert data["total_calls"] == 3
    assert data["bookings"] == 2
    assert abs(data["conversion_rate"] - 0.6667) < 0.001
    assert data["outcome_breakdown"]["booked"] == 2
    assert data["outcome_breakdown"]["no_agreement"] == 1
    assert data["sentiment_breakdown"]["positive"] == 3


def test_metrics_avg_final_rate(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(outcome="booked", final_rate=2000.0), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(outcome="booked", final_rate=2200.0, load_id=None), headers=AUTH_HEADERS)

    res = client.get(METRICS_URL, headers=AUTH_HEADERS)
    assert res.json()["avg_final_rate"] == 2100.0


# ── GET /calls ────────────────────────────────────────────────────────────────

def test_list_calls_empty(client):
    res = client.get(CALLS_URL, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == []


def test_list_calls_returns_records(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(outcome="no_agreement", load_id=None), headers=AUTH_HEADERS)

    res = client.get(CALLS_URL, headers=AUTH_HEADERS)
    assert len(res.json()) == 2


def test_list_calls_filter_by_outcome(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(outcome="booked"), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(outcome="no_agreement", load_id=None), headers=AUTH_HEADERS)

    res = client.get(f"{CALLS_URL}?outcome=booked", headers=AUTH_HEADERS)
    data = res.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "booked"


def test_list_calls_filter_by_sentiment(client, db):
    make_load(db)
    client.post(LOG_URL, json=base_payload(sentiment="positive"), headers=AUTH_HEADERS)
    client.post(LOG_URL, json=base_payload(sentiment="negative", outcome="no_agreement", load_id=None), headers=AUTH_HEADERS)

    res = client.get(f"{CALLS_URL}?sentiment=negative", headers=AUTH_HEADERS)
    data = res.json()
    assert len(data) == 1
    assert data[0]["sentiment"] == "negative"


def test_list_calls_pagination(client, db):
    make_load(db)
    for _ in range(5):
        client.post(LOG_URL, json=base_payload(), headers=AUTH_HEADERS)

    res = client.get(f"{CALLS_URL}?limit=2&offset=0", headers=AUTH_HEADERS)
    assert len(res.json()) == 2

    res2 = client.get(f"{CALLS_URL}?limit=2&offset=2", headers=AUTH_HEADERS)
    assert len(res2.json()) == 2


# ── POST /calls/log-call (HappyRobot nested payload) ─────────────────────────

def hr_payload(**overrides) -> dict:
    """Build a minimal valid LogCallRequest payload."""
    p = {
        "call_id": "hr_test0001",
        "started_at": "2026-04-19T15:00:00",
        "ended_at": "2026-04-19T15:04:00",
        "carrier": {
            "mc_number": "MC-123456",
            "carrier_name": "SWIFT LOGISTICS LLC",
            "dot_number": "DOT-2001001",
            "eligible": True,
        },
        "load": {
            "load_id": "LD-00001",
            "origin": "Chicago, IL",
            "destination": "Atlanta, GA",
            "equipment_type": "Dry Van",
            "loadboard_rate": 1500.0,
            "miles": 716,
            "commodity_type": "Electronics",
            "pickup_datetime": "2026-04-25T08:00:00",
        },
        "negotiation": {
            "initial_carrier_offer": 1650.0,
            "final_rate": 1560.0,
            "num_rounds": 1,
            "rounds_detail": [
                {"round": 1, "carrier_offer": 1650.0, "our_counter": 1500.0, "decision": "accept"}
            ],
            "walk_away_reason": None,
        },
        "classification": {
            "outcome": "booked",
            "sentiment": "positive",
            "unresolved_topics": [],
            "tool_errors": [],
        },
        "summary": {
            "transcript_summary": "Booked after 1 round.",
            "raw_extraction": {},
        },
    }
    p.update(overrides)
    return p


def test_log_call_creates_new(client, db):
    make_load(db)
    res = client.post(LOG_CALL_URL, json=hr_payload(), headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["call_id"] == "hr_test0001"
    assert data["stored"] is True
    assert data["action"] == "created"
    assert db.query(CallLog).filter(CallLog.id == "hr_test0001").count() == 1


def test_log_call_idempotent(client, db):
    make_load(db)
    client.post(LOG_CALL_URL, json=hr_payload(), headers=AUTH_HEADERS)
    # Second call with same call_id but different sentiment
    payload2 = hr_payload()
    payload2["classification"]["sentiment"] = "neutral"
    res = client.post(LOG_CALL_URL, json=payload2, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["action"] == "updated"
    # Only one row in DB
    assert db.query(CallLog).filter(CallLog.id == "hr_test0001").count() == 1
    record = db.get(CallLog, "hr_test0001")
    db.refresh(record)
    assert record.sentiment.value == "neutral"


def test_log_call_booked_updates_load(client, db):
    make_load(db)
    res = client.post(LOG_CALL_URL, json=hr_payload(), headers=AUTH_HEADERS)
    assert res.json()["load_status_changed"] is True

    load = db.get(Load, "LD-00001")
    db.refresh(load)
    assert load.status == LoadStatus.booked
    assert load.booked_rate == 1560.0
    assert load.booked_mc == "123456"  # normalized from "MC-123456"


def test_log_call_booked_on_already_booked_load_warns(client, db):
    make_load(db)
    # First booking
    client.post(LOG_CALL_URL, json=hr_payload(), headers=AUTH_HEADERS)
    # Second booking attempt on same load with different call_id
    payload2 = hr_payload()
    payload2["call_id"] = "hr_test0002"
    res = client.post(LOG_CALL_URL, json=payload2, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["load_status_changed"] is False
    assert data["warning"] is not None
    assert "already booked" in data["warning"]


def test_log_call_invalid_booked_without_final_rate(client, db):
    make_load(db)
    payload = hr_payload()
    payload["negotiation"]["final_rate"] = None
    res = client.post(LOG_CALL_URL, json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 400
    assert "final_rate" in res.json()["detail"]


def test_log_call_num_rounds_mismatch(client, db):
    payload = hr_payload()
    payload["classification"]["outcome"] = "no_agreement"
    payload["negotiation"]["final_rate"] = None
    payload["negotiation"]["num_rounds"] = 3          # says 3 rounds
    payload["negotiation"]["rounds_detail"] = [       # but only 1 entry
        {"round": 1, "carrier_offer": 1650.0, "our_counter": 1500.0, "decision": "counter"}
    ]
    payload["load"]["load_id"] = "LD-00001"
    res = client.post(LOG_CALL_URL, json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 400
    assert "num_rounds" in res.json()["detail"]


def test_log_call_requires_api_key(client):
    res = client.post(LOG_CALL_URL, json=hr_payload())
    assert res.status_code == 401
