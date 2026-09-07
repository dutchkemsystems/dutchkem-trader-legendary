import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from backend.execution.position_sizer import PositionSizer


@pytest.fixture
def mock_account_manager():
    am = MagicMock()
    config = MagicMock()
    config.balance = Decimal("10000.00")
    config.equity = Decimal("10000.00")
    am.get_config.return_value = config
    am.is_cent_account.return_value = False
    am.get_min_lot.return_value = Decimal("0.01")
    am.get_max_lot.return_value = Decimal("100")
    return am


@pytest.fixture
def cent_account_manager():
    am = MagicMock()
    config = MagicMock()
    config.balance = Decimal("500.00")
    config.equity = Decimal("500.00")
    am.get_config.return_value = config
    am.is_cent_account.return_value = True
    am.get_min_lot.return_value = Decimal("0.01")
    am.get_max_lot.return_value = Decimal("10")
    return am


@pytest.fixture
def sizer(mock_account_manager):
    return PositionSizer(mock_account_manager)


@pytest.fixture
def cent_sizer(cent_account_manager):
    return PositionSizer(cent_account_manager)


# =============================================================================
# calculate_lot_size
# =============================================================================

def test_calculate_lot_size(sizer):
    lot = sizer.calculate_lot_size(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
        risk_percent=Decimal("1.0"),
        symbol="EURUSD",
    )
    assert lot >= Decimal("0.01")
    assert lot <= Decimal("100")


def test_calculate_lot_size_no_config():
    am = MagicMock()
    am.get_config.return_value = None
    am.get_min_lot.return_value = Decimal("0.01")
    sizer = PositionSizer(am)
    lot = sizer.calculate_lot_size(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
    )
    assert lot == Decimal("0.01")


# =============================================================================
# calculate_lot_size_from_confidence
# =============================================================================

def test_calculate_lot_size_from_confidence(sizer):
    lot_high = sizer.calculate_lot_size_from_confidence(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
        confidence=0.95,
    )
    lot_low = sizer.calculate_lot_size_from_confidence(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
        confidence=0.5,
    )
    assert lot_high >= lot_low


# =============================================================================
# calculate_dynamic_stop_loss
# =============================================================================

def test_calculate_dynamic_stop_loss(sizer):
    sl_buy = sizer.calculate_dynamic_stop_loss(
        entry_price=Decimal("1.0850"), side="buy", symbol="EURUSD"
    )
    assert sl_buy < Decimal("1.0850")

    sl_sell = sizer.calculate_dynamic_stop_loss(
        entry_price=Decimal("1.0850"), side="sell", symbol="EURUSD"
    )
    assert sl_sell > Decimal("1.0850")


def test_calculate_dynamic_stop_loss_with_atr(sizer):
    sl = sizer.calculate_dynamic_stop_loss(
        entry_price=Decimal("1.0850"), side="buy",
        atr=Decimal("0.0050"), symbol="EURUSD"
    )
    expected = Decimal("1.0850") - Decimal("2") * Decimal("0.0050")
    assert sl == expected


# =============================================================================
# calculate_take_profit
# =============================================================================

def test_calculate_take_profit(sizer):
    tp_buy = sizer.calculate_take_profit(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
        side="buy",
        risk_reward_ratio=Decimal("2.0"),
    )
    risk = abs(Decimal("1.0850") - Decimal("1.0800"))
    expected = Decimal("1.0850") + risk * Decimal("2.0")
    assert tp_buy == expected

    tp_sell = sizer.calculate_take_profit(
        entry_price=Decimal("1.0850"),
        stop_loss=Decimal("1.0900"),
        side="sell",
        risk_reward_ratio=Decimal("2.0"),
    )
    risk_s = abs(Decimal("1.0850") - Decimal("1.0900"))
    expected_s = Decimal("1.0850") - risk_s * Decimal("2.0")
    assert tp_sell == expected_s
