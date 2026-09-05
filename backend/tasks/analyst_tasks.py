# backend/tasks/analyst_tasks.py
from celery import shared_task
import asyncio
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.compliance import ComplianceAnalyst

ANALYSTS = {
    'market': MarketAnalyst(),
    'news': NewsAnalyst(),
    'fundamentals': FundamentalsAnalyst(),
    'sentiment': SentimentAnalyst(),
    'technical': TechnicalAnalyst(),
    'options': OptionsAnalyst(),
    'order_flow': OrderFlowAnalyst(),
    'risk': RiskAnalyst(),
    'macro': MacroAnalyst(),
    'on_chain': OnChainAnalyst(),
    'quant': QuantAnalyst(),
    'compliance': ComplianceAnalyst(),
}

@shared_task
def run_analyst(analyst_name: str, symbol: str, timeframe: str):
    analyst = ANALYSTS.get(analyst_name)
    if not analyst:
        return {'error': f'Analyst {analyst_name} not found'}
    
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(analyst.analyze(symbol, timeframe))
        return {
            'analyst_name': result.analyst_name,
            'symbol': result.symbol,
            'timeframe': result.timeframe,
            'signal': result.signal,
            'confidence': result.confidence,
            'reasoning': result.reasoning,
            'data': result.data
        }
    except Exception as e:
        return {'error': f'{analyst_name} failed: {str(e)}'}
    finally:
        loop.close()

@shared_task
def run_all_analysts(symbol: str, timeframe: str):
    results = []
    for name, analyst in ANALYSTS.items():
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(analyst.analyze(symbol, timeframe))
            results.append({
                'analyst_name': result.analyst_name,
                'signal': result.signal,
                'confidence': result.confidence
            })
        except Exception as e:
            results.append({
                'analyst_name': name,
                'error': str(e)
            })
        finally:
            loop.close()
    return results
