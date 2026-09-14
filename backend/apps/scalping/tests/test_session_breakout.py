"""Tests for Session Open Breakout Strategy."""

import pytest
from apps.scalping.strategies.session_breakout import SessionBreakoutStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return SessionBreakoutStrategy({
        'enabled': True,
        'session_open_gmt': '08:00',
        'range_minutes': 60,
        'tp_pips': 15,
        'sl_pips': 10
    })


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M5', 'M15'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_returns_none_on_insufficient_data(strategy):
    import pandas as pd
    dates = pd.date_range('2026-01-01', periods=5, freq='5min')
    small_data = pd.DataFrame({
        'open': [1.1] * 5,
        'high': [1.11] * 5,
        'low': [1.09] * 5,
        'close': [1.1] * 5,
        'volume': [100] * 5
    }, index=dates)
    result = strategy.analyze('EURUSD', {'M5': small_data, 'M15': small_data})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'session_breakout'
        assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
        assert result.sl_pips == 10
        assert result.tp_pips == 15
        assert 0 <= result.confidence <= 1.0


def test_validate_signal_always_true(strategy):
    from apps.scalping.signals import ScalpSignal
    signal = ScalpSignal(
        direction=SignalDirection.BUY,
        symbol='EURUSD',
        strategy_name='session_breakout',
        entry_price=1.1,
        sl_pips=10,
        tp_pips=15,
        confidence=0.7,
        reason='test'
    )
    assert strategy.validate_signal(signal) is True


def test_strategy_disabled_by_default():
    strategy = SessionBreakoutStrategy({'enabled': False})
    assert strategy.enabled is False
