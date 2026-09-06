from __future__ import annotations

import logging
from typing import Optional

from data.models import Candle, Quote, Tick, Timeframe
from data.cache import DataCache
from data.normalization import DataNormalizer
from data.providers import StubProvider
from data.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class MarketDataManager:
    """Orchestrates data providers with caching and normalization."""

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        cache: Optional[DataCache] = None,
        normalizer: Optional[DataNormalizer] = None,
    ) -> None:
        self.registry = registry or ProviderRegistry()
        if not registry:
            self.registry.register(StubProvider())
        self.cache = cache or DataCache()
        self.normalizer = normalizer or DataNormalizer()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        cache_key_tf = timeframe.value
        cached = self.cache.get_candle(symbol, cache_key_tf)
        if cached is not None:
            logger.debug("Cache hit for candles %s %s", symbol, cache_key_tf)
            return [cached]

        candles = await self.registry.get_candles(symbol, timeframe, limit)
        if candles:
            self.cache.set_candle(symbol, cache_key_tf, candles[-1])
        return candles

    async def get_quote(self, symbol: str) -> Quote:
        cached = self.cache.get_quote(symbol)
        if cached is not None:
            logger.debug("Cache hit for quote %s", symbol)
            return cached

        quote = await self.registry.get_quote(symbol)
        self.cache.set_quote(symbol, quote)
        return quote

    async def get_latest_price(self, symbol: str) -> float:
        return await self.registry.get_latest_price(symbol)

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        errors: list[str] = []
        for provider in self.registry.providers:
            try:
                return await provider.get_ticks(symbol, limit)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed on get_ticks: %s", provider.name, e)
        return []
