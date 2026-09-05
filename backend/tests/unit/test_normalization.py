import pytest
from datetime import datetime
from data.models import Candle, Quote, Tick, Timeframe


class TestDataNormalizer:
    """Tests for DataNormalizer that standardizes data across providers."""

    def test_normalize_polygon_candle(self):
        """Normalizer should convert Polygon OHLCV to Candle model."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        polygon_data = {
            "o": 150.0,
            "h": 155.0,
            "l": 148.0,
            "c": 153.0,
            "v": 1000000,
            "t": 1704067200000,  # 2024-01-01 00:00:00 UTC in ms
        }

        result = normalizer.normalize_candle(polygon_data, "AAPL", Timeframe.ONE_DAY, provider="polygon")

        assert isinstance(result, Candle)
        assert result.symbol == "AAPL"
        assert result.open == 150.0
        assert result.high == 155.0
        assert result.low == 148.0
        assert result.close == 153.0
        assert result.volume == 1000000

    def test_normalize_yfinance_candle(self):
        """Normalizer should convert yfinance data to Candle model."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        yf_data = {
            "Open": 150.0,
            "High": 155.0,
            "Low": 148.0,
            "Close": 153.0,
            "Volume": 1000000,
        }

        result = normalizer.normalize_candle(yf_data, "AAPL", Timeframe.ONE_DAY, provider="yfinance")

        assert isinstance(result, Candle)
        assert result.close == 153.0

    def test_normalize_akshare_candle(self):
        """Normalizer should convert AKShare data to Candle model."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        akshare_data = {
            "open": 150.0,
            "high": 155.0,
            "low": 148.0,
            "close": 153.0,
            "volume": 1000000,
            "datetime": datetime(2026, 1, 1),
        }

        result = normalizer.normalize_candle(akshare_data, "AAPL", Timeframe.ONE_DAY, provider="akshare")

        assert isinstance(result, Candle)
        assert result.open == 150.0

    def test_normalize_polygon_quote(self):
        """Normalizer should convert Polygon quote to Quote model."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        polygon_quote = {
            "bp": 1.1050,
            "ap": 1.1052,
            "bs": 1000000,
            "as": 1500000,
            "t": 1704067200000,
        }

        result = normalizer.normalize_quote(polygon_quote, "EURUSD", provider="polygon")

        assert isinstance(result, Quote)
        assert result.symbol == "EURUSD"
        assert result.bid == 1.1050
        assert result.ask == 1.1052
        assert result.spread == pytest.approx(0.0002, abs=1e-6)

    def test_normalize_polygon_tick(self):
        """Normalizer should convert Polygon tick to Tick model."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        polygon_tick = {
            "sym": "AAPL",
            "p": 153.5,
            "s": 100,
            "t": 1704067200000,
            "x": "NASDAQ",
        }

        result = normalizer.normalize_tick(polygon_tick, provider="polygon")

        assert isinstance(result, Tick)
        assert result.symbol == "AAPL"
        assert result.price == 153.5
        assert result.exchange == "NASDAQ"

    def test_normalize_batch_candles(self):
        """Normalizer should handle batch normalization of multiple candles."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        polygon_data = [
            {"o": 150.0, "h": 155.0, "l": 148.0, "c": 153.0, "v": 1000000, "t": 1704067200000},
            {"o": 153.0, "h": 157.0, "l": 151.0, "c": 156.0, "v": 1200000, "t": 1704153600000},
            {"o": 156.0, "h": 158.0, "l": 154.0, "c": 157.0, "v": 800000, "t": 1704240000000},
        ]

        results = normalizer.normalize_batch_candles(polygon_data, "AAPL", Timeframe.ONE_DAY, provider="polygon")

        assert len(results) == 3
        assert all(isinstance(c, Candle) for c in results)
        assert results[0].close == 153.0
        assert results[1].close == 156.0
        assert results[2].close == 157.0

    def test_normalize_unknown_provider_raises(self):
        """Normalizer should raise ValueError for unknown provider."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()

        with pytest.raises(ValueError, match="Unknown provider"):
            normalizer.normalize_candle({}, "AAPL", Timeframe.ONE_DAY, provider="unknown")

    def test_normalize_candle_validates_ohlc(self):
        """Normalizer should validate OHLC relationships after normalization."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        invalid_data = {
            "o": 150.0,
            "h": 145.0,  # high < open
            "l": 148.0,
            "c": 153.0,
            "v": 1000000,
            "t": 1704067200000,
        }

        with pytest.raises(ValueError):
            normalizer.normalize_candle(invalid_data, "AAPL", Timeframe.ONE_DAY, provider="polygon")

    def test_normalize_handles_missing_timestamp(self):
        """Normalizer should handle missing timestamp gracefully."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        data_no_ts = {
            "o": 150.0,
            "h": 155.0,
            "l": 148.0,
            "c": 153.0,
            "v": 1000000,
            # no "t" key
        }

        result = normalizer.normalize_candle(data_no_ts, "AAPL", Timeframe.ONE_DAY, provider="polygon")

        assert isinstance(result, Candle)
        assert result.timestamp is not None  # should use default

    def test_normalize_empty_batch_returns_empty_list(self):
        """Normalizer should handle empty batch gracefully."""
        from data.normalization import DataNormalizer

        normalizer = DataNormalizer()
        results = normalizer.normalize_batch_candles([], "AAPL", Timeframe.ONE_DAY, provider="polygon")
        assert results == []
