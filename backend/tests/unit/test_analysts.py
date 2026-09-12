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
    assert 'dollar_index' in analyst.get_capabilities()


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


def test_risk_analyst():
    from apps.analysts.risk import RiskAnalyst
    analyst = RiskAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'portfolio_correlation' in analyst.get_capabilities()


def test_macro_analyst():
    from apps.analysts.macro import MacroAnalyst
    analyst = MacroAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'economic_indicators' in analyst.get_capabilities()


def test_on_chain_analyst():
    from apps.analysts.on_chain import OnChainAnalyst
    analyst = OnChainAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'blockchain_data' in analyst.get_capabilities()


def test_quant_analyst():
    from apps.analysts.quant import QuantAnalyst
    analyst = QuantAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'stat_arb' in analyst.get_capabilities()


def test_compliance_analyst():
    from apps.analysts.compliance import ComplianceAnalyst
    analyst = ComplianceAnalyst()
    assert hasattr(analyst, 'analyze')
    assert 'regulatory_checks' in analyst.get_capabilities()


def test_risk_analyst_analyze():
    from apps.analysts.risk import RiskAnalyst
    analyst = RiskAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'risk'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_macro_analyst_analyze():
    from apps.analysts.macro import MacroAnalyst
    analyst = MacroAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'macro'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_on_chain_analyst_analyze():
    from apps.analysts.on_chain import OnChainAnalyst
    analyst = OnChainAnalyst()
    result = asyncio.run(analyst.analyze('BTCUSD', '1H'))
    assert result.analyst_name == 'on_chain'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_quant_analyst_analyze():
    from apps.analysts.quant import QuantAnalyst
    analyst = QuantAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'quant'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_compliance_analyst_analyze():
    from apps.analysts.compliance import ComplianceAnalyst
    analyst = ComplianceAnalyst()
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'compliance'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_technical_analyst_with_chart_analyzer():
    from apps.analysts.technical import TechnicalAnalyst
    from apps.vision import ChartAnalyzer
    analyzer = ChartAnalyzer()
    analyst = TechnicalAnalyst(chart_analyzer=analyzer)
    assert analyst.chart_analyzer is analyzer
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'technical'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0
    assert 'patterns' in result.data
    assert 'support' in result.data or 'support_resistance' in result.data


def test_technical_analyst_without_chart_analyzer():
    from apps.analysts.technical import TechnicalAnalyst
    analyst = TechnicalAnalyst()
    assert analyst.chart_analyzer is None
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'technical'
    assert result.signal in ('BUY', 'SELL', 'HOLD')
    assert 0.0 <= result.confidence <= 1.0


def test_technical_analyst_chart_analyzer_provides_real_patterns():
    from apps.analysts.technical import TechnicalAnalyst
    from apps.vision import ChartAnalyzer
    import random
    random.seed(42)
    analyzer = ChartAnalyzer()
    analyst = TechnicalAnalyst(chart_analyzer=analyzer)
    result = asyncio.run(analyst.analyze('EURUSD', '1H'))
    assert result.analyst_name == 'technical'
    assert isinstance(result.data, dict)
