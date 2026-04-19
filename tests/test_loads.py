from datetime import datetime


from app.models import EquipmentType, Load, LoadStatus
from tests.conftest import AUTH_HEADERS


def make_load(db, **kwargs) -> Load:
    defaults = dict(
        load_id="LD-TEST-01",
        origin="Chicago, IL",
        destination="Atlanta, GA",
        pickup_datetime=datetime(2026, 4, 25, 8, 0),
        delivery_datetime=datetime(2026, 4, 26, 18, 0),
        equipment_type=EquipmentType.dry_van,
        loadboard_rate=1500.0,
        weight=38000,
        commodity_type="Electronics",
        num_of_pieces=22,
        miles=716,
        dimensions="48x40x60 in",
        status=LoadStatus.available,
    )
    defaults.update(kwargs)
    load = Load(**defaults)
    db.add(load)
    db.commit()
    return load


# ── GET /loads/{id} ──────────────────────────────────────────────────────────

def test_get_load_found(client, db):
    make_load(db)
    res = client.get("/loads/LD-TEST-01", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["load_id"] == "LD-TEST-01"


def test_get_load_not_found(client):
    res = client.get("/loads/LD-MISSING", headers=AUTH_HEADERS)
    assert res.status_code == 404


# ── POST /loads/search ───────────────────────────────────────────────────────

def test_search_empty_db_returns_empty_list(client):
    res = client.post("/loads/search", json={}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == []


def test_search_by_origin_city(client, db):
    make_load(db, load_id="LD-T-01", origin="Chicago, IL")
    make_load(db, load_id="LD-T-02", origin="Houston, TX")
    res = client.post("/loads/search", json={"origin": "Chicago"}, headers=AUTH_HEADERS)
    data = res.json()
    assert len(data) == 1
    assert data[0]["origin"] == "Chicago, IL"


def test_search_by_origin_case_insensitive(client, db):
    make_load(db)
    res = client.post("/loads/search", json={"origin": "chicago, il"}, headers=AUTH_HEADERS)
    assert len(res.json()) == 1


def test_search_by_destination(client, db):
    make_load(db, load_id="LD-T-01", destination="Atlanta, GA")
    make_load(db, load_id="LD-T-02", destination="Dallas, TX")
    res = client.post("/loads/search", json={"destination": "Atlanta"}, headers=AUTH_HEADERS)
    data = res.json()
    assert len(data) == 1
    assert data[0]["destination"] == "Atlanta, GA"


def test_search_by_equipment_type(client, db):
    make_load(db, load_id="LD-T-01", equipment_type=EquipmentType.dry_van)
    make_load(db, load_id="LD-T-02", equipment_type=EquipmentType.reefer)
    res = client.post(
        "/loads/search", json={"equipment_type": "Reefer"}, headers=AUTH_HEADERS
    )
    data = res.json()
    assert len(data) == 1
    assert data[0]["equipment_type"] == "Reefer"


def test_search_by_pickup_date_range(client, db):
    make_load(db, load_id="LD-T-01", pickup_datetime=datetime(2026, 4, 20, 8, 0))
    make_load(db, load_id="LD-T-02", pickup_datetime=datetime(2026, 4, 28, 8, 0))
    res = client.post(
        "/loads/search",
        json={"pickup_date_from": "2026-04-19", "pickup_date_to": "2026-04-25"},
        headers=AUTH_HEADERS,
    )
    data = res.json()
    assert len(data) == 1
    assert data[0]["load_id"] == "LD-T-01"


def test_search_excludes_booked_loads(client, db):
    make_load(db, load_id="LD-T-01", status=LoadStatus.available)
    make_load(db, load_id="LD-T-02", status=LoadStatus.booked)
    res = client.post("/loads/search", json={}, headers=AUTH_HEADERS)
    data = res.json()
    assert len(data) == 1
    assert data[0]["load_id"] == "LD-T-01"


def test_search_respects_max_results(client, db):
    for i in range(5):
        make_load(
            db,
            load_id=f"LD-T-0{i}",
            pickup_datetime=datetime(2026, 4, 20 + i, 8, 0),
        )
    res = client.post("/loads/search", json={"max_results": 2}, headers=AUTH_HEADERS)
    assert len(res.json()) == 2


def test_search_results_ordered_by_pickup_asc(client, db):
    make_load(db, load_id="LD-T-01", pickup_datetime=datetime(2026, 4, 25, 8, 0))
    make_load(db, load_id="LD-T-02", pickup_datetime=datetime(2026, 4, 22, 8, 0))
    res = client.post("/loads/search", json={"max_results": 5}, headers=AUTH_HEADERS)
    ids = [r["load_id"] for r in res.json()]
    assert ids == ["LD-T-02", "LD-T-01"]
