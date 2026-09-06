from unittest.mock import AsyncMock, patch
import pytest

from data.models import Candle, Quote, Timeframe


class TestFetchCandlesTask:
    def test_returns_list_of_candle_dicts(self):
        from tasks.data_tasks import fetch_candles_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            candles = [
                Candle(
                    symbol="AAPL", timeframe=Timeframe.ONE_DAY,
                    open=150, high=155, low=148, close=153,
                    volume=5000000, timestamp="2025-01-01",
                ),
            ]
            manager.get_candles.return_value = candles
            mock_get.return_value = manager

            result = fetch_candles_task("AAPL", "1D", 10)

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["symbol"] == "AAPL"
            assert result[0]["open"] == 150

    def test_returns_empty_list_on_no_data(self):
        from tasks.data_tasks import fetch_candles_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            manager.get_candles.return_value = []
            mock_get.return_value = manager

            result = fetch_candles_task("INVALID", "1D", 10)

            assert result == []

    def test_returns_error_dict_on_failure(self):
        from tasks.data_tasks import fetch_candles_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            manager.get_candles.side_effect = RuntimeError("All providers failed")
            mock_get.return_value = manager

            result = fetch_candles_task("AAPL", "1D", 10)

            assert "error" in result
            assert "All providers failed" in result["error"]


class TestFetchQuoteTask:
    def test_returns_quote_dict(self):
        from tasks.data_tasks import fetch_quote_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            quote = Quote(
                symbol="AAPL", bid=150.0, ask=150.5,
                bid_size=1000, ask_size=2000, timestamp="2025-01-01",
            )
            manager.get_quote.return_value = quote
            mock_get.return_value = manager

            result = fetch_quote_task("AAPL")

            assert isinstance(result, dict)
            assert result["symbol"] == "AAPL"
            assert result["bid"] == 150.0
            assert result["ask"] == 150.5

    def test_returns_error_dict_on_failure(self):
        from tasks.data_tasks import fetch_quote_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            manager.get_quote.side_effect = RuntimeError("No providers available")
            mock_get.return_value = manager

            result = fetch_quote_task("AAPL")

            assert "error" in result
            assert "No providers available" in result["error"]


class TestFetchLatestPriceTask:
    def test_returns_price_float(self):
        from tasks.data_tasks import fetch_latest_price_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            manager.get_latest_price.return_value = 150.25
            mock_get.return_value = manager

            result = fetch_latest_price_task("AAPL")

            assert result == 150.25

    def test_returns_error_dict_on_failure(self):
        from tasks.data_tasks import fetch_latest_price_task

        with patch("tasks.data_tasks._get_manager") as mock_get:
            manager = AsyncMock()
            manager.get_latest_price.side_effect = RuntimeError("fail")
            mock_get.return_value = manager

            result = fetch_latest_price_task("AAPL")

            assert "error" in result
