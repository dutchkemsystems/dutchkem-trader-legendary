import os
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


# =============================================================================
# Base ABC Tests
# =============================================================================

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


# =============================================================================
# Polygon.io Provider Tests (Primary)
# =============================================================================

class TestPolygonProviderSymbolConversion:
    def test_forex_symbol_gets_c_prefix(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._convert_symbol("EURUSD") == "C:EURUSD"

    def test_equity_symbol_unchanged(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._convert_symbol("AAPL") == "AAPL"

    def test_forex_with_dot_gets_c_prefix(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._convert_symbol("EUR/USD") == "C:EURUSD"

    def test_already_prefixed_forex_not_double_prefixed(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._convert_symbol("C:EURUSD") == "C:EURUSD"


class TestPolygonProviderName:
    def test_name_is_polygon(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider.name == "polygon"

    def test_is_base_data_provider_subclass(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert isinstance(provider, BaseDataProvider)


class TestPolygonProviderRateLimiting:
    def test_rate_limiter_allows_burst_under_limit(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._rate_remaining == 5

    def test_rate_limiter_decrements_on_call(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        provider._consume_rate_limit()
        assert provider._rate_remaining == 4

    def test_rate_limiter_blocks_when_exhausted(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        for _ in range(5):
            provider._consume_rate_limit()
        assert provider._rate_remaining == 0
        assert provider._is_rate_limited() is True


class TestPolygonProviderGetCandles:
    @pytest.mark.asyncio
    async def test_returns_list_of_candles(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"o": 1.0890, "h": 1.0910, "l": 1.0880, "c": 1.0900, "v": 1000, "t": 1690000000000},
                {"o": 1.0900, "h": 1.0920, "l": 1.0890, "c": 1.0910, "v": 1200, "t": 1690000060000},
            ]
        }

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            candles = await provider.get_candles("EURUSD", Timeframe.ONE_HOUR, limit=2)

        assert len(candles) == 2
        assert all(isinstance(c, Candle) for c in candles)
        assert candles[0].symbol == "EURUSD"
        assert candles[0].open == 1.0890
        assert candles[1].close == 1.0910

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            candles = await provider.get_candles("EURUSD", Timeframe.ONE_DAY, limit=10)

        assert candles == []


class TestPolygonProviderGetQuote:
    @pytest.mark.asyncio
    async def test_returns_quote(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "lastTrade": {"p": 1.0900, "s": 100000, "x": "X", "t": 1690000000000},
            "lastQuote": {"bp": 1.0899, "ap": 1.0901, "bs": 500000, "as": 600000, "t": 1690000000000},
        }

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            quote = await provider.get_quote("EURUSD")

        assert isinstance(quote, Quote)
        assert quote.symbol == "EURUSD"
        assert quote.bid == 1.0899
        assert quote.ask == 1.0901
        assert quote.spread > 0


class TestPolygonProviderGetTicks:
    @pytest.mark.asyncio
    async def test_returns_ticks(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"p": 1.0900, "s": 100, "x": "X", "t": 1690000000000, "sym": "EURUSD"}]
        }

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            ticks = await provider.get_ticks("EURUSD", limit=10)

        assert len(ticks) == 1
        assert isinstance(ticks[0], Tick)
        assert ticks[0].price == 1.0900


class TestPolygonProviderApiKey:
    def test_api_key_stored(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="my_secret_key")
        assert provider._api_key == "my_secret_key"

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"POLYGON_API_KEY": "env_key"}):
            from data.providers.polygon import PolygonProvider
            provider = PolygonProvider()
            assert provider._api_key == "env_key"

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="POLYGON_API_KEY"):
                from data.providers.polygon import PolygonProvider
                PolygonProvider()


class TestPolygonProviderTimeframeMapping:
    def test_one_minute_maps_to_minute(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._timeframe_to_polygon(Timeframe.ONE_MINUTE) == "minute"

    def test_five_minutes_maps_to_minute(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._timeframe_to_polygon(Timeframe.FIVE_MINUTES) == "minute"

    def test_one_hour_maps_to_hour(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._timeframe_to_polygon(Timeframe.ONE_HOUR) == "hour"

    def test_one_day_maps_to_day(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._timeframe_to_polygon(Timeframe.ONE_DAY) == "day"

    def test_four_hours_maps_to_hour(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        assert provider._timeframe_to_polygon(Timeframe.FOUR_HOURS) == "hour"


class TestPolygonProviderWebsocket:
    @pytest.mark.asyncio
    async def test_connect_disconnect_does_not_raise(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")
        await provider.connect_websocket(["EURUSD"])
        await provider.disconnect_websocket()


class TestPolygonProviderErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        from data.providers.polygon import PolygonProvider
        provider = PolygonProvider(api_key="test_key")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "unauthorized"}
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(Exception, match="403"):
                await provider.get_candles("EURUSD", Timeframe.ONE_DAY)


# =============================================================================
# Finnhub Provider Tests (Backup #1, 60 req/min free)
# =============================================================================

class TestFinnhubProvider:
    def test_finnhub_is_base_data_provider_subclass(self):
        from data.providers.finnhub import FinnhubProvider
        assert issubclass(FinnhubProvider, BaseDataProvider)

    def test_finnhub_name_property(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        assert provider.name == "finnhub"

    def test_finnhub_requires_api_key(self):
        from data.providers.finnhub import FinnhubProvider
        with pytest.raises(ValueError, match="api_key"):
            FinnhubProvider(api_key="")

    def test_finnhub_stores_api_key(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="abc123")
        assert provider.api_key == "abc123"

    def test_finnhub_default_base_url(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="key")
        assert provider.base_url == "https://finnhub.io/api/v1"

    def test_finnhub_custom_base_url(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="key", base_url="https://custom.api/v1")
        assert provider.base_url == "https://custom.api/v1"

    def test_finnhub_timeframe_mapping(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="key")
        assert provider._timeframe_to_resolution(Timeframe.ONE_MINUTE) == "1"
        assert provider._timeframe_to_resolution(Timeframe.FIVE_MINUTES) == "5"
        assert provider._timeframe_to_resolution(Timeframe.FIFTEEN_MINUTES) == "15"
        assert provider._timeframe_to_resolution(Timeframe.ONE_HOUR) == "60"
        assert provider._timeframe_to_resolution(Timeframe.FOUR_HOURS) == "D"
        assert provider._timeframe_to_resolution(Timeframe.ONE_DAY) == "D"

    @pytest.mark.asyncio
    async def test_finnhub_get_candles(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        mock_response = {
            "s": "ok",
            "c": [150.0, 151.0, 152.0, 153.0, 154.0],
            "h": [152.0, 153.0, 154.0, 155.0, 156.0],
            "l": [149.0, 150.0, 151.0, 152.0, 153.0],
            "o": [149.5, 150.5, 151.5, 152.5, 153.5],
            "v": [1000000, 1100000, 1200000, 1300000, 1400000],
            "t": [1609459200, 1609545600, 1609632000, 1609718400, 1609804800],
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.closed = False
        mock_client.get = MagicMock(return_value=mock_resp)
        provider._client = mock_client

        candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=5)
        assert isinstance(candles, list)
        assert all(isinstance(c, Candle) for c in candles)
        assert all(c.symbol == "AAPL" for c in candles)
        assert all(c.timeframe == Timeframe.ONE_DAY for c in candles)

    @pytest.mark.asyncio
    async def test_finnhub_get_candles_with_mock(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        mock_response = {
            "s": "ok",
            "c": [150.0, 151.0, 152.0],
            "h": [152.0, 153.0, 154.0],
            "l": [149.0, 150.0, 151.0],
            "o": [149.5, 150.5, 151.5],
            "v": [1000000, 1100000, 1200000],
            "t": [1609459200, 1609545600, 1609632000],
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.closed = False
        mock_client.get = MagicMock(return_value=mock_resp)
        provider._client = mock_client

        candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=3)
        assert len(candles) == 3
        assert candles[0].open == 149.5
        assert candles[0].high == 152.0
        assert candles[0].low == 149.0
        assert candles[0].close == 150.0
        assert candles[0].volume == 1000000

    @pytest.mark.asyncio
    async def test_finnhub_get_candles_empty_response(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"s": "no_data"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.closed = False
        mock_client.get = MagicMock(return_value=mock_resp)
        provider._client = mock_client

        candles = await provider.get_candles("INVALID", Timeframe.ONE_DAY, limit=5)
        assert candles == []

    @pytest.mark.asyncio
    async def test_finnhub_get_quote(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "c": 150.0, "d": 1.5, "dp": 1.01, "h": 152.0, "l": 148.0,
            "o": 149.0, "pc": 148.5, "t": 1609459200,
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.closed = False
        mock_client.get = MagicMock(return_value=mock_resp)
        provider._client = mock_client

        quote = await provider.get_quote("AAPL")
        assert isinstance(quote, Quote)
        assert quote.symbol == "AAPL"
        assert quote.bid > 0
        assert quote.ask > 0
        assert quote.spread >= 0

    @pytest.mark.asyncio
    async def test_finnhub_get_ticks(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        ticks = await provider.get_ticks("AAPL", limit=10)
        assert isinstance(ticks, list)
        assert all(isinstance(t, Tick) for t in ticks)

    @pytest.mark.asyncio
    async def test_finnhub_connect_websocket(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        await provider.connect_websocket(["AAPL", "MSFT"])

    @pytest.mark.asyncio
    async def test_finnhub_disconnect_websocket(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        await provider.connect_websocket(["AAPL"])
        await provider.disconnect_websocket()

    @pytest.mark.asyncio
    async def test_finnhub_handles_http_error(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.text = AsyncMock(return_value="Rate limit exceeded")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.closed = False
        mock_client.get = MagicMock(return_value=mock_resp)
        provider._client = mock_client

        with pytest.raises(RuntimeError, match="rate limit|429"):
            await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=5)

    @pytest.mark.asyncio
    async def test_finnhub_rate_limiting(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="test_key")
        assert hasattr(provider, '_request_times')
        assert isinstance(provider._request_times, list)

    def test_finnhub_max_requests_per_minute(self):
        from data.providers.finnhub import FinnhubProvider
        provider = FinnhubProvider(api_key="key")
        assert provider._max_requests_per_minute == 60


# =============================================================================
# AKShare Provider Tests (Backup #2, Zero-Cost)
# =============================================================================

class TestAKShareProvider:
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


# =============================================================================
# FinanceDataReader Provider Tests (Backup #3)
# =============================================================================

class TestFinanceDataReaderProvider:
    def _make_provider(self):
        from data.providers.fdr_provider import FinanceDataReaderProvider
        return FinanceDataReaderProvider()

    def test_is_base_data_provider_subclass(self):
        from data.providers.fdr_provider import FinanceDataReaderProvider
        assert issubclass(FinanceDataReaderProvider, BaseDataProvider)

    def test_name_property(self):
        provider = self._make_provider()
        assert provider.name == "financedatareader"

    @pytest.mark.asyncio
    async def test_get_candles_returns_list_of_candle(self):
        import pandas as pd
        from data.providers.fdr_provider import FinanceDataReaderProvider

        fake_df = pd.DataFrame({
            "Open": [100.0, 101.0], "High": [102.0, 103.0],
            "Low": [99.0, 100.0], "Close": [101.0, 102.0], "Volume": [1000000, 1100000],
        }, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.return_value = fake_df
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=2)

        assert len(candles) == 2
        assert all(isinstance(c, Candle) for c in candles)
        assert candles[0].symbol == "AAPL"
        assert candles[0].open == 100.0

    @pytest.mark.asyncio
    async def test_get_candles_respects_limit(self):
        import pandas as pd
        from data.providers.fdr_provider import FinanceDataReaderProvider

        fake_df = pd.DataFrame({
            "Open": [100.0] * 10, "High": [102.0] * 10,
            "Low": [99.0] * 10, "Close": [101.0] * 10, "Volume": [1000000] * 10,
        }, index=pd.to_datetime([f"2024-01-{i+1:02d}" for i in range(10)]))

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.return_value = fake_df
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=5)

        assert len(candles) == 5

    @pytest.mark.asyncio
    async def test_get_candles_empty_df(self):
        import pandas as pd
        from data.providers.fdr_provider import FinanceDataReaderProvider

        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.return_value = empty_df
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=10)

        assert candles == []

    @pytest.mark.asyncio
    async def test_get_latest_price(self):
        import pandas as pd
        from data.providers.fdr_provider import FinanceDataReaderProvider

        fake_df = pd.DataFrame({
            "Open": [100.0], "High": [102.0], "Low": [99.0], "Close": [101.5], "Volume": [1000000],
        }, index=pd.to_datetime(["2024-01-02"]))

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.return_value = fake_df
            price = await provider.get_latest_price("AAPL")

        assert price == 101.5

    @pytest.mark.asyncio
    async def test_get_quote_returns_quote_from_latest(self):
        import pandas as pd
        from data.providers.fdr_provider import FinanceDataReaderProvider

        fake_df = pd.DataFrame({
            "Open": [100.0], "High": [102.0], "Low": [99.0], "Close": [101.5], "Volume": [1000000],
        }, index=pd.to_datetime(["2024-01-02"]))

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.return_value = fake_df
            quote = await provider.get_quote("AAPL")

        assert isinstance(quote, Quote)
        assert quote.symbol == "AAPL"
        assert quote.spread >= 0

    @pytest.mark.asyncio
    async def test_get_ticks_returns_empty_list(self):
        provider = self._make_provider()
        ticks = await provider.get_ticks("AAPL", limit=10)
        assert ticks == []

    @pytest.mark.asyncio
    async def test_connect_websocket_noop(self):
        provider = self._make_provider()
        await provider.connect_websocket(["AAPL"])

    @pytest.mark.asyncio
    async def test_disconnect_websocket_noop(self):
        provider = self._make_provider()
        await provider.disconnect_websocket()

    @pytest.mark.asyncio
    async def test_get_candles_fdr_error_propagates(self):
        from data.providers.fdr_provider import FinanceDataReaderProvider

        provider = self._make_provider()
        with patch("data.providers.fdr_provider.fdr") as mock_fdr:
            mock_fdr.DataReader.side_effect = Exception("Network error")
            with pytest.raises(Exception, match="Network error"):
                await provider.get_candles("INVALID", Timeframe.ONE_DAY, limit=10)


# =============================================================================
# OpenBB Provider Tests (Backup #4)
# =============================================================================

class TestOpenBBProvider:
    def test_openbb_provider_name(self):
        from data.providers.openbb_provider import OpenBBProvider
        provider = OpenBBProvider()
        assert provider.name == "openbb"

    def test_openbb_provider_is_base_subclass(self):
        from data.providers.openbb_provider import OpenBBProvider
        assert issubclass(OpenBBProvider, BaseDataProvider)

    def test_openbb_provider_requires_api_key(self):
        from data.providers.openbb_provider import OpenBBProvider
        provider = OpenBBProvider(api_key="test_key")
        assert provider.api_key == "test_key"

    @pytest.mark.asyncio
    async def test_openbb_get_candles(self):
        from data.providers.openbb_provider import OpenBBProvider

        mock_result = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__iter__ = MagicMock(return_value=iter([
            {"date": datetime(2024, 1, 1), "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 50000},
            {"date": datetime(2024, 1, 2), "open": 101.0, "high": 103.0, "low": 100.5, "close": 102.5, "volume": 60000},
        ]))
        mock_df.to_dict = MagicMock(return_value=[
            {"date": datetime(2024, 1, 1), "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 50000},
            {"date": datetime(2024, 1, 2), "open": 101.0, "high": 103.0, "low": 100.5, "close": 102.5, "volume": 60000},
        ])
        mock_result.value = mock_df

        with patch("data.providers.openbb_provider.openbb") as mock_openbb:
            mock_openbb.equity.price.historical = MagicMock(return_value=mock_result)

            provider = OpenBBProvider(api_key="test_key")
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=2)

            assert len(candles) == 2
            assert all(isinstance(c, Candle) for c in candles)
            assert candles[0].symbol == "AAPL"
            assert candles[0].open == 100.0
            assert candles[0].close == 101.0

    @pytest.mark.asyncio
    async def test_openbb_get_quote(self):
        from data.providers.openbb_provider import OpenBBProvider

        mock_quote = MagicMock()
        mock_quote.bid = 150.0
        mock_quote.ask = 150.05
        mock_quote.bid_size = 1000
        mock_quote.ask_size = 1000

        mock_result = MagicMock()
        mock_result.value = mock_quote

        with patch("data.providers.openbb_provider.openbb") as mock_openbb:
            mock_openbb.equity.price.quote = MagicMock(return_value=mock_result)

            provider = OpenBBProvider(api_key="test_key")
            quote = await provider.get_quote("AAPL")

            assert isinstance(quote, Quote)
            assert quote.symbol == "AAPL"
            assert quote.bid == 150.0
            assert quote.ask == 150.05
            assert quote.spread > 0

    @pytest.mark.asyncio
    async def test_openbb_get_ticks(self):
        from data.providers.openbb_provider import OpenBBProvider

        mock_result = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__iter__ = MagicMock(return_value=iter([{"price": 150.1, "size": 100, "exchange": "XNAS"}]))
        mock_df.to_dict = MagicMock(return_value=[{"price": 150.1, "size": 100, "exchange": "XNAS"}])
        mock_result.value = mock_df

        with patch("data.providers.openbb_provider.openbb") as mock_openbb:
            mock_openbb.equity.price.historical = MagicMock(return_value=mock_result)

            provider = OpenBBProvider(api_key="test_key")
            ticks = await provider.get_ticks("AAPL", limit=1)

            assert isinstance(ticks, list)
            assert all(isinstance(t, Tick) for t in ticks)

    @pytest.mark.asyncio
    async def test_openbb_connect_websocket(self):
        from data.providers.openbb_provider import OpenBBProvider
        provider = OpenBBProvider(api_key="test_key")
        await provider.connect_websocket(["AAPL", "MSFT"])
        assert provider._ws_connected is True

    @pytest.mark.asyncio
    async def test_openbb_disconnect_websocket(self):
        from data.providers.openbb_provider import OpenBBProvider
        provider = OpenBBProvider(api_key="test_key")
        await provider.connect_websocket(["AAPL"])
        await provider.disconnect_websocket()
        assert provider._ws_connected is False

    @pytest.mark.asyncio
    async def test_openbb_get_candles_handles_empty(self):
        from data.providers.openbb_provider import OpenBBProvider

        mock_result = MagicMock()
        mock_df = MagicMock()
        mock_df.empty = True
        mock_result.value = mock_df

        with patch("data.providers.openbb_provider.openbb") as mock_openbb:
            mock_openbb.equity.price.historical = MagicMock(return_value=mock_result)

            provider = OpenBBProvider(api_key="test_key")
            candles = await provider.get_candles("INVALID", Timeframe.ONE_DAY, limit=10)

            assert candles == []


# =============================================================================
# pandas-datareader Provider Tests (Backup #5)
# =============================================================================

class TestPandasDataReaderProvider:
    def test_pdr_provider_name(self):
        from data.providers.pdr_provider import PandasDataProvider
        provider = PandasDataProvider()
        assert provider.name == "pandas_datareader"

    def test_pdr_provider_is_base_subclass(self):
        from data.providers.pdr_provider import PandasDataProvider
        assert issubclass(PandasDataProvider, BaseDataProvider)

    def test_pdr_provider_default_source(self):
        from data.providers.pdr_provider import PandasDataProvider
        provider = PandasDataProvider()
        assert provider.data_source == "yahoo"

    def test_pdr_provider_custom_source(self):
        from data.providers.pdr_provider import PandasDataProvider
        provider = PandasDataProvider(data_source="fred")
        assert provider.data_source == "fred"

    @pytest.mark.asyncio
    async def test_pdr_get_candles(self):
        from data.providers.pdr_provider import PandasDataProvider
        import pandas as pd

        dates = pd.date_range("2024-01-01", periods=3)
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0],
            "High": [102.0, 103.0, 104.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [50000, 60000, 70000],
        }, index=dates)

        with patch("data.providers.pdr_provider.pdr") as mock_pdr:
            mock_pdr.DataReader = MagicMock(return_value=df)

            provider = PandasDataProvider(data_source="yahoo")
            candles = await provider.get_candles("AAPL", Timeframe.ONE_DAY, limit=3)

            assert len(candles) == 3
            assert all(isinstance(c, Candle) for c in candles)
            assert candles[0].symbol == "AAPL"
            assert candles[0].open == 100.0
            assert candles[0].close == 101.0
            assert candles[0].volume == 50000

    @pytest.mark.asyncio
    async def test_pdr_get_quote(self):
        from data.providers.pdr_provider import PandasDataProvider
        import pandas as pd

        df = pd.DataFrame({
            "Open": [149.0], "High": [151.0], "Low": [148.0], "Close": [150.0], "Volume": [100000],
        }, index=[datetime.now()])

        with patch("data.providers.pdr_provider.pdr") as mock_pdr:
            mock_pdr.DataReader = MagicMock(return_value=df)

            provider = PandasDataProvider(data_source="yahoo")
            quote = await provider.get_quote("AAPL")

            assert isinstance(quote, Quote)
            assert quote.symbol == "AAPL"
            assert quote.bid == 149.99
            assert quote.ask == 150.01
            assert quote.spread > 0

    @pytest.mark.asyncio
    async def test_pdr_get_ticks(self):
        from data.providers.pdr_provider import PandasDataProvider

        with patch("data.providers.pdr_provider.pdr") as mock_pdr:
            mock_pdr.DataReader = MagicMock(return_value=MagicMock(empty=True))

            provider = PandasDataProvider(data_source="yahoo")
            ticks = await provider.get_ticks("AAPL", limit=10)

            assert isinstance(ticks, list)

    @pytest.mark.asyncio
    async def test_pdr_connect_websocket(self):
        from data.providers.pdr_provider import PandasDataProvider
        provider = PandasDataProvider()
        await provider.connect_websocket(["AAPL"])
        assert provider._ws_connected is True

    @pytest.mark.asyncio
    async def test_pdr_disconnect_websocket(self):
        from data.providers.pdr_provider import PandasDataProvider
        provider = PandasDataProvider()
        await provider.connect_websocket(["AAPL"])
        await provider.disconnect_websocket()
        assert provider._ws_connected is False

    @pytest.mark.asyncio
    async def test_pdr_get_candles_handles_empty(self):
        from data.providers.pdr_provider import PandasDataProvider
        import pandas as pd

        empty_df = pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"],
            index=pd.DatetimeIndex([], name="Date"),
        )

        with patch("data.providers.pdr_provider.pdr") as mock_pdr:
            mock_pdr.DataReader = MagicMock(return_value=empty_df)

            provider = PandasDataProvider(data_source="yahoo")
            candles = await provider.get_candles("INVALID", Timeframe.ONE_DAY, limit=10)

            assert candles == []


# =============================================================================
# ProviderRegistry Tests (6-tier fallback)
# =============================================================================

class TestProviderRegistry:
    def test_registry_instantiation(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        assert registry.providers == []

    def test_register_single_provider(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        provider = ConcreteProvider()
        registry.register(provider)
        assert len(registry.providers) == 1
        assert registry.providers[0] is provider

    def test_register_multiple_providers_appends_in_order(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        p1 = ConcreteProvider()
        p1.name = "alpha"
        p2 = ConcreteProvider()
        p2.name = "beta"
        registry.register(p1)
        registry.register(p2)
        assert registry.providers[0].name == "alpha"
        assert registry.providers[1].name == "beta"

    def test_register_with_priority_inserts_at_position(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        p1 = ConcreteProvider()
        p1.name = "first"
        p2 = ConcreteProvider()
        p2.name = "second"
        registry.register(p1)
        registry.register(p2, priority=0)
        assert len(registry.providers) == 2
        assert registry.providers[0].name == "second"
        assert registry.providers[1].name == "first"

    @pytest.mark.asyncio
    async def test_get_candles_tries_first_provider(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        provider = ConcreteProvider()
        registry.register(provider)
        candles = await registry.get_candles("EURUSD", Timeframe.ONE_HOUR, limit=10)
        assert len(candles) == 1
        assert isinstance(candles[0], Candle)
        assert candles[0].symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_candles_falls_back_on_first_failure(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        failing = MagicMock(spec=BaseDataProvider)
        failing.name = "failing"
        failing.get_candles = AsyncMock(side_effect=Exception("provider down"))

        working = ConcreteProvider()
        registry.register(failing)
        registry.register(working)

        candles = await registry.get_candles("EURUSD", Timeframe.ONE_HOUR, limit=10)
        assert len(candles) == 1
        assert candles[0].symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_candles_raises_when_all_providers_fail(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        f1 = MagicMock(spec=BaseDataProvider)
        f1.name = "fail1"
        f1.get_candles = AsyncMock(side_effect=Exception("error1"))

        f2 = MagicMock(spec=BaseDataProvider)
        f2.name = "fail2"
        f2.get_candles = AsyncMock(side_effect=Exception("error2"))

        registry.register(f1)
        registry.register(f2)

        with pytest.raises(RuntimeError, match="All providers failed"):
            await registry.get_candles("EURUSD", Timeframe.ONE_HOUR, limit=10)

    @pytest.mark.asyncio
    async def test_get_quote_falls_back(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        failing = MagicMock(spec=BaseDataProvider)
        failing.name = "failing"
        failing.get_quote = AsyncMock(side_effect=Exception("down"))

        working = ConcreteProvider()
        registry.register(failing)
        registry.register(working)

        quote = await registry.get_quote("EURUSD")
        assert isinstance(quote, Quote)
        assert quote.symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_quote_raises_when_all_fail(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        f1 = MagicMock(spec=BaseDataProvider)
        f1.name = "f1"
        f1.get_quote = AsyncMock(side_effect=Exception("e1"))

        registry.register(f1)

        with pytest.raises(RuntimeError, match="All providers failed"):
            await registry.get_quote("EURUSD")

    @pytest.mark.asyncio
    async def test_get_ticks_falls_back(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        failing = MagicMock(spec=BaseDataProvider)
        failing.name = "failing"
        failing.get_ticks = AsyncMock(side_effect=Exception("down"))

        working = ConcreteProvider()
        registry.register(failing)
        registry.register(working)

        ticks = await registry.get_ticks("EURUSD", limit=10)
        assert len(ticks) == 1
        assert isinstance(ticks[0], Tick)

    @pytest.mark.asyncio
    async def test_get_latest_price_falls_back(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()

        failing = MagicMock(spec=BaseDataProvider)
        failing.name = "failing"
        failing.get_latest_price = AsyncMock(side_effect=Exception("down"))

        working = ConcreteProvider()
        registry.register(failing)
        registry.register(working)

        price = await registry.get_latest_price("EURUSD")
        assert isinstance(price, float)
        assert price > 0

    @pytest.mark.asyncio
    async def test_connect_websocket_delegates(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        provider = ConcreteProvider()
        registry.register(provider)
        await registry.connect_websocket(["EURUSD"])

    @pytest.mark.asyncio
    async def test_disconnect_websocket_delegates(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        provider = ConcreteProvider()
        registry.register(provider)
        await registry.disconnect_websocket()

    def test_create_default_returns_registry(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry.create_default()
        assert isinstance(registry, ProviderRegistry)
        assert len(registry.providers) > 0

    def test_create_default_provider_names(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry.create_default()
        names = [p.name for p in registry.providers]
        assert len(names) >= 1

    def test_create_default_provider_is_base_subclass(self):
        from data.providers.registry import ProviderRegistry
        registry = ProviderRegistry.create_default()
        for provider in registry.providers:
            assert isinstance(provider, BaseDataProvider)
