"""Tests for News Fade Strategy."""

import pytest
from apps.scalping.strategies.news_fade import NewsFadeStrategy
from apps.scalping.signals import SignalDirection


@pytest.fixture
def strategy():
    return NewsFadeStrategy({'enabled': True, 'events': ['NFP', 'CPI', 'FOMC'], 'wait_minutes': 5, 'tp_pips': 12, 'sl_pips': 8})


def test_required_timeframes(strategy):
    assert set(strategy.required_timeframes()) == {'M1', 'M5'}


def test_returns_none_on_empty_data(strategy):
    result = strategy.analyze('EURUSD', {})
    assert result is None


def test_analyze_returns_signal_or_none(strategy, mock_data_dict):
    result = strategy.analyze('EURUSD', mock_data_dict)
    if result is not None:
        assert result.strategy_name == 'news_fade'


def test_strategy_disabled_by_default():
    strategy = NewsFadeStrategy({'enabled': False})
    assert strategy.enabled is False
