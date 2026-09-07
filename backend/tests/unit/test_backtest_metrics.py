"""Tests for backtesting performance metrics."""
import pytest
from decimal import Decimal
from backtesting.metrics import PerformanceMetrics, TradeRecord


class TestPerformanceMetrics:
    def test_empty_trades(self):
        m = PerformanceMetrics([])
        assert m.total_trades == 0
        assert m.win_rate == 0

    def test_win_rate(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("110"), Decimal("10")),
            TradeRecord("EURUSD", "SELL", Decimal("1"), Decimal("100"), Decimal("90"), Decimal("10")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("95"), Decimal("-5")),
        ]
        m = PerformanceMetrics(trades)
        assert m.win_rate == pytest.approx(2 / 3, rel=0.01)

    def test_profit_factor(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("120"), Decimal("20")),
            TradeRecord("EURUSD", "SELL", Decimal("1"), Decimal("100"), Decimal("90"), Decimal("10")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("95"), Decimal("-5")),
        ]
        m = PerformanceMetrics(trades)
        assert m.profit_factor == pytest.approx(6.0, rel=0.01)

    def test_total_pnl(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("110"), Decimal("10")),
            TradeRecord("EURUSD", "SELL", Decimal("1"), Decimal("100"), Decimal("90"), Decimal("10")),
        ]
        m = PerformanceMetrics(trades)
        assert m.total_pnl == Decimal("20")

    def test_sharpe_ratio(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("110"), Decimal("10")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("105"), Decimal("5")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("108"), Decimal("8")),
        ]
        m = PerformanceMetrics(trades)
        assert m.sharpe_ratio > 0

    def test_max_drawdown(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("110"), Decimal("10")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("90"), Decimal("-10")),
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("95"), Decimal("-5")),
        ]
        m = PerformanceMetrics(trades)
        assert m.max_drawdown_pct > 0

    def test_summary_dict(self):
        trades = [
            TradeRecord("EURUSD", "BUY", Decimal("1"), Decimal("100"), Decimal("110"), Decimal("10")),
        ]
        m = PerformanceMetrics(trades)
        s = m.summary()
        assert "total_trades" in s
        assert "win_rate" in s
        assert "profit_factor" in s
        assert "sharpe_ratio" in s
        assert "max_drawdown_pct" in s
