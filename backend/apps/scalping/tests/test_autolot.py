"""Tests for AutoLot 20-Pip Strategy."""

import pytest
from apps.scalping.strategies.autolot import AutoLotStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return AutoLotStrategy({'enabled': True, 'tp_pips': 20, 'sl_pips': 20, 'ema_fast': 10, 'ema_slow': 20, 'rsi_period': 14, 'adx_threshold': 25})


def test_required_timeframes(strategy):
    assert strategy.required_timeframes() == ['M5']


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'autolot_20pip'


def test_strategy_disabled_by_default():
    strategy = AutoLotStrategy({'enabled': False})
    assert strategy.enabled is False
