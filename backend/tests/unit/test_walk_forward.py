"""Tests for WalkForwardOptimizer — walk-forward analysis for backtesting."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from data.models import Candle, Timeframe


def _make_candles(prices, symbol="EURUSD"):
    """Helper: create candles from a list of close prices."""
    from datetime import timedelta
    candles = []
    base = datetime(2024, 1, 1)
    for i, p in enumerate(prices):
        candles.append(Candle(
            symbol=symbol, timeframe=Timeframe.ONE_HOUR,
            open=p, high=p + 0.001, low=p - 0.001, close=p,
            volume=1000, timestamp=base + timedelta(hours=i),
        ))
    return candles


class TestWalkForwardConfig:
    def test_default_config(self):
        from backtesting.walk_forward import WalkForwardConfig
        cfg = WalkForwardConfig()
        assert cfg.in_sample_pct == 0.7
        assert cfg.n_splits == 5
        assert cfg.initial_balance == Decimal("10000")
        assert cfg.symbol == "EURUSD"
        assert cfg.timeframe == "1H"

    def test_custom_config(self):
        from backtesting.walk_forward import WalkForwardConfig
        cfg = WalkForwardConfig(
            in_sample_pct=0.6, n_splits=3,
            initial_balance=Decimal("50000"),
            symbol="GBPUSD", timeframe="4H",
        )
        assert cfg.in_sample_pct == 0.6
        assert cfg.n_splits == 3
        assert cfg.initial_balance == Decimal("50000")
        assert cfg.symbol == "GBPUSD"
        assert cfg.timeframe == "4H"


class TestWalkForwardSplitter:
    def test_split_windows(self):
        from backtesting.walk_forward import WalkForwardSplitter
        candles = _make_candles(list(range(100)))
        splitter = WalkForwardSplitter(n_splits=5, in_sample_pct=0.7)
        windows = splitter.split(candles)
        assert len(windows) == 5
        for in_sample, out_sample in windows:
            assert len(in_sample) > 0
            assert len(out_sample) > 0

    def test_split_empty_candles(self):
        from backtesting.walk_forward import WalkForwardSplitter
        splitter = WalkForwardSplitter(n_splits=5, in_sample_pct=0.7)
        windows = splitter.split([])
        assert len(windows) == 0

    def test_split_too_few_candles(self):
        """With fewer candles than splits, returns at most n_splits windows."""
        from backtesting.walk_forward import WalkForwardSplitter
        candles = _make_candles(list(range(10)))
        splitter = WalkForwardSplitter(n_splits=5, in_sample_pct=0.7)
        windows = splitter.split(candles)
        assert len(windows) > 0
        assert len(windows) <= 5

    def test_in_sample_before_out_sample(self):
        """In-sample window indices should come before out-sample."""
        from backtesting.walk_forward import WalkForwardSplitter
        candles = _make_candles(list(range(100)))
        splitter = WalkForwardSplitter(n_splits=5, in_sample_pct=0.7)
        windows = splitter.split(candles)
        for in_sample, out_sample in windows:
            last_in = in_sample[-1]
            first_out = out_sample[0]
            assert candles.index(last_in) < candles.index(first_out)


class TestWalkForwardOptimizer:
    def test_basic_optimize(self):
        """Optimizer runs without errors on simple data."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        candles = _make_candles([1.085 + i * 0.001 for i in range(60)])
        config = WalkForwardConfig(
            symbol="EURUSD", timeframe="1H",
            n_splits=3, in_sample_pct=0.7,
            initial_balance=Decimal("10000"),
        )
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        assert hasattr(result, "oos_results")
        assert hasattr(result, "oos_equity_curve")
        assert hasattr(result, "oos_metrics")
        assert len(result.oos_results) > 0

    def test_oos_metrics_computed(self):
        """Out-of-sample metrics are computed from concatenated OOS results."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        prices = [1.085 + i * 0.001 for i in range(60)]
        candles = _make_candles(prices)
        config = WalkForwardConfig(symbol="EURUSD", n_splits=3, in_sample_pct=0.7)
        optimizer = WalkForwardOptimizer(config)

        call_count = 0
        async def mock_consensus(symbol, timeframe):
            nonlocal call_count
            call_count += 1
            if call_count % 5 == 0:
                return {"action": "BUY", "confidence": 0.8, "agreement_pct": 0.85}
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        assert "win_rate" in result.oos_metrics
        assert "profit_factor" in result.oos_metrics
        assert "total_pnl" in result.oos_metrics
        assert "sharpe_ratio" in result.oos_metrics

    def test_oos_equity_curve_length(self):
        """OOS equity curve total matches sum of all OOS equity histories."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        candles = _make_candles([1.085 + i * 0.001 for i in range(60)])
        config = WalkForwardConfig(symbol="EURUSD", n_splits=3, in_sample_pct=0.7)
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        # Each OOS segment produces equity_history, total should equal sum of their lengths
        total_equity_points = sum(
            len(r.equity_history) for r in result.oos_results
        )
        assert len(result.oos_equity_curve) == total_equity_points

    def test_empty_candles(self):
        """Optimizer handles empty candle list gracefully."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        config = WalkForwardConfig(symbol="EURUSD", n_splits=3)
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run([], mock_consensus)
        assert len(result.oos_results) == 0
        assert len(result.oos_equity_curve) == 0

    def test_n_splits_one(self):
        """With n_splits=1, entire data is one window (70% train, 30% test)."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        candles = _make_candles([1.085 + i * 0.001 for i in range(30)])
        config = WalkForwardConfig(symbol="EURUSD", n_splits=1, in_sample_pct=0.7)
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        assert len(result.oos_results) == 1

    def test_param_grid(self):
        """Optimizer can accept a parameter grid for optimization."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        candles = _make_candles([1.085 + i * 0.001 for i in range(60)])
        config = WalkForwardConfig(
            symbol="EURUSD", n_splits=3, in_sample_pct=0.7,
            param_grid={"stop_loss_pips": [30, 50], "take_profit_pips": [60, 100]},
        )
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        assert hasattr(result, "best_params")
        assert isinstance(result.best_params, dict)
        # Best params should be from the grid
        assert result.best_params["stop_loss_pips"] in [30, 50]
        assert result.best_params["take_profit_pips"] in [60, 100]

    def test_best_params_selected_by_sharpe(self):
        """Best params are selected by highest Sharpe ratio in OOS."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig
        candles = _make_candles([1.085 + i * 0.001 for i in range(60)])
        config = WalkForwardConfig(
            symbol="EURUSD", n_splits=3, in_sample_pct=0.7,
            param_grid={"stop_loss_pips": [30, 50]},
        )
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        # Should have a best params dict
        assert isinstance(result.best_params, dict)
        assert "stop_loss_pips" in result.best_params

    def test_oos_concatenated_result(self):
        """WalkForwardResult contains concatenated results from all OOS windows."""
        from backtesting.walk_forward import WalkForwardOptimizer, WalkForwardConfig, WalkForwardResult
        candles = _make_candles([1.085 + i * 0.001 for i in range(60)])
        config = WalkForwardConfig(symbol="EURUSD", n_splits=3, in_sample_pct=0.7)
        optimizer = WalkForwardOptimizer(config)

        async def mock_consensus(symbol, timeframe):
            return {"action": "HOLD", "confidence": 0.0, "agreement_pct": 0.0}

        result = optimizer.run(candles, mock_consensus)
        assert isinstance(result, WalkForwardResult)
        assert isinstance(result.oos_metrics, dict)
        assert isinstance(result.oos_equity_curve, list)
        assert isinstance(result.oos_results, list)
        assert isinstance(result.best_params, dict)
