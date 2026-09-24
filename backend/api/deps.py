from functools import lru_cache

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
from apps.consensus.gates import ConsensusGates
from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory
from apps.ml.data_loader import MLDataLoader
from apps.ml.predictor import MLPredictor
from apps.scanner.scanner import MultiTimeframeScanner
from apps.vision import ChartAnalyzer
from config.broker_config import BrokerConfig
from data.manager import MarketDataManager
from execution.broker_factory import create_broker
from execution.engine import OrderExecutionEngine
from apps.llm.client import LLMClient
from cache.redis import RedisCache


_chart_analyzer = None
_ml_predictor = None
_market_data_manager = None
_llm_client = None


def get_market_data_manager():
    global _market_data_manager
    if _market_data_manager is None:
        _market_data_manager = MarketDataManager()
    return _market_data_manager


@lru_cache
def get_ml_data_loader():
    data_manager = get_market_data_manager()
    return MLDataLoader(data_manager=data_manager)


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


def get_llm_client():
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


@lru_cache
def get_consensus_engine():
    chart_analyzer = get_chart_analyzer()
    ml_predictor = get_ml_predictor()
    llm_client = get_llm_client()
    # All analysts now provide real data — inject LLM client for enhanced analysis
    analysts = [
        MarketAnalyst(llm_client=llm_client),  # MT5 technical data
        FundamentalsAnalyst(
            llm_client=llm_client
        ),  # yfinance (DXY, yields, commodities)
        TechnicalAnalyst(
            chart_analyzer=chart_analyzer, llm_client=llm_client
        ),  # MT5 patterns
        OrderFlowAnalyst(llm_client=llm_client),  # MT5 tick data
        RiskAnalyst(llm_client=llm_client),  # MT5 account + price data
        QuantAnalyst(llm_client=llm_client),  # MT5 statistical analysis
        ComplianceAnalyst(llm_client=llm_client),  # MT5 position checks
        NewsAnalyst(llm_client=llm_client),  # RSS feeds (ForexLive, DailyFX, etc.)
        SentimentAnalyst(llm_client=llm_client),  # VIX + Fear&Greed + DXY momentum
        MacroAnalyst(llm_client=llm_client),  # yfinance (DXY, yields, commodities, VIX)
        OptionsAnalyst(llm_client=llm_client),  # SPY/QQQ options chain (put/call, IV)
        OnChainAnalyst(llm_client=llm_client),  # CoinGecko BTC dominance (risk-on/off)
    ]
    debate_engine = DebateEngine(llm_client=llm_client, max_rounds=1)
    memory = FinancialSituationMemory()
    return ConsensusEngine(
        analysts=analysts,
        ml_predictor=ml_predictor,
        debate_engine=debate_engine,
        memory=memory,
    )


def get_current_user():
    """Return a default user dict. Auth is handled by AuthMiddleware."""
    return {"id": 1, "username": "admin", "is_active": True}
