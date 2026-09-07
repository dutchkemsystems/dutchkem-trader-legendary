"""Tests for AccountConfig sync between broker API and Django model."""
import pytest
from unittest.mock import patch, MagicMock, ANY
from decimal import Decimal
from datetime import datetime, timezone

from django_app.models import AccountConfig


@pytest.fixture
def client():
    from api.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def test_user(db):
    from django.contrib.auth.models import User
    return User.objects.create_user(
        username="sync_tester",
        email="sync@dutchkem.com",
        password="testpass",
    )


def _make_account_info(**overrides):
    """Create a mock AccountInfo with sensible defaults."""
    from execution.broker import AccountInfo
    defaults = dict(
        account_number="12345",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        margin=Decimal("0.00"),
        free_margin=Decimal("10000.00"),
        leverage=100,
        currency="USD",
        account_type="STANDARD",
        profit=Decimal("0.00"),
    )
    defaults.update(overrides)
    return AccountInfo(**defaults)


def _mock_config(**overrides):
    """Create a mock AccountConfig."""
    cfg = MagicMock(spec=AccountConfig)
    cfg.broker = "MT5"
    cfg.account_number = ""
    cfg.account_type = None
    cfg.balance = Decimal("0.00")
    cfg.equity = Decimal("0.00")
    cfg.margin = Decimal("0.00")
    cfg.free_margin = Decimal("0.00")
    cfg.leverage = 100
    cfg.currency = "USD"
    cfg.is_connected = False
    cfg.simulation_mode = True
    cfg.last_synced = None
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _mock_broker_config(**overrides):
    """Create a mock BrokerConfig."""
    bc = MagicMock()
    bc.simulation_mode = True
    for k, v in overrides.items():
        setattr(bc, k, v)
    return bc


# ---------------------------------------------------------------------------
# Unit tests for _sync_config_from_broker helper
# ---------------------------------------------------------------------------

def test_sync_config_from_broker_connected():
    """_sync_config_from_broker updates config fields from broker info."""
    from api.routes.broker import _sync_config_from_broker

    config = _mock_config()
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = _make_account_info()
    broker_config = _mock_broker_config(simulation_mode=False)

    _sync_config_from_broker(config, broker, broker_config)

    assert config.account_number == "12345"
    assert config.balance == Decimal("10000.00")
    assert config.is_connected is True
    assert config.simulation_mode is False
    assert config.last_synced is not None
    config.save.assert_called_once()


def test_sync_config_from_broker_disconnected():
    """_sync_config_from_broker sets disconnected state."""
    from api.routes.broker import _sync_config_from_broker

    config = _mock_config(is_connected=True, account_number="99999")
    broker = MagicMock()
    broker.is_connected.return_value = False
    broker_config = _mock_broker_config(simulation_mode=True)

    _sync_config_from_broker(config, broker, broker_config)

    assert config.is_connected is False
    assert config.simulation_mode is True
    config.save.assert_called_once()


def test_sync_config_auto_detects_cent_account():
    """_sync_config_from_broker auto-detects cent account type."""
    from api.routes.broker import _sync_config_from_broker

    config = _mock_config(account_type=None)
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = _make_account_info(
        balance=Decimal("500.00"),
    )
    broker_config = _mock_broker_config(simulation_mode=True)

    _sync_config_from_broker(config, broker, broker_config)

    assert config.account_type == AccountConfig.AccountType.CENT


def test_sync_config_auto_detects_standard_account():
    """_sync_config_from_broker auto-detects standard account type."""
    from api.routes.broker import _sync_config_from_broker

    config = _mock_config(account_type=None)
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = _make_account_info(
        balance=Decimal("10000.00"),
    )
    broker_config = _mock_broker_config(simulation_mode=False)

    _sync_config_from_broker(config, broker, broker_config)

    assert config.account_type == AccountConfig.AccountType.STANDARD


def test_sync_config_preserves_existing_account_type():
    """_sync_config_from_broker preserves existing account_type."""
    from api.routes.broker import _sync_config_from_broker

    config = _mock_config(account_type=AccountConfig.AccountType.CENT)
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = _make_account_info(
        balance=Decimal("10000.00"),
    )
    broker_config = _mock_broker_config(simulation_mode=False)

    _sync_config_from_broker(config, broker, broker_config)

    assert config.account_type == AccountConfig.AccountType.CENT


# ---------------------------------------------------------------------------
# Unit tests for _get_or_create_config helper
# ---------------------------------------------------------------------------

def test_get_or_create_config(db):
    """_get_or_create_config returns existing config."""
    from api.routes.broker import _get_or_create_config
    from django.contrib.auth.models import User

    user = User.objects.create_user(username="cfg_user", password="pass")
    existing = AccountConfig.objects.create(user=user, broker="MT5", balance=Decimal("500.00"))
    config = _get_or_create_config(user)
    assert config.pk == existing.pk
    assert config.balance == Decimal("500.00")


def test_get_or_create_config_creates_default(db):
    """_get_or_create_config creates default config if none exists."""
    from api.routes.broker import _get_or_create_config
    from django.contrib.auth.models import User

    user = User.objects.create_user(username="new_user", password="pass")
    config = _get_or_create_config(user)
    assert config.broker == "MT5"
    assert config.is_connected is False
    assert config.simulation_mode is True


# ---------------------------------------------------------------------------
# Route tests — GET /broker/config
# ---------------------------------------------------------------------------

def test_broker_config_endpoint(client):
    """GET /broker/config returns the stored AccountConfig."""
    mock_cfg = _mock_config(
        account_number="12345", balance=Decimal("10000.00"),
        is_connected=True, simulation_mode=False,
    )
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg

        response = client.get("/api/v1/broker/config")
        assert response.status_code == 200
        data = response.json()
        assert data["account_number"] == "12345"
        assert data["is_connected"] is True
        assert data["simulation_mode"] is False


# ---------------------------------------------------------------------------
# Route tests — POST /broker/sync
# ---------------------------------------------------------------------------

def test_broker_sync_endpoint_connected(client):
    """POST /broker/sync syncs broker state and returns it."""
    mock_cfg = _mock_config(
        account_number="12345", balance=Decimal("10000.00"),
        is_connected=True, simulation_mode=False,
    )
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker.get_broker") as mock_get_broker, \
         patch("api.routes.broker.BrokerConfig") as mock_bc_cls:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = True
        mock_broker.get_account_info.return_value = _make_account_info()
        mock_get_broker.return_value = mock_broker
        mock_bc_cls.from_env.return_value = _mock_broker_config(simulation_mode=False)

        response = client.post("/api/v1/broker/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["synced"] is True
        assert data["account_number"] == "12345"
        assert data["is_connected"] is True
        assert data["simulation_mode"] is False
        mock_cfg.save.assert_called_once()


def test_broker_sync_endpoint_disconnected(client):
    """POST /broker/sync when broker is disconnected."""
    mock_cfg = _mock_config(
        is_connected=True, simulation_mode=True,
    )
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker.get_broker") as mock_get_broker, \
         patch("api.routes.broker.BrokerConfig") as mock_bc_cls:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = False
        mock_get_broker.return_value = mock_broker
        mock_bc_cls.from_env.return_value = _mock_broker_config(simulation_mode=True)

        response = client.post("/api/v1/broker/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["is_connected"] is False
        assert data["simulation_mode"] is True


# ---------------------------------------------------------------------------
# Route tests — POST /broker/connect
# ---------------------------------------------------------------------------

def test_broker_connect_syncs_config(client):
    """POST /broker/connect also syncs AccountConfig."""
    mock_cfg = _mock_config()
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker._sync_config_from_broker") as mock_sync, \
         patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_broker.connect.return_value = True
        mock_broker.is_connected.return_value = True
        mock_broker.get_account_info.return_value = _make_account_info()
        mock_get_broker.return_value = mock_broker

        response = client.post("/api/v1/broker/connect", json={
            "account_number": "12345",
            "password": "test",
            "server": "Exness-MT5Trial",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "connected"
        mock_sync.assert_called_once_with(mock_cfg, mock_broker, ANY)


def test_broker_connect_failed_no_sync(client):
    """POST /broker/connect on failure does not sync."""
    mock_cfg = _mock_config()
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker._sync_config_from_broker") as mock_sync, \
         patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_broker.connect.return_value = False
        mock_get_broker.return_value = mock_broker

        response = client.post("/api/v1/broker/connect", json={
            "account_number": "12345",
            "password": "test",
            "server": "Exness-MT5Trial",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Route tests — POST /broker/disconnect
# ---------------------------------------------------------------------------

def test_broker_disconnect_syncs_config(client):
    """POST /broker/disconnect also syncs AccountConfig."""
    mock_cfg = _mock_config(is_connected=True)
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker._sync_config_from_broker") as mock_sync, \
         patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_get_broker.return_value = mock_broker

        response = client.post("/api/v1/broker/disconnect")
        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"
        mock_sync.assert_called_once_with(mock_cfg, mock_broker, ANY)


# ---------------------------------------------------------------------------
# Route tests — GET /broker/account
# ---------------------------------------------------------------------------

def test_broker_account_syncs_config(client):
    """GET /broker/account also syncs AccountConfig."""
    mock_cfg = _mock_config()
    with patch("api.routes.broker.get_current_user") as mock_user, \
         patch("api.routes.broker._get_or_create_config") as mock_get_cfg, \
         patch("api.routes.broker._sync_config_from_broker") as mock_sync, \
         patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_user.return_value = MagicMock()
        mock_get_cfg.return_value = mock_cfg
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = True
        mock_broker.get_account_info.return_value = _make_account_info()
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/account")
        assert response.status_code == 200
        data = response.json()
        assert data["account_number"] == "12345"
        mock_sync.assert_called_once_with(mock_cfg, mock_broker, ANY)


# ---------------------------------------------------------------------------
# Edge case: existing status/connect/disconnect endpoints still work
# ---------------------------------------------------------------------------

def test_broker_status_still_works(client):
    """GET /broker/status endpoint is not broken by sync changes."""
    with patch("api.routes.broker.get_broker") as mock_get_broker:
        mock_broker = MagicMock()
        mock_broker.is_connected.return_value = False
        mock_get_broker.return_value = mock_broker

        response = client.get("/api/v1/broker/status")
        assert response.status_code == 200
        assert response.json()["connected"] is False
