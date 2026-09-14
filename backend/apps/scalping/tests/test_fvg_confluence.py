"""Tests for FVG Confluence Strategy."""

import pytest
from apps.scalping.strategies.fvg_confluence import FVGConfluenceStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return FVGConfluenceStrategy({'enabled': True, 'htf': 'H4', 'entry_tf': 'M5', 'tp_pips': 15, 'sl_pips': 10})


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M5', 'H4'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'fvg_confluence'


def test_strategy_disabled_by_default():
    strategy = FVGConfluenceStrategy({'enabled': False})
    assert strategy.enabled is False
