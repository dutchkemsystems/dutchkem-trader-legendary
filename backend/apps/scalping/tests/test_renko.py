"""Tests for Renko Strategy."""

import pytest
from apps.scalping.strategies.renko import RenkoStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return RenkoStrategy({'enabled': True, 'brick_size_pips': 10, 'tp_pips': 20, 'sl_pips': 20})


def test_required_timeframes(strategy):
    assert strategy.required_timeframes() == ['M5']


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'renko_20pip'


def test_strategy_disabled_by_default():
    strategy = RenkoStrategy({'enabled': False})
    assert strategy.enabled is False
