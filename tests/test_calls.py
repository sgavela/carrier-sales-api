from datetime import datetime

from app.models import CallLog, CallOutcome, CallSentiment, EquipmentType, Load, LoadStatus
from tests.conftest import AUTH_HEADERS

LOG_URL = "/calls/log"
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
