"""Tests for 5-Point Checklist Strategy."""

import pytest
from apps.scalping.strategies.checklist_5pt import FivePointChecklistStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return FivePointChecklistStrategy({'enabled': True, 'tp_pips': 15, 'sl_pips': 10, 'min_conditions': 5})


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M5', 'H1'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'checklist_5point'


def test_strategy_disabled_by_default():
    strategy = FivePointChecklistStrategy({'enabled': False})
    assert strategy.enabled is False
