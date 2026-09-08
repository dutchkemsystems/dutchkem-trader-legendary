from functools import lru_cache

from django.contrib.auth.models import User

from apps.analysts.compliance import ComplianceAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.consensus.engine import ConsensusEngine
from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory
from apps.scanner.scanner import MultiTimeframeScanner
from apps.vision import ChartAnalyzer
from config.broker_config import BrokerConfig
from execution.broker_factory import create_broker
from execution.engine import OrderExecutionEngine
from cache.redis import RedisCache


_chart_analyzer = None
_ml_predictor = None


def get_chart_analyzer():
    global _chart_analyzer
    if _chart_analyzer is None:
        _chart_analyzer = ChartAnalyzer()
    return _chart_analyzer


def get_ml_predictor():
    global _ml_predictor
    if _ml_predictor is None:
        _ml_predictor = MLPredictor(model_type="xgboost")
    return _ml_predictor


@lru_cache
def get_market_analyst():
    return MarketAnalyst()


@lru_cache
def get_consensus_engine():
    chart_analyzer = get_chart_analyzer()
    ml_predictor = get_ml_predictor()
    analysts = [
        MarketAnalyst(), NewsAnalyst(), FundamentalsAnalyst(), SentimentAnalyst(),
        TechnicalAnalyst(chart_analyzer=chart_analyzer), OptionsAnalyst(), OrderFlowAnalyst(),
        RiskAnalyst(), MacroAnalyst(), OnChainAnalyst(), QuantAnalyst(), ComplianceAnalyst()
    ]
    debate_engine = DebateEngine(max_rounds=1)
    memory = FinancialSituationMemory()
    return ConsensusEngine(
        analysts=analysts,
        ml_predictor=ml_predictor,
        debate_engine=debate_engine,
        memory=memory,
    )


@lru_cache
def get_consensus_gates():
    ml_predictor = get_ml_predictor()
    return ConsensusGates(ml_predictor=ml_predictor)


@lru_cache
def get_scanner():
    return MultiTimeframeScanner()


@lru_cache
def get_redis_cache():
    return RedisCache()


@lru_cache
def get_broker():
    config = BrokerConfig.from_env()
    return create_broker(config)


@lru_cache
def get_execution_engine():
    broker = get_broker()
    return OrderExecutionEngine(broker)


def get_current_user():
    return User.objects.first()
