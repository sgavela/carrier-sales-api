"""
FMCSA_MOCK=true is set in conftest.py, so no real HTTP calls are made.

Mock behaviour:
  MC 000000  → not found
  MC 111111  → found, not authorized
  MC 123456  → found, authorized (ACME TRUCKING LLC)
  any other  → found, authorized (GENERIC TRANSPORT LLC)
"""
from tests.conftest import AUTH_HEADERS

URL = "/carriers/verify"


def post(client, mc: str):
    return client.post(URL, json={"mc_number": mc}, headers=AUTH_HEADERS)


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_requires_auth(client):
    res = client.post(URL, json={"mc_number": "123456"})
    assert res.status_code == 401


# ── MC normalisation ──────────────────────────────────────────────────────────

def test_mc_prefix_stripped(client):
    """'MC123456' should resolve the same as '123456'."""
    res = post(client, "MC123456")
    assert res.status_code == 200
    assert res.json()["mc_number"] == "123456"


def test_mc_dashes_and_spaces_stripped(client):
    res = post(client, "MC 12-3456")
    assert res.status_code == 200
    assert res.json()["mc_number"] == "123456"


# ── Eligible carrier ──────────────────────────────────────────────────────────

def test_eligible_carrier_returns_true(client):
    res = post(client, "123456")
    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is True
    assert data["carrier_name"] == "ACME TRUCKING LLC"
    assert data["allowed_to_operate"] == "Y"
    assert data["reason"] is None


def test_unknown_mc_returns_generic_eligible_carrier(client):
    res = post(client, "999999")
    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is True
    assert data["carrier_name"] == "GENERIC TRANSPORT LLC"


# ── Ineligible cases ──────────────────────────────────────────────────────────

def test_mc_not_found(client):
    res = post(client, "000000")
    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is False
    assert "not found" in data["reason"].lower()
    assert data["carrier_name"] is None


def test_not_authorized_to_operate(client):
    res = post(client, "111111")
    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is False
    assert data["allowed_to_operate"] == "N"
    assert "not authorized" in data["reason"].lower()


# ── Input validation ──────────────────────────────────────────────────────────

def test_empty_mc_returns_400(client):
    res = post(client, "   ")
    assert res.status_code == 400


def test_missing_mc_field_returns_422(client):
    res = client.post(URL, json={}, headers=AUTH_HEADERS)
    assert res.status_code == 422
