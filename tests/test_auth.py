from tests.conftest import AUTH_HEADERS


def test_health_requires_no_auth(client):
    res = client.get("/health")
    assert res.status_code == 200


def test_protected_endpoint_without_key_returns_401(client):
    res = client.post("/loads/search", json={})
    assert res.status_code == 401


def test_protected_endpoint_with_wrong_key_returns_401(client):
    res = client.post("/loads/search", json={}, headers={"X-API-Key": "wrong"})
    assert res.status_code == 401


def test_protected_endpoint_with_valid_key_returns_200(client):
    res = client.post("/loads/search", json={}, headers=AUTH_HEADERS)
    assert res.status_code == 200
