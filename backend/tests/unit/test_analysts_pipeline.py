import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from data.models import Candle, Tick, Quote, Timeframe
from data.providers import BaseDataProvider
from data.registry import ProviderRegistry
from data.manager import MarketDataManager
from apps.analysts.market import MarketAnalyst


# --- BaseDataProvider ABC tests ---

def test_base_provider_is_abstract():
    with pytest.raises(TypeError):
        BaseDataProvider()


def test_base_provider_has_required_methods():
    assert hasattr(BaseDataProvider, 'get_candles')
    assert hasattr(BaseDataProvider, 'get_latest_price')
    assert hasattr(BaseDataProvider, 'get_quote')


# --- StubProvider tests ---

def test_stub_provider_returns_candles():
    from data.providers import StubProvider
    provider = StubProvider()
    candles = asyncio.run(provider.get_candles("EURUSD", Timeframe.ONE_HOUR, 10))
    assert len(candles) == 10
    assert all(isinstance(c, Candle) for c in candles)
    assert all(c.symbol == "EURUSD" for c in candles)


def test_stub_provider_returns_latest_price():
    from data.providers import StubProvider
    provider = StubProvider()
    price = asyncio.run(provider.get_latest_price("EURUSD"))
    assert isinstance(price, float)
    assert price > 0


def test_stub_provider_returns_quote():
    from data.providers import StubProvider
    provider = StubProvider()
    quote = asyncio.run(provider.get_quote("EURUSD"))
    assert isinstance(quote, Quote)
    assert quote.bid < quote.ask


# --- ProviderRegistry tests ---

def test_registry_registers_provider():
    from data.providers import StubProvider
    registry = ProviderRegistry()
    provider = StubProvider()
    registry.register(provider)
    assert len(registry.providers) == 1


def test_registry_fallback_on_failure():
    from data.providers import StubProvider
    registry = ProviderRegistry()

    failing_provider = MagicMock(spec=BaseDataProvider)
    failing_provider.name = "failing"
    failing_provider.get_candles = AsyncMock(side_effect=Exception("Provider down"))

    stub_provider = StubProvider()
    registry.register(failing_provider)
    registry.register(stub_provider)

    candles = asyncio.run(registry.get_candles("EURUSD", Timeframe.ONE_HOUR, 5))
    assert len(candles) == 5


def test_registry_raises_when_all_fail():
    from data.providers import StubProvider
    registry = ProviderRegistry()

    failing1 = MagicMock(spec=BaseDataProvider)
    failing1.name = "failing1"
    failing1.get_candles = AsyncMock(side_effect=Exception("fail1"))

    failing2 = MagicMock(spec=BaseDataProvider)
    failing2.name = "failing2"
    failing2.get_candles = AsyncMock(side_effect=Exception("fail2"))

    registry.register(failing1)
    registry.register(failing2)

    with pytest.raises(Exception, match="All providers failed"):
        asyncio.run(registry.get_candles("EURUSD", Timeframe.ONE_HOUR, 5))


# --- MarketDataManager tests ---

def test_data_manager_has_registry():
    manager = MarketDataManager()
    assert hasattr(manager, 'registry')
    assert isinstance(manager.registry, ProviderRegistry)


def test_data_manager_get_candles():
    manager = MarketDataManager()
    candles = asyncio.run(manager.get_candles("EURUSD", Timeframe.ONE_HOUR, 10))
    assert len(candles) == 10
    assert all(isinstance(c, Candle) for c in candles)


def test_data_manager_get_latest_price():
    manager = MarketDataManager()
    price = asyncio.run(manager.get_latest_price("EURUSD"))
    assert isinstance(price, float)
    assert price > 0


# --- MarketAnalyst + DataPipeline integration tests ---

def test_market_analyst_with_data_manager():
    manager = MarketDataManager()
    analyst = MarketAnalyst(data_manager=manager)
    assert analyst.data_manager is manager


def test_market_analyst_without_data_manager():
    analyst = MarketAnalyst()
    assert analyst.data_manager is None


def test_market_analyst_analyze_with_data_manager():
    manager = MarketDataManager()
    analyst = MarketAnalyst(data_manager=manager)
    result = asyncio.run(analyst.analyze("EURUSD", "1H"))
    assert result.analyst_name == "market"
    assert result.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= result.confidence <= 1.0
    assert result.data.get("data_source") == "pipeline"


def test_market_analyst_analyze_without_data_manager_uses_placeholder():
    analyst = MarketAnalyst()
    result = asyncio.run(analyst.analyze("EURUSD", "1H"))
    assert result.analyst_name == "market"
    assert result.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= result.confidence <= 1.0
    assert result.data.get("data_source") == "placeholder"


def test_market_analyst_with_mock_data_manager():
    mock_manager = AsyncMock(spec=MarketDataManager)
    candles = []
    base_price = 1.0890
    for i in range(100):
        candles.append(Candle(
            symbol="EURUSD",
            timeframe=Timeframe.ONE_HOUR,
            open=base_price + i * 0.0001,
            high=base_price + i * 0.0002,
            low=base_price + i * 0.00005,
            close=base_price + i * 0.00015,
            volume=10000 + i * 100,
            timestamp=datetime.utcnow()
        ))
    mock_manager.get_candles = AsyncMock(return_value=candles)

    analyst = MarketAnalyst(data_manager=mock_manager)
    result = asyncio.run(analyst.analyze("EURUSD", "1H"))
    assert result.analyst_name == "market"
    mock_manager.get_candles.assert_called_once_with("EURUSD", Timeframe.ONE_HOUR, 200)
