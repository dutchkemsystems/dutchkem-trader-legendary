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
from apps.scanner.scanner import MultiTimeframeScanner
from config.broker_config import BrokerConfig
from execution.broker_factory import create_broker
from execution.engine import OrderExecutionEngine
from cache.redis import RedisCache


@lru_cache
def get_market_analyst():
    return MarketAnalyst()


@lru_cache
def get_consensus_engine():
    analysts = [
        MarketAnalyst(), NewsAnalyst(), FundamentalsAnalyst(), SentimentAnalyst(),
        TechnicalAnalyst(), OptionsAnalyst(), OrderFlowAnalyst(), RiskAnalyst(),
        MacroAnalyst(), OnChainAnalyst(), QuantAnalyst(), ComplianceAnalyst()
    ]
    return ConsensusEngine(analysts=analysts)


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
