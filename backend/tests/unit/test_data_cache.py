import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from dataclasses import asdict
from data.models import Candle, Quote, Tick, Timeframe


class TestDataCache:
    """Tests for DataCache with TTL-based caching."""

    def test_cache_candle_with_ttl(self):
        """Candles should be cached with 300s TTL."""
        from data.cache import DataCache

        cache = DataCache()
        candle = Candle(
            symbol="AAPL",
            timeframe=Timeframe.ONE_DAY,
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
            timestamp=datetime(2026, 1, 1),
        )

        cache.set_candle("AAPL", "1D", candle)
        result = cache.get_candle("AAPL", "1D")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.close == 153.0

    def test_cache_candle_ttl_value(self):
        """Candle cache TTL should be 300 seconds."""
        from data.cache import CANDLE_TTL

        assert CANDLE_TTL == 300

    def test_cache_quote_with_ttl(self):
        """Quotes should be cached with 10s TTL."""
        from data.cache import DataCache

        cache = DataCache()
        quote = Quote(
            symbol="EURUSD",
            bid=1.1050,
            ask=1.1052,
            bid_size=1000000,
            ask_size=1500000,
            timestamp=datetime(2026, 1, 1),
        )

        cache.set_quote("EURUSD", quote)
        result = cache.get_quote("EURUSD")

        assert result is not None
        assert result.symbol == "EURUSD"
        assert result.spread == pytest.approx(0.0002, abs=1e-6)

    def test_cache_quote_ttl_value(self):
        """Quote cache TTL should be 10 seconds."""
        from data.cache import QUOTE_TTL

        assert QUOTE_TTL == 10

    def test_cache_returns_none_for_missing_key(self):
        """Cache should return None for missing keys."""
        from data.cache import DataCache

        cache = DataCache()
        result = cache.get_candle("NONEXIST", "1D")
        assert result is None

    def test_cache_delete_candle(self):
        """Cache should support deleting candle entries."""
        from data.cache import DataCache

        cache = DataCache()
        candle = Candle(
            symbol="AAPL",
            timeframe=Timeframe.ONE_DAY,
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
            timestamp=datetime(2026, 1, 1),
        )

        cache.set_candle("AAPL", "1D", candle)
        cache.delete_candle("AAPL", "1D")
        result = cache.get_candle("AAPL", "1D")
        assert result is None

    def test_cache_ttl_provides_type_constants(self):
        """Cache module should export TTL constants for data types."""
        from data import cache as cache_module

        assert hasattr(cache_module, 'CANDLE_TTL')
        assert hasattr(cache_module, 'QUOTE_TTL')
        assert hasattr(cache_module, 'TICK_TTL')

    def test_cache_tick_with_ttl(self):
        """Ticks should be cached with appropriate TTL."""
        from data.cache import DataCache, TICK_TTL

        assert TICK_TTL > 0
        cache = DataCache()
        tick = Tick(
            symbol="AAPL",
            price=153.5,
            size=100,
            timestamp=datetime(2026, 1, 1),
        )

        cache.set_tick("AAPL", tick)
        result = cache.get_tick("AAPL")

        assert result is not None
        assert result.price == 153.5

    def test_cache_multiple_candles_per_symbol(self):
        """Cache should store multiple candles per symbol with different timeframes."""
        from data.cache import DataCache

        cache = DataCache()
        candle_1d = Candle(
            symbol="AAPL",
            timeframe=Timeframe.ONE_DAY,
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1000000,
            timestamp=datetime(2026, 1, 1),
        )
        candle_1h = Candle(
            symbol="AAPL",
            timeframe=Timeframe.ONE_HOUR,
            open=151.0,
            high=152.0,
            low=150.0,
            close=151.5,
            volume=500000,
            timestamp=datetime(2026, 1, 1, 10),
        )

        cache.set_candle("AAPL", "1D", candle_1d)
        cache.set_candle("AAPL", "1H", candle_1h)

        assert cache.get_candle("AAPL", "1D") is not None
        assert cache.get_candle("AAPL", "1H") is not None
        assert cache.get_candle("AAPL", "1D").close == 153.0
        assert cache.get_candle("AAPL", "1H").close == 151.5
