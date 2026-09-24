import pytest
from decimal import Decimal
from unittest.mock import patch

from execution.broker import (
    BrokerOrder,
    OrderSide,
    OrderType,
)
from execution.mt5_connector import MT5Connector


@pytest.fixture
def connector():
    """Fresh MT5Connector forced into simulation mode."""
    with patch("execution.mt5_connector.MT5_AVAILABLE", False):
        conn = MT5Connector()
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


# =============================================================================
# Config injection
# =============================================================================

def test_connector_accepts_config_simulation():
    from config.broker_config import BrokerConfig
    cfg = BrokerConfig()
    with patch("execution.mt5_connector.MT5_AVAILABLE", False):
        conn = MT5Connector(config=cfg)
    assert conn._config is cfg


def test_connector_config_magic_number():
    from config.broker_config import BrokerConfig
    cfg = BrokerConfig(magic_number=999999)
    with patch("execution.mt5_connector.MT5_AVAILABLE", False):
        conn = MT5Connector(config=cfg)
    assert conn._config.magic_number == 999999


def test_connector_default_config():
    with patch("execution.mt5_connector.MT5_AVAILABLE", False):
        conn = MT5Connector()
    from config.broker_config import BrokerConfig
    assert isinstance(conn._config, BrokerConfig)


# =============================================================================
# Pending order management (for Gold Hedge EA)
# =============================================================================

def test_cancel_pending_order_sim(connector):
    """Should cancel pending order in simulation mode."""
    connector.connect("SIM-001", "pass", "Sim")
    
    # Manually add a pending order to sim state
    connector._sim_pending[12345] = {
        'symbol': 'XAUUSD',
        'type': 'BUY_STOP',
        'volume': 0.01,
        'price': 2010.0,
    }
    
    result = connector.cancel_pending_order(12345)
    assert result is True
    assert 12345 not in connector._sim_pending


def test_cancel_pending_order_not_found(connector):
    """Should return False for non-existent pending order."""
    connector.connect("SIM-001", "pass", "Sim")
    result = connector.cancel_pending_order(99999)
    assert result is False


def test_modify_pending_order_sim(connector):
    """Should modify pending order in simulation mode."""
    connector.connect("SIM-001", "pass", "Sim")
    
    connector._sim_pending[12345] = {
        'symbol': 'XAUUSD',
        'type': 'BUY_STOP',
        'volume': 0.01,
        'price': 2010.0,
        'sl': 2000.0,
        'tp': 2020.0,
    }
    
    result = connector.modify_pending_order(12345, price=Decimal("2015.0"), stop_loss=Decimal("2005.0"))
    assert result is True
    assert connector._sim_pending[12345]['price'] == Decimal("2015.0")
    assert connector._sim_pending[12345]['sl'] == Decimal("2005.0")


def test_modify_pending_order_not_found(connector):
    """Should return False for non-existent pending order."""
    connector.connect("SIM-001", "pass", "Sim")
    result = connector.modify_pending_order(99999, price=Decimal("2015.0"))
    assert result is False


def test_get_pending_orders_sim(connector):
    """Should return pending orders in simulation mode."""
    connector.connect("SIM-001", "pass", "Sim")
    
    connector._sim_pending[12345] = {
        'symbol': 'XAUUSD',
        'type': 'BUY_STOP',
        'volume': 0.01,
        'price': 2010.0,
        'magic': 234020,
    }
    connector._sim_pending[12346] = {
        'symbol': 'EURUSD',
        'type': 'SELL_LIMIT',
        'volume': 0.02,
        'price': 1.1000,
        'magic': 234010,
    }
    
    # Get all
    orders = connector.get_pending_orders()
    assert len(orders) == 2
    
    # Filter by symbol
    orders = connector.get_pending_orders(symbol='XAUUSD')
    assert len(orders) == 1
    assert orders[0]['symbol'] == 'XAUUSD'
    
    # Filter by magic
    orders = connector.get_pending_orders(magic=234020)
    assert len(orders) == 1
    assert orders[0]['magic'] == 234020


def test_get_pending_orders_empty(connector):
    """Should return empty list when no pending orders."""
    connector.connect("SIM-001", "pass", "Sim")
    orders = connector.get_pending_orders()
    assert orders == []
