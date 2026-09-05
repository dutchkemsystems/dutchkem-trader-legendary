from __future__ import annotations

import logging
from typing import Any

from data.models import Candle, Quote, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: list[BaseDataProvider] = []

    def register(self, provider: BaseDataProvider) -> None:
        self.providers.append(provider)
        logger.info("Registered provider: %s", provider.name)

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = await provider.get_candles(symbol, timeframe, limit)
                logger.info("Provider %s returned %d candles", provider.name, len(result))
                return result
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    async def get_latest_price(self, symbol: str) -> float:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.get_latest_price(symbol)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    async def get_quote(self, symbol: str) -> Quote:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.get_quote(symbol)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")
