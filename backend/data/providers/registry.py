from __future__ import annotations

import logging
from typing import Any, Callable

from data.models import Candle, Quote, Tick, Timeframe
from data.providers import BaseDataProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry with priority-ordered provider fallback chain.

    Providers are tried in registration order (lowest index first).
    If a provider raises an exception, the next provider is tried.
    If all providers fail, a RuntimeError is raised.
    """

    def __init__(self) -> None:
        self._providers: list[BaseDataProvider] = []

    @property
    def providers(self) -> list[BaseDataProvider]:
        return list(self._providers)

    def register(self, provider: BaseDataProvider, priority: int | None = None) -> None:
        if priority is not None:
            self._providers.insert(priority, provider)
        else:
            self._providers.append(provider)
        logger.info("Registered provider: %s (priority=%s)", provider.name, priority)

    @classmethod
    def create_default(cls) -> ProviderRegistry:
        """Create a registry with the 6-tier fallback chain:
        Polygon -> Finnhub -> AKShare -> FDR -> OpenBB -> PDR

        Providers that cannot be instantiated (missing API keys / dependencies)
        are silently skipped.
        """
        registry = cls()

        tiers: list[tuple[int, str, type[BaseDataProvider], dict[str, Any]]] = [
            (0, "polygon", None, {}),
            (1, "finnhub", None, {}),
            (2, "akshare", None, {}),
            (3, "financedatareader", None, {}),
            (4, "openbb", None, {}),
            (5, "pandas_datareader", None, {}),
        ]

        provider_map: dict[str, tuple[str, str]] = {
            "polygon": ("data.providers.polygon", "PolygonProvider"),
            "finnhub": ("data.providers.finnhub", "FinnhubProvider"),
            "akshare": ("data.providers.akshare_provider", "AKShareProvider"),
            "financedatareader": ("data.providers.fdr_provider", "FinanceDataReaderProvider"),
            "openbb": ("data.providers.openbb_provider", "OpenBBProvider"),
            "pandas_datareader": ("data.providers.pdr_provider", "PandasDataProvider"),
        }

        for priority, name, _cls, kwargs in tiers:
            try:
                module_path, class_name = provider_map[name]
                import importlib
                module = importlib.import_module(module_path)
                provider_cls = getattr(module, class_name)
                registry.register(provider_cls(**kwargs), priority=priority)
                logger.info("Loaded tier %d provider: %s", priority, name)
            except Exception as e:
                logger.debug("Skipping provider %s: %s", name, e)

        return registry

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        errors: list[str] = []
        for provider in self._providers:
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
        for provider in self._providers:
            try:
                return await provider.get_latest_price(symbol)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    async def get_quote(self, symbol: str) -> Quote:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.get_quote(symbol)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.get_ticks(symbol, limit)
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                logger.warning("Provider %s failed: %s", provider.name, e)
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        for provider in self._providers:
            try:
                await provider.connect_websocket(symbols, on_tick)
                return
            except Exception as e:
                logger.warning("Provider %s connect_websocket failed: %s", provider.name, e)
        raise RuntimeError("All providers failed to connect websocket")

    async def disconnect_websocket(self) -> None:
        for provider in self._providers:
            try:
                await provider.disconnect_websocket()
                return
            except Exception as e:
                logger.warning("Provider %s disconnect_websocket failed: %s", provider.name, e)
        raise RuntimeError("All providers failed to disconnect websocket")
