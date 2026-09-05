import pytest
from abc import ABC
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from data.models import Candle, Tick, Quote, Timeframe
from data.providers.base import BaseDataProvider


class ConcreteProvider(BaseDataProvider):
    """Minimal concrete implementation for testing ABC behavior."""

    async def get_candles(self, symbol: str, timeframe: Timeframe, limit: int = 100) -> list[Candle]:
        return [
            Candle(
                symbol=symbol, timeframe=timeframe,
                open=100.0, high=101.0, low=99.5, close=100.5,
                volume=1000, timestamp=datetime.utcnow()
            )
        ]

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol, bid=1.0890, ask=1.0892,
            bid_size=1000000, ask_size=1000000,
            timestamp=datetime.utcnow()
        )

    async def get_ticks(self, symbol: str, limit: int = 100) -> list[Tick]:
        return [
            Tick(
                symbol=symbol, price=100.5, size=100,
                timestamp=datetime.utcnow(), exchange="TEST"
            )
        ]

    async def connect_websocket(self, symbols: list[str], on_tick=None) -> None:
        pass

    async def disconnect_websocket(self) -> None:
        pass


def test_base_data_provider_is_abstract():
    with pytest.raises(TypeError):
        BaseDataProvider()


def test_base_data_provider_has_required_methods():
    assert hasattr(BaseDataProvider, "get_candles")
    assert hasattr(BaseDataProvider, "get_quote")
    assert hasattr(BaseDataProvider, "get_ticks")
    assert hasattr(BaseDataProvider, "connect_websocket")
    assert hasattr(BaseDataProvider, "disconnect_websocket")


def test_base_data_provider_is_abc_subclass():
    assert issubclass(BaseDataProvider, ABC)


def test_concrete_provider_instantiation():
    provider = ConcreteProvider()
    assert isinstance(provider, BaseDataProvider)


@pytest.mark.asyncio
async def test_concrete_get_candles():
    provider = ConcreteProvider()
    candles = await provider.get_candles("EURUSD", Timeframe.ONE_HOUR, limit=10)
    assert len(candles) == 1
    assert isinstance(candles[0], Candle)
    assert candles[0].symbol == "EURUSD"


@pytest.mark.asyncio
async def test_concrete_get_quote():
    provider = ConcreteProvider()
    quote = await provider.get_quote("EURUSD")
    assert isinstance(quote, Quote)
    assert quote.symbol == "EURUSD"
    assert quote.spread > 0


@pytest.mark.asyncio
async def test_concrete_get_ticks():
    provider = ConcreteProvider()
    ticks = await provider.get_ticks("EURUSD", limit=10)
    assert len(ticks) == 1
    assert isinstance(ticks[0], Tick)
    assert ticks[0].symbol == "EURUSD"


@pytest.mark.asyncio
async def test_concrete_connect_disconnect_websocket():
    provider = ConcreteProvider()
    await provider.connect_websocket(["EURUSD"])
    await provider.disconnect_websocket()
