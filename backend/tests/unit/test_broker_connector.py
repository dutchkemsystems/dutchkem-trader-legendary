import pytest
from decimal import Decimal
from unittest.mock import patch

from backend.execution.broker import (
    BrokerOrder,
    OrderSide,
    OrderType,
)
from backend.execution.mt5_connector import MT5BrokerConnector


@pytest.fixture
def connector():
    """Fresh MT5BrokerConnector forced into simulation mode."""
    with patch("backend.execution.mt5_connector.MT5_AVAILABLE", False):
        conn = MT5BrokerConnector()
        yield conn


# =============================================================================
# Connection
# =============================================================================

def test_mt5_simulation_connect(connector):
    assert not connector.is_connected()
    result = connector.connect("12345", "pass", "SimServer")
    assert result is True
    assert connector.is_connected()
    assert connector._account_number == "12345"
    assert connector._server == "SimServer"


def test_mt5_disconnect(connector):
    connector.connect("12345", "pass", "SimServer")
    assert connector.is_connected()
    connector.disconnect()
    assert not connector.is_connected()


# =============================================================================
# Account info
# =============================================================================

def test_mt5_get_account_info(connector):
    connector.connect("SIM-001", "pass", "Sim")
    info = connector.get_account_info()
    assert info.account_number == "SIM-001"
    assert info.balance == Decimal("10000.00")
    assert info.leverage == 100
    assert info.currency == "USD"
    assert info.account_type == "STANDARD"


# =============================================================================
# Order simulation
# =============================================================================

def test_mt5_simulate_fill(connector):
    connector.connect("SIM-001", "pass", "Sim")
    order = BrokerOrder(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.10"),
        stop_loss=Decimal("1.0800"),
        take_profit=Decimal("1.0950"),
    )
    fill = connector.place_order(order)
    assert fill.symbol == "EURUSD"
    assert fill.side == OrderSide.BUY
    assert fill.quantity == Decimal("0.10")
    assert fill.price > Decimal("0")
    assert connector.is_connected()


# =============================================================================
# Positions
# =============================================================================

def test_mt5_get_positions(connector):
    connector.connect("SIM-001", "pass", "Sim")
    positions = connector.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 0


def test_mt5_close_position(connector):
    connector.connect("SIM-001", "pass", "Sim")
    order = BrokerOrder(
        symbol="GBPUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.50"),
    )
    fill = connector.place_order(order)
    ticket = int(fill.broker_order_id)

    positions = connector.get_positions()
    assert len(positions) == 1

    close_fill = connector.close_position(ticket)
    assert close_fill.symbol == "GBPUSD"
    assert close_fill.side == OrderSide.SELL
    assert close_fill.quantity == Decimal("0.50")

    positions = connector.get_positions()
    assert len(positions) == 0


def test_mt5_close_position_not_found(connector):
    connector.connect("SIM-001", "pass", "Sim")
    with pytest.raises(RuntimeError, match="not found"):
        connector.close_position(99999)
