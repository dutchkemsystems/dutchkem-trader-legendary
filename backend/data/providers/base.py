from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from data.models import Candle, Quote, Tick, Timeframe


class BaseDataProvider(ABC):
    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 100
    ) -> list[Candle]:
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        ...

    @abstractmethod
    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        ...

    @abstractmethod
    async def connect_websocket(
        self, symbols: list[str], on_tick: Callable[[Tick], Any] | None = None
    ) -> None:
        ...

    @abstractmethod
    async def disconnect_websocket(self) -> None:
        ...
