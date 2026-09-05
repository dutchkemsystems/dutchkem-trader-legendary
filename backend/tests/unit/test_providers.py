import pytest
from abc import ABC
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from data.models import Candle, Tick, Quote, Timeframe
from data.providers import BaseDataProvider


class ConcreteProvider(BaseDataProvider):
    """Minimal concrete implementation for testing ABC behavior."""

    name: str = "concrete"

    async def get_candles(self, symbol: str, timeframe: Timeframe, limit: int = 100) -> list[Candle]:
        return [
            Candle(
                symbol=symbol, timeframe=timeframe,
                open=100.0, high=101.0, low=99.5, close=100.5,
                volume=1000, timestamp=datetime.utcnow()
            )
        ]

    async def get_latest_price(self, symbol: str) -> float:
        return 100.5

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


# ─── AKShare Provider Tests ───────────────────────────────────────────────────

class TestAKShareProvider:
    """Tests for AKShare zero-cost backup provider."""

    def test_akshare_is_base_data_provider_subclass(self):
        from data.providers.akshare_provider import AKShareProvider
        assert issubclass(AKShareProvider, BaseDataProvider)

    def test_akshare_name(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        assert provider.name == "akshare"

    def test_akshare_instantiation_no_api_key(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        assert provider is not None

    @pytest.mark.asyncio
    async def test_akshare_get_candles_forex(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=5)
        mock_df.iterrows = MagicMock(return_value=iter([
            (0, {"Open": 1.0890, "High": 1.0910, "Low": 1.0870, "Close": 1.0900, "Volume": 100000, "Datetime": datetime(2024, 1, 1)}),
            (1, {"Open": 1.0900, "High": 1.0920, "Low": 1.0880, "Close": 1.0910, "Volume": 110000, "Datetime": datetime(2024, 1, 2)}),
            (2, {"Open": 1.0910, "High": 1.0930, "Low": 1.0890, "Close": 1.0920, "Volume": 120000, "Datetime": datetime(2024, 1, 3)}),
            (3, {"Open": 1.0920, "High": 1.0940, "Low": 1.0900, "Close": 1.0930, "Volume": 130000, "Datetime": datetime(2024, 1, 4)}),
            (4, {"Open": 1.0930, "High": 1.0950, "Low": 1.0910, "Close": 1.0940, "Volume": 140000, "Datetime": datetime(2024, 1, 5)}),
        ]))
        mock_df.iloc = MagicMock()
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_df)

        with patch("data.providers.akshare_provider.akshare") as mock_ak:
            mock_ak.forex_hist_sina = MagicMock(return_value=mock_df)
            candles = await provider.get_candles("EURUSD", Timeframe.ONE_DAY, limit=5)
            assert len(candles) == 5
            assert all(isinstance(c, Candle) for c in candles)
            assert candles[0].symbol == "EURUSD"
            assert candles[0].timeframe == Timeframe.ONE_DAY

    @pytest.mark.asyncio
    async def test_akshare_get_candles_equity(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=3)
        mock_df.iterrows = MagicMock(return_value=iter([
            (0, {"Open": 150.0, "High": 152.0, "Low": 149.0, "Close": 151.0, "Volume": 5000000, "Datetime": datetime(2024, 1, 1)}),
            (1, {"Open": 151.0, "High": 153.0, "Low": 150.0, "Close": 152.0, "Volume": 6000000, "Datetime": datetime(2024, 1, 2)}),
            (2, {"Open": 152.0, "High": 154.0, "Low": 151.0, "Close": 153.0, "Volume": 7000000, "Datetime": datetime(2024, 1, 3)}),
        ]))

        with patch("data.providers.akshare_provider.akshare") as mock_ak:
            mock_ak.stock_zh_a_hist = MagicMock(return_value=mock_df)
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=3)
            assert len(candles) == 3
            assert all(isinstance(c, Candle) for c in candles)
            assert candles[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_akshare_get_latest_price(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=1)
        mock_df.iterrows = MagicMock(return_value=iter([
            (0, {"Open": 1.0890, "High": 1.0910, "Low": 1.0870, "Close": 1.0900, "Volume": 100000, "Datetime": datetime(2024, 1, 1)}),
        ]))

        with patch("data.providers.akshare_provider.akshare") as mock_ak:
            mock_ak.forex_hist_sina = MagicMock(return_value=mock_df)
            price = await provider.get_latest_price("EURUSD")
            assert isinstance(price, float)
            assert price > 0

    @pytest.mark.asyncio
    async def test_akshare_get_quote(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()

        mock_row = MagicMock()
        mock_row.get = MagicMock(side_effect=lambda k, d=0: {"买入价": 1.0890, "卖出价": 1.0892}[k])

        mock_filtered = MagicMock()
        mock_filtered.__len__ = MagicMock(return_value=1)
        mock_filtered.iloc = MagicMock()
        mock_filtered.iloc.__getitem__ = MagicMock(return_value=mock_row)

        mock_spot = MagicMock()
        mock_spot.__getitem__ = MagicMock(return_value=mock_filtered)

        with patch("data.providers.akshare_provider.akshare") as mock_ak:
            mock_ak.forex_spot = MagicMock(return_value=mock_spot)
            quote = await provider.get_quote("EURUSD")
            assert isinstance(quote, Quote)
            assert quote.symbol == "EURUSD"
            assert quote.bid > 0
            assert quote.ask > quote.bid

    @pytest.mark.asyncio
    async def test_akshare_get_ticks(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        ticks = await provider.get_ticks("EURUSD", limit=10)
        assert isinstance(ticks, list)
        assert len(ticks) == 0

    @pytest.mark.asyncio
    async def test_akshare_connect_websocket_noop(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        await provider.connect_websocket(["EURUSD"])

    @pytest.mark.asyncio
    async def test_akshare_disconnect_websocket_noop(self):
        from data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        await provider.disconnect_websocket()
