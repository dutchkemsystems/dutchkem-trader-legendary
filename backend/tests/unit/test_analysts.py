import pytest
from apps.analysts.base import BaseAnalyst, AnalystResult


def test_analyst_result_creation():
    result = AnalystResult(
        analyst_name='test',
        symbol='EURUSD',
        timeframe='1H',
        signal='BUY',
        confidence=0.85,
        reasoning='Strong bullish signal',
        data={'rsi': 65}
    )
    assert result.analyst_name == 'test'
    assert result.signal == 'BUY'
    assert result.confidence == 0.85


def test_base_analyst_is_abstract():
    with pytest.raises(TypeError):
        BaseAnalyst()


def test_market_analyst_has_analyze_method():
    from apps.analysts.market import MarketAnalyst
    analyst = MarketAnalyst()
    assert hasattr(analyst, 'analyze')
    assert hasattr(analyst, 'get_capabilities')
