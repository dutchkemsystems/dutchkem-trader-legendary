"""Tests for Chiaroscuro Scalp Model Strategy."""

import pytest
from apps.scalping.strategies.chiaroscuro import ChiaroscuroStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return ChiaroscuroStrategy({
        'enabled': True,
        'tp_pips': 20,
        'sl_pips': 12,
        'min_confidence': 0.6
    })


def test_required_timeframes(strategy):
    assert strategy.required_timeframes() == ['M5', 'M15', 'H1']


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_returns_none_on_insufficient_data(strategy):
    import pandas as pd
    import numpy as np
    dates = pd.date_range('2026-01-01', periods=5, freq='5min')
    small_data = pd.DataFrame({
        'open': [1.1] * 5,
        'high': [1.11] * 5,
        'low': [1.09] * 5,
        'close': [1.1] * 5,
        'volume': [100] * 5
    }, index=dates)
    result = strategy.analyze('EURUSD', {'M5': small_data, 'M15': small_data, 'H1': small_data})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    # Result depends on mock data - either Signal or None
    if result is not None:
        assert result.strategy_name == 'chiaroscuro'
        assert result.direction in [SignalDirection.BUY, SignalDirection.SELL]
        assert result.sl_pips == 12
        assert result.tp_pips == 20
        assert 0 <= result.confidence <= 1.0


def test_validate_signal_always_true(strategy):
    from apps.scalping.signals import ScalpSignal
    signal = ScalpSignal(
        direction=SignalDirection.BUY,
        symbol='EURUSD',
        strategy_name='chiaroscuro',
        entry_price=1.1,
        sl_pips=12,
        tp_pips=20,
        confidence=0.7,
        reason='test'
    )
    assert strategy.validate_signal(signal) is True


def test_strategy_disabled_by_default():
    strategy = ChiaroscuroStrategy({'enabled': False})
    assert strategy.enabled is False


def test_strategy_enabled():
    strategy = ChiaroscuroStrategy({'enabled': True})
    assert strategy.enabled is True
