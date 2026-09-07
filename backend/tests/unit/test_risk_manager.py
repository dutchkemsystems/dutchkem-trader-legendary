import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from execution.broker import BrokerOrder, OrderSide, OrderType
from execution.risk_manager import RiskManager
from django_app.models import Position


@pytest.fixture
def mock_account_manager():
    am = MagicMock()
    config = MagicMock()
    config.balance = Decimal("10000.00")
    config.equity = Decimal("10000.00")
    am.get_config.return_value = config
    return am


@pytest.fixture
def risk_manager(mock_account_manager):
    rm = RiskManager(mock_account_manager)
    rm._peak_balance = Decimal("10000.00")
    return rm


# =============================================================================
# validate_trade
# =============================================================================

def test_validate_trade_passes(risk_manager):
    with patch.object(Position.objects, "count", return_value=0):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
            stop_loss=Decimal("1.0800"),
        )
        ok, reason = risk_manager.validate_trade(order, Decimal("0.10"), Decimal("1.0850"))
        assert ok is True
        assert "passed" in reason.lower()


def test_validate_trade_rejects_no_stop_loss(risk_manager):
    with patch.object(Position.objects, "count", return_value=0):
        order = BrokerOrder(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.10"),
        )
        ok, reason = risk_manager.validate_trade(order, Decimal("0.10"), Decimal("1.0850"))
        assert ok is False
        assert "stop-loss" in reason.lower()


# =============================================================================
# enforce_stop_loss / enforce_take_profit
# =============================================================================

def test_enforce_stop_loss(risk_manager):
    position = MagicMock()
    position.current_price = Decimal("1.0780")
    position.stop_loss = Decimal("1.0800")
    position.side = "BUY"
    result = risk_manager.enforce_stop_loss(position)
    assert result == Decimal("1.0780")


def test_enforce_stop_loss_no_trigger(risk_manager):
    position = MagicMock()
    position.current_price = Decimal("1.0850")
    position.stop_loss = Decimal("1.0800")
    position.side = "BUY"
    result = risk_manager.enforce_stop_loss(position)
    assert result is None


def test_enforce_take_profit(risk_manager):
    position = MagicMock()
    position.current_price = Decimal("1.0960")
    position.take_profit = Decimal("1.0950")
    position.side = "BUY"
    result = risk_manager.enforce_take_profit(position)
    assert result == Decimal("1.0960")


def test_enforce_take_profit_no_trigger(risk_manager):
    position = MagicMock()
    position.current_price = Decimal("1.0900")
    position.take_profit = Decimal("1.0950")
    position.side = "BUY"
    result = risk_manager.enforce_take_profit(position)
    assert result is None


# =============================================================================
# risk_status
# =============================================================================

def test_risk_status(risk_manager):
    with patch.object(Position.objects, "count", return_value=3):
        status = risk_manager.get_risk_status()
        assert status["daily_trades"] == 0
        assert status["open_positions"] == 3
        assert status["max_open_positions"] == 10
        assert "daily_pnl" in status
        assert "drawdown_pct" in status
