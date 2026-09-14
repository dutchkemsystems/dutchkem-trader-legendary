"""Tests for ScalpingEngine."""

import pytest
from unittest.mock import Mock
from apps.scalping.engine import ScalpingEngine


@pytest.fixture
def mock_mt5():
    return Mock()


@pytest.fixture
def mock_risk():
    risk = Mock()
    risk.balance = 10000.0
    risk.daily_pnl = 0.0
    risk.check_correlation.return_value = True
    risk.check_portfolio_limits.return_value = True
    risk.check_circuit_breaker.return_value = True
    return risk


def test_engine_initialization(mock_mt5, mock_risk):
    engine = ScalpingEngine(mock_mt5, mock_risk)
    assert len(engine.strategies) == 0  # All disabled by default


def test_engine_loads_enabled_strategies(mock_mt5, mock_risk):
    engine = ScalpingEngine(mock_mt5, mock_risk)
    # With all flags OFF, no strategies should load
    assert len(engine.strategies) == 0


def test_engine_trade_history_empty(mock_mt5, mock_risk):
    engine = ScalpingEngine(mock_mt5, mock_risk)
    assert len(engine.trade_history) == 0


def test_engine_get_trade_results_empty(mock_mt5, mock_risk):
    engine = ScalpingEngine(mock_mt5, mock_risk)
    results = engine.get_trade_results()
    assert len(results) == 0
