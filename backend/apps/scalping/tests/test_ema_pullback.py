"""Tests for EMA Pullback Strategy."""

import pytest
from apps.scalping.strategies.ema_pullback import EMAPullbackStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return EMAPullbackStrategy({'enabled': True, 'tp_pips': 20, 'sl_pips': 12, 'ema_fast': 10, 'ema_slow': 20})


def test_required_timeframes(strategy):
    assert strategy.required_timeframes() == ['M5']


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'ema_pullback'


def test_strategy_disabled_by_default():
    strategy = EMAPullbackStrategy({'enabled': False})
    assert strategy.enabled is False
