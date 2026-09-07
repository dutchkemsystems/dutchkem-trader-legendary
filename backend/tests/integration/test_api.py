import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Create a fake user without hitting the DB."""
    user = MagicMock()
    user.id = 1
    user.username = "admin"
    return user


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "checks" in data


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


def test_list_trades(client, mock_user):
    mock_engine = MagicMock()
    mock_engine.get_trade_history.return_value = []
    with (
        patch("api.routes.trades.get_current_user", return_value=mock_user),
        patch("api.routes.trades.get_execution_engine", return_value=mock_engine),
    ):
        response = client.get("/api/v1/trades/")
    assert response.status_code == 200
    assert "trades" in response.json()


def test_list_positions(client, mock_user):
    with (
        patch("api.routes.positions.get_current_user", return_value=mock_user),
    ):
        mock_qs = MagicMock()
        mock_qs.order_by.return_value = []
        with patch("api.routes.positions.Position.objects") as mock_objects:
            mock_objects.filter.return_value = mock_qs
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
