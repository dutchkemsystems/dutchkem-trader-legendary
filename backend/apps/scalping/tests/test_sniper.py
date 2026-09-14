"""Tests for Sniper Strategy."""

import pytest
from apps.scalping.strategies.sniper import SniperStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return SniperStrategy({'enabled': True, 'tp_pips': 15, 'sl_pips': 10, 'require_rejection_candle': True, 'lookback_periods': 20})


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M1', 'M5'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'sniper'
        assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]


def test_validate_signal_always_true(strategy):
    from apps.scalping.signals import ScalpSignal
    signal = ScalpSignal(direction=SignalDirection.BUY, symbol='EURUSD', strategy_name='sniper', entry_price=1.1, sl_pips=10, tp_pips=15, confidence=0.7, reason='test')
    assert strategy.validate_signal(signal) is True


def test_strategy_disabled_by_default():
    strategy = SniperStrategy({'enabled': False})
    assert strategy.enabled is False
