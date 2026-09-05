from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable

from data.models import Candle, Quote, Tick, Timeframe


class BaseDataProvider(ABC):
    """Abstract base class for all data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        pass

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        pass

    @abstractmethod
    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        pass

    @abstractmethod
    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        pass

    @abstractmethod
    async def disconnect_websocket(self) -> None:
        pass


class StubProvider(BaseDataProvider):
    """Stub provider that returns fake data for testing."""

    name: str = "stub"

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        candles: list[Candle] = []
        base_price = 100.0
        for i in range(limit):
            o = base_price + i * 0.1
            h = o + 0.5
            l = o - 0.3
            c = o + 0.2
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=10000 + i * 100,
                    timestamp=datetime.utcnow(),
                )
            )
        return candles

    async def get_latest_price(self, symbol: str) -> float:
        return 109.5

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            bid=109.4,
            ask=109.6,
            bid_size=100000,
            ask_size=100000,
            timestamp=datetime.utcnow(),
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        return []

    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        pass

    async def disconnect_websocket(self) -> None:
        pass
