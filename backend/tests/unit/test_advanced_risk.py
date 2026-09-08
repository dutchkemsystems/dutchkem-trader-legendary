import pytest
from execution.kelly_sizer import KellySizer
from execution.risk_config import RiskConfig
from execution.circuit_breaker import CircuitBreaker, CircuitState


def test_kelly_sizing():
    sizer = KellySizer()
    fraction = sizer.calculate(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
    assert 0.0 < fraction < 0.25


def test_kelly_edge_cases():
    sizer = KellySizer()
    assert sizer.calculate(win_rate=0.0, avg_win=0.02, avg_loss=0.01) == 0.0
    assert sizer.calculate(win_rate=1.0, avg_win=0.02, avg_loss=0.01) == 0.0
    assert sizer.calculate(win_rate=0.6, avg_win=0.0, avg_loss=0.01) == 0.0


def test_hard_usd_cap():
    config = RiskConfig(max_position_usd=50000)
    capped = config.apply_usd_cap(lot_size=2.0, price=1.1000, symbol="EURUSD")
    assert capped * 1.1000 * 100000 <= 50000


def test_per_market_limit():
    config = RiskConfig(max_positions_per_market=2)
    assert config.check_per_market("EURUSD", {"EURUSD": 1}) is True
    assert config.check_per_market("EURUSD", {"EURUSD": 2}) is False


def test_per_hour_limit():
    config = RiskConfig(max_trades_per_hour=5)
    assert config.check_hourly_limit(3) is True
    assert config.check_hourly_limit(5) is False


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_trade() is True


def test_circuit_breaker_opens_on_loss():
    cb = CircuitBreaker(daily_loss_limit=5.0)
    cb.record_loss(6.0)
    assert cb.state == CircuitState.OPEN
    assert cb.can_trade() is False


def test_circuit_breaker_half_open():
    cb = CircuitBreaker(cooldown_minutes=0)
    cb.record_loss(6.0)
    assert cb.state == CircuitState.OPEN
    # With 0 cooldown, should immediately go to half-open
    assert cb.can_trade() is True
    assert cb.state == CircuitState.HALF_OPEN
