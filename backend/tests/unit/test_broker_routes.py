"""Tests for broker API routes."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


def test_broker_status_endpoint_returns_simulation_mode(client):
    """GET /api/v1/broker/status should return connection status."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = False
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/status")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert data["connected"] is False


def test_broker_status_connected(client):
    """GET /api/v1/broker/status should show connected state."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = True
        mock_broker._account_number = "12345"
        mock_broker._server = "Exness-MT5Trial"
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["account_number"] == "12345"
        assert data["server"] == "Exness-MT5Trial"


def test_broker_connect_endpoint(client):
    """POST /api/v1/broker/connect should attempt connection."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.connect.return_value = True
        mock_broker.is_connected.return_value = True
        mock_broker.get_account_info.return_value = MagicMock(
            account_number="12345",
            balance=MagicMock(__str__=lambda s: "10000.00"),
            equity=MagicMock(__str__=lambda s: "10000.00"),
            free_margin=MagicMock(__str__=lambda s: "10000.00"),
            leverage=100,
            currency="USD",
            account_type="simulation",
            profit=MagicMock(__str__=lambda s: "0.00"),
        )
        mock_get_broker.return_value = mock_broker

        response = client.post("/api/v1/broker/connect", json={
            "account_number": "12345",
            "password": "test",
            "server": "Exness-MT5Trial",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"


def test_broker_disconnect_endpoint(client):
    """POST /api/v1/broker/disconnect should disconnect."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.disconnect.return_value = None
        mock_get_broker.return_value = mock_broker

        response = client.post("/api/v1/broker/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"


def test_broker_account_info_endpoint(client):
    """GET /api/v1/broker/account should return account info when connected."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = True
        mock_broker.get_account_info.return_value = MagicMock(
            account_number="12345",
            balance=MagicMock(__str__=lambda s: "10000.00"),
            equity=MagicMock(__str__=lambda s: "10000.00"),
            free_margin=MagicMock(__str__=lambda s: "10000.00"),
            leverage=100,
            currency="USD",
            account_type="simulation",
            profit=MagicMock(__str__=lambda s: "0.00"),
        )
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/account")
        assert response.status_code == 200
        data = response.json()
        assert "account_number" in data
        assert "balance" in data


def test_broker_account_info_not_connected(client):
    """GET /api/v1/broker/account should return 503 when not connected."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = False
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/account")
        assert response.status_code == 503
