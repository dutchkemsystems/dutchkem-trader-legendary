import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from data.models import Candle, Quote, Timeframe
from data.cache import DataCache
from data.normalization import DataNormalizer
from data.providers import BaseDataProvider, StubProvider
from data.registry import ProviderRegistry
from data.manager import MarketDataManager


class TestMarketDataManagerInit:
    def test_creates_with_default_registry(self):
        mgr = MarketDataManager()
        assert mgr.registry is not None
        assert len(mgr.registry.providers) > 0

    def test_creates_with_custom_cache(self):
        cache = DataCache()
        mgr = MarketDataManager(cache=cache)
        assert mgr.cache is cache

    def test_creates_with_custom_normalizer(self):
        norm = DataNormalizer()
        mgr = MarketDataManager(normalizer=norm)
        assert mgr.normalizer is norm


class TestMarketDataManagerCandles:
    @pytest.mark.asyncio
    async def test_get_candles_returns_list(self):
        mgr = MarketDataManager()
        candles = await mgr.get_candles("AAPL", Timeframe.ONE_DAY, 5)
        assert isinstance(candles, list)
        assert len(candles) == 5
        assert all(isinstance(c, Candle) for c in candles)

    @pytest.mark.asyncio
    async def test_get_candles_populates_cache(self):
        cache = DataCache()
        mgr = MarketDataManager(cache=cache)

        candles = await mgr.get_candles("AAPL", Timeframe.ONE_DAY, 5)
        assert len(candles) == 5

        cached = cache.get_candle("AAPL", Timeframe.ONE_DAY.value)
        assert cached is not None
        assert cached.symbol == "AAPL"
        assert cached.close == candles[-1].close

    @pytest.mark.asyncio
    async def test_get_candles_falls_back_on_provider_failure(self):
        mgr = MarketDataManager()
        failing = AsyncMock(spec=BaseDataProvider)
        failing.name = "failing"
        failing.get_candles = AsyncMock(side_effect=RuntimeError("fail"))
        mgr.registry.providers.insert(0, failing)

        candles = await mgr.get_candles("AAPL", Timeframe.ONE_DAY, 5)
        assert len(candles) > 0


class TestMarketDataManagerQuote:
    @pytest.mark.asyncio
    async def test_get_quote_returns_quote(self):
        mgr = MarketDataManager()
        quote = await mgr.get_quote("AAPL")
        assert isinstance(quote, Quote)
        assert quote.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_quote_uses_cache(self):
        cache = DataCache()
        mgr = MarketDataManager(cache=cache)

        q1 = await mgr.get_quote("AAPL")
        q2 = await mgr.get_quote("AAPL")

        assert q1.bid == q2.bid
        assert q1.ask == q2.ask


class TestMarketDataManagerPrice:
    @pytest.mark.asyncio
    async def test_get_latest_price_returns_float(self):
        mgr = MarketDataManager()
        price = await mgr.get_latest_price("AAPL")
        assert isinstance(price, float)
        assert price > 0


class TestMarketDataManagerTicks:
    @pytest.mark.asyncio
    async def test_get_ticks_returns_list(self):
        mgr = MarketDataManager()
        ticks = await mgr.get_ticks("AAPL", 10)
        assert isinstance(ticks, list)


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_candle_fetch_cache_roundtrip(self):
        cache = DataCache()
        mgr = MarketDataManager(cache=cache)

        candles = await mgr.get_candles("AAPL", Timeframe.ONE_DAY, 3)
        assert len(candles) == 3

        cached = cache.get_candle("AAPL", Timeframe.ONE_DAY.value)
        assert cached is not None

    @pytest.mark.asyncio
    async def test_quote_fetch_cache_roundtrip(self):
        cache = DataCache()
        mgr = MarketDataManager(cache=cache)

        quote = await mgr.get_quote("AAPL")
        cached = cache.get_quote("AAPL")
        assert cached is not None
        assert cached.symbol == quote.symbol
