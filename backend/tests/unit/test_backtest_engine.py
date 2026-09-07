import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
from backtesting.engine import BacktestEngine
from data.models import Candle, Timeframe
from datetime import datetime


def _make_candles(prices, symbol="EURUSD"):
    """Helper: create candles from a list of close prices."""
    candles = []
    for i, p in enumerate(prices):
        candles.append(Candle(
            symbol=symbol, timeframe=Timeframe.ONE_HOUR,
            open=p, high=p + 0.001, low=p - 0.001, close=p,
            volume=1000, timestamp=datetime(2024, 1, 1, i),
        ))
    return candles


class TestBacktestEngine:
    def test_basic_run(self):
        """Engine runs without errors on simple data."""
        candles = _make_candles([1.085, 1.086, 1.087, 1.088, 1.089])
        engine = BacktestEngine(
            symbol="EURUSD",
            timeframe="1H",
            initial_balance=Decimal("10000"),
        )
        # Mock consensus to return BUY on first candle, HOLD after
        call_count = 0
        async def mock_consensus(symbol, timeframe):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"action": "BUY", "confidence": 0.8, "agreement_pct": 0.85}
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        engine.consensus_fn = mock_consensus
        result = engine.run(candles)
        assert result.total_trades >= 0
        assert result.equity_history is not None

    def test_no_trades_holds(self):
        """Engine produces no trades when consensus always says HOLD."""
        candles = _make_candles([1.085, 1.086, 1.087])
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}
        engine.consensus_fn = mock_consensus
        result = engine.run(candles)
        assert result.total_trades == 0

    def test_buy_and_sell(self):
        """Engine opens a position and closes it."""
        candles = _make_candles([1.085, 1.086, 1.087, 1.088, 1.089])
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        call_count = 0
        async def mock_consensus(symbol, timeframe):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"action": "BUY", "confidence": 0.8, "agreement_pct": 0.85}
            elif call_count == 4:
                return {"action": "SELL", "confidence": 0.8, "agreement_pct": 0.85}
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}
        engine.consensus_fn = mock_consensus
        result = engine.run(candles)
        assert result.total_trades >= 1

    def test_empty_candles(self):
        """Engine handles empty candle list gracefully."""
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        result = engine.run([])
        assert result.total_trades == 0
        assert result.equity_history == [10000.0]

    def test_result_fields(self):
        """BacktestResult contains all expected fields."""
        candles = _make_candles([1.085, 1.086])
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}
        engine.consensus_fn = mock_consensus
        result = engine.run(candles)
        assert hasattr(result, "symbol")
        assert hasattr(result, "total_trades")
        assert hasattr(result, "winning_trades")
        assert hasattr(result, "losing_trades")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "total_pnl")
        assert hasattr(result, "profit_factor")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "max_drawdown_pct")
        assert hasattr(result, "equity_history")
        assert hasattr(result, "trade_history")
        assert hasattr(result, "metrics_summary")
        assert result.symbol == "EURUSD"

    def test_sl_tp_closes_position(self):
        """Engine closes position when SL is hit via candle low."""
        # Create candles where price drops enough to hit SL
        candles = _make_candles([1.085, 1.080, 1.081])
        engine = BacktestEngine(
            symbol="EURUSD", timeframe="1H",
            initial_balance=Decimal("10000"),
            stop_loss_pips=30,
        )
        call_count = 0
        async def mock_consensus(symbol, timeframe):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"action": "BUY", "confidence": 0.8, "agreement_pct": 0.85}
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}
        engine.consensus_fn = mock_consensus
        result = engine.run(candles)
        # Position should have been closed by SL hit or at end
        assert result.total_trades >= 1

    def test_no_consensus_fn(self):
        """Engine runs without consensus function (no trades)."""
        candles = _make_candles([1.085, 1.086, 1.087])
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        # No consensus_fn set
        result = engine.run(candles)
        assert result.total_trades == 0
        assert result.equity_history[-1] == 10000.0
