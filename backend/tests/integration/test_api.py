import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_analysts():
    response = client.get("/api/v1/analysts/")
    assert response.status_code == 200
    assert "analysts" in response.json()
    assert len(response.json()["analysts"]) == 12


def test_get_analyst():
    response = client.get("/api/v1/analysts/market")
    assert response.status_code == 200
    assert "capabilities" in response.json()


def test_get_analyst_not_found():
    response = client.get("/api/v1/analysts/nonexistent")
    assert response.status_code == 200  # Returns error dict, not 404
    assert "error" in response.json()


def test_list_trades():
    response = client.get("/api/v1/trades/")
    assert response.status_code == 200
    assert "trades" in response.json()


def test_list_positions():
    response = client.get("/api/v1/positions/")
    assert response.status_code == 200
    assert "positions" in response.json()


def test_get_price():
    response = client.get("/api/v1/market/EURUSD/price")
    assert response.status_code == 200
    assert response.json()["symbol"] == "EURUSD"
    assert "signal" in response.json()
    assert "confidence" in response.json()


def test_scan_symbol():
    response = client.get("/api/v1/scanner/EURUSD")
    assert response.status_code == 200
    assert "overall_signal" in response.json()
    assert "overall_confidence" in response.json()
    assert "timeframes" in response.json()


def test_get_seykota():
    response = client.get("/api/v1/legendary/seykota/EURUSD")
    assert response.status_code == 200
    assert "trend" in response.json()
    assert "action" in response.json()
    assert "confidence" in response.json()


def test_get_turtle_soup():
    response = client.get("/api/v1/legendary/turtle-soup/EURUSD")
    assert response.status_code == 200
    assert "result" in response.json()


def test_get_pyramiding():
    response = client.get("/api/v1/legendary/pyramiding/EURUSD")
    assert response.status_code == 200
    assert "entry_count" in response.json()
    assert "max_entries" in response.json()
