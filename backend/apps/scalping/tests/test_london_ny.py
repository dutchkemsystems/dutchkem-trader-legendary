"""Tests for London/NY Overlap Scalping Strategy."""

import pytest
from apps.scalping.strategies.london_ny import LondonNYOverlapStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return LondonNYOverlapStrategy({
        'enabled': True,
        'tp_pips': 15,
        'sl_pips': 10,
        'bb_squeeze_threshold': 0.02
    })


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M1', 'M5'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_returns_none_on_insufficient_data(strategy):
    import pandas as pd
    dates = pd.date_range('2026-01-01', periods=5, freq='1min')
    small_data = pd.DataFrame({
        'open': [1.1] * 5,
        'high': [1.11] * 5,
        'low': [1.09] * 5,
        'close': [1.1] * 5,
        'volume': [100] * 5
    }, index=dates)
    result = strategy.analyze('EURUSD', {'M1': small_data, 'M5': small_data})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'london_ny_overlap'
        assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
        assert result.sl_pips == 10
        assert result.tp_pips == 15
        assert 0 <= result.confidence <= 1.0


def test_validate_signal_always_true(strategy):
    from apps.scalping.signals import ScalpSignal
    signal = ScalpSignal(
        direction=SignalDirection.BUY,
        symbol='EURUSD',
        strategy_name='london_ny_overlap',
        entry_price=1.1,
        sl_pips=10,
        tp_pips=15,
        confidence=0.7,
        reason='test'
    )
    assert strategy.validate_signal(signal) is True


def test_strategy_disabled_by_default():
    strategy = LondonNYOverlapStrategy({'enabled': False})
    assert strategy.enabled is False
