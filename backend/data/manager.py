from __future__ import annotations

import logging

from data.models import Candle, Quote, Timeframe
from data.providers import StubProvider
from data.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class MarketDataManager:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()
        self.registry.register(StubProvider())

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        return await self.registry.get_candles(symbol, timeframe, limit)

    async def get_latest_price(self, symbol: str) -> float:
        return await self.registry.get_latest_price(symbol)

    async def get_quote(self, symbol: str) -> Quote:
        return await self.registry.get_quote(symbol)
