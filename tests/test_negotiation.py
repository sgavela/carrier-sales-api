"""
Negotiation tests split into two layers:
  1. Unit tests on the pure evaluate() function — no HTTP, no DB
  2. Integration tests on POST /negotiation/evaluate-offer — uses test DB
"""
from datetime import datetime

import pytest

from app.models import EquipmentType, Load, LoadStatus
from app.services.negotiator import NegotiationDecision, evaluate
from tests.conftest import AUTH_HEADERS

RATE = 2000.0   # loadboard rate used in all scenarios

# ── Pure unit tests (no HTTP) ─────────────────────────────────────────────────

class TestRound1:
    def test_accept_when_offer_at_loadboard_rate(self):
        d = evaluate(RATE, RATE, 1)
        assert d.action == "accept"
        assert d.counter_offer is None
        assert d.should_close is False

    def test_accept_when_offer_below_loadboard_rate(self):
        d = evaluate(RATE, 1800.0, 1)
        assert d.action == "accept"

    def test_counter_when_offer_above_ceiling(self):
        # ceiling = 2000 * 1.12 = 2240; offer > 2240
        d = evaluate(RATE, 2500.0, 1)
        assert d.action == "counter"
        assert d.counter_offer == round(RATE * 1.05, 2)   # 2100.0
        assert d.should_close is False

    def test_counter_with_midpoint_when_offer_between_rate_and_ceiling(self):
        # ceiling = 2240; offer = 2100 is between 2000 and 2240
        d = evaluate(RATE, 2100.0, 1)
        assert d.action == "counter"
        assert d.counter_offer == round((RATE + 2100.0) / 2, 2)  # 2050.0
        assert d.should_close is False

    def test_counter_exactly_at_ceiling_gets_midpoint(self):
        ceiling = RATE * 1.12   # 2240.0
        d = evaluate(RATE, ceiling, 1)
        assert d.action == "counter"
        assert d.counter_offer == round((RATE + ceiling) / 2, 2)

    def test_counter_one_cent_above_ceiling_uses_r1_counter(self):
        d = evaluate(RATE, RATE * 1.12 + 0.01, 1)
        assert d.action == "counter"
        assert d.counter_offer == round(RATE * 1.05, 2)


class TestRound2:
    def test_accept_when_offer_at_or_below_loadboard_rate(self):
        d = evaluate(RATE, RATE, 2)
        assert d.action == "accept"

    def test_counter_blends_toward_carrier_within_ceiling(self):
        # r1_counter=2100, offer=2150, ceiling=2200 (1.10)
        # blend = 2100 + 0.75*(2150-2100) = 2100 + 37.5 = 2137.5
        d = evaluate(RATE, 2150.0, 2)
        assert d.action == "counter"
        r1 = RATE * 1.05
        expected = round(r1 + 0.75 * (2150.0 - r1), 2)
        assert d.counter_offer == expected
        assert d.should_close is False

    def test_counter_capped_at_r2_ceiling_when_offer_is_very_high(self):
        ceiling = RATE * 1.10   # 2200.0
        d = evaluate(RATE, 3000.0, 2)
        assert d.action == "counter"
        assert d.counter_offer <= ceiling

    def test_should_close_is_false_in_round_2(self):
        d = evaluate(RATE, 2500.0, 2)
        assert d.should_close is False


class TestRound3:
    def test_accept_when_offer_within_final_ceiling(self):
        # accept ceiling = 2000 * 1.08 = 2160
        d = evaluate(RATE, 2160.0, 3)
        assert d.action == "accept"
        assert d.should_close is False

    def test_accept_when_offer_below_final_ceiling(self):
        d = evaluate(RATE, 2100.0, 3)
        assert d.action == "accept"

    def test_reject_when_offer_above_final_ceiling(self):
        d = evaluate(RATE, 2161.0, 3)
        assert d.action == "reject"
        assert d.counter_offer is None
        assert d.should_close is True

    def test_reject_for_very_high_offer(self):
        d = evaluate(RATE, 9999.0, 3)
        assert d.action == "reject"
        assert d.should_close is True

    def test_round_beyond_max_treated_as_final(self):
        # round 4 should behave exactly like round 3
        d4 = evaluate(RATE, 2161.0, 4)
        d3 = evaluate(RATE, 2161.0, 3)
        assert d4.action == d3.action
        assert d4.should_close == d3.should_close


# ── HTTP integration tests ────────────────────────────────────────────────────

URL = "/negotiation/evaluate-offer"


def _seed_load(db, rate: float = RATE) -> Load:
    load = Load(
        load_id="LD-NEG-01",
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


def test_evaluate_offer_accept(client, db):
    _seed_load(db)
    res = client.post(
        URL,
        json={"load_id": "LD-NEG-01", "loadboard_rate": RATE, "carrier_offer": RATE, "round": 1},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["action"] == "accept"


def test_evaluate_offer_counter(client, db):
    _seed_load(db)
    res = client.post(
        URL,
        json={"load_id": "LD-NEG-01", "loadboard_rate": RATE, "carrier_offer": 2500.0, "round": 1},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "counter"
    assert data["counter_offer"] == round(RATE * 1.05, 2)


def test_evaluate_offer_reject(client, db):
    _seed_load(db)
    res = client.post(
        URL,
        json={"load_id": "LD-NEG-01", "loadboard_rate": RATE, "carrier_offer": 9999.0, "round": 3},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "reject"
    assert data["should_close"] is True


def test_evaluate_offer_uses_db_rate_not_request_rate(client, db):
    """Caller cannot manipulate the negotiation by sending a fake loadboard_rate."""
    _seed_load(db, rate=2000.0)
    # send a fake low rate hoping to lower our counter-offer floor
    res = client.post(
        URL,
        json={"load_id": "LD-NEG-01", "loadboard_rate": 500.0, "carrier_offer": 2500.0, "round": 1},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    # counter should be based on 2000, not 500
    assert res.json()["counter_offer"] == round(2000.0 * 1.05, 2)


def test_evaluate_offer_load_not_found(client):
    res = client.post(
        URL,
        json={"load_id": "LD-MISSING", "loadboard_rate": RATE, "carrier_offer": 2500.0, "round": 1},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 404
