import asyncio

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


def test_news_analyst():
    from apps.analysts.news import NewsAnalyst
    analyst = NewsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'sentiment_analysis' in analyst.get_capabilities()


def test_fundamentals_analyst():
    from apps.analysts.fundamentals import FundamentalsAnalyst
    analyst = FundamentalsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'financial_ratios' in analyst.get_capabilities()


def test_sentiment_analyst():
    from apps.analysts.sentiment import SentimentAnalyst
    analyst = SentimentAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'social_sentiment' in analyst.get_capabilities()


def test_news_analyst_analyze():
    from apps.analysts.news import NewsAnalyst
    analyst = NewsAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'news'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_fundamentals_analyst_analyze():
    from apps.analysts.fundamentals import FundamentalsAnalyst
    analyst = FundamentalsAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'fundamentals'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_sentiment_analyst_analyze():
    from apps.analysts.sentiment import SentimentAnalyst
    analyst = SentimentAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'sentiment'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_technical_analyst():
    from apps.analysts.technical import TechnicalAnalyst
    analyst = TechnicalAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'chart_patterns' in analyst.get_capabilities()


def test_options_analyst():
    from apps.analysts.options import OptionsAnalyst
    analyst = OptionsAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'implied_volatility' in analyst.get_capabilities()


def test_order_flow_analyst():
    from apps.analysts.order_flow import OrderFlowAnalyst
    analyst = OrderFlowAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'microprice' in analyst.get_capabilities()


def test_technical_analyst_analyze():
    from apps.analysts.technical import TechnicalAnalyst
    analyst = TechnicalAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'technical'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_options_analyst_analyze():
    from apps.analysts.options import OptionsAnalyst
    analyst = OptionsAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'options'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_order_flow_analyst_analyze():
    from apps.analysts.order_flow import OrderFlowAnalyst
    analyst = OrderFlowAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'order_flow'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0
