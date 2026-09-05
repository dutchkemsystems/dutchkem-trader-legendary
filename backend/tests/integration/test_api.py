import pytest
from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_analysts(client):
    response = client.get("/api/v1/analysts/")
    assert response.status_code == 200
    assert "analysts" in response.json()
    assert len(response.json()["analysts"]) == 12


def test_get_analyst(client):
    response = client.get("/api/v1/analysts/market")
    assert response.status_code == 200
    assert "capabilities" in response.json()


def test_get_analyst_not_found(client):
    response = client.get("/api/v1/analysts/nonexistent")
    assert response.status_code == 200  # Returns error dict, not 404
    assert "error" in response.json()


def test_list_trades(client):
    response = client.get("/api/v1/trades/")
    assert response.status_code == 200
    assert "trades" in response.json()


def test_list_positions(client):
    response = client.get("/api/v1/positions/")
    assert response.status_code == 200
    assert "positions" in response.json()


def test_get_price(client):
    response = client.get("/api/v1/market/EURUSD/price")
    assert response.status_code == 200
    assert response.json()["symbol"] == "EURUSD"
    assert "signal" in response.json()
    assert "confidence" in response.json()


def test_scan_symbol(client):
    response = client.get("/api/v1/scanner/EURUSD")
    assert response.status_code == 200
    assert "overall_signal" in response.json()
    assert "overall_confidence" in response.json()
    assert "timeframes" in response.json()


def test_get_seykota(client):
    response = client.get("/api/v1/legendary/seykota/EURUSD")
    assert response.status_code == 200
    assert "trend" in response.json()
    assert "action" in response.json()
    assert "confidence" in response.json()


def test_get_turtle_soup(client):
    response = client.get("/api/v1/legendary/turtle-soup/EURUSD")
    assert response.status_code == 200
    assert "result" in response.json()


def test_get_pyramiding(client):
    response = client.get("/api/v1/legendary/pyramiding/EURUSD")
    assert response.status_code == 200
    assert "entry_count" in response.json()
    assert "max_entries" in response.json()
