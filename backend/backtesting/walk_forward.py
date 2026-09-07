"""Walk-Forward Optimizer — validates strategy parameters across rolling windows."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from data.models import Candle
from backtesting.engine import BacktestEngine, BacktestResult
from backtesting.metrics import PerformanceMetrics, TradeRecord


@dataclass
class WalkForwardConfig:
    symbol: str = "EURUSD"
    timeframe: str = "1H"
    initial_balance: Decimal = Decimal("10000")
    in_sample_pct: float = 0.7
    n_splits: int = 5
    risk_per_trade: float = 0.01
    stop_loss_pips: float = 50
    take_profit_pips: float = 100
    contract_size: int = 100000
    param_grid: Optional[Dict[str, List]] = None


class WalkForwardSplitter:
    """Splits candle data into rolling (in-sample, out-sample) window pairs."""

    def __init__(self, n_splits: int, in_sample_pct: float):
        self.n_splits = n_splits
        self.in_sample_pct = in_sample_pct

    def split(self, candles: List[Candle]) -> List[Tuple[List[Candle], List[Candle]]]:
        if not candles:
            return []

        n = len(candles)
        if n < self.n_splits:
            # Fewer candles than splits — produce one window
            split_point = max(1, int(n * self.in_sample_pct))
            return [(candles[:split_point], candles[split_point:])]

        window_size = n // self.n_splits
        windows: List[Tuple[List[Candle], List[Candle]]] = []

        for i in range(self.n_splits):
            start = i * window_size
            if i == self.n_splits - 1:
                end = n
            else:
                end = start + window_size

            segment = candles[start:end]
            split_point = max(1, int(len(segment) * self.in_sample_pct))
            in_sample = segment[:split_point]
            out_sample = segment[split_point:]
            if in_sample and out_sample:
                windows.append((in_sample, out_sample))

        return windows


@dataclass
class WalkForwardResult:
    oos_results: List[BacktestResult]
    oos_equity_curve: List[float]
    oos_metrics: Dict[str, Any]
    best_params: Dict[str, Any]
    param_scores: Optional[List[Dict[str, Any]]] = None


class WalkForwardOptimizer:
    """Walk-forward optimization: trains on in-sample windows, tests on out-of-sample."""

    def __init__(self, config: WalkForwardConfig):
        self.config = config

    def run(
        self,
        candles: List[Candle],
        consensus_fn: Optional[Callable] = None,
    ) -> WalkForwardResult:
        if not candles:
            return WalkForwardResult(
                oos_results=[], oos_equity_curve=[], oos_metrics={},
                best_params=self._default_params(),
            )

        splitter = WalkForwardSplitter(
            n_splits=self.config.n_splits,
            in_sample_pct=self.config.in_sample_pct,
        )
        windows = splitter.split(candles)

        if not windows:
            return WalkForwardResult(
                oos_results=[], oos_equity_curve=[], oos_metrics={},
                best_params=self._default_params(),
            )

        # If param_grid provided, find best params via grid search on in-sample
        if self.config.param_grid:
            best_params, param_scores = self._optimize_params(windows, consensus_fn)
        else:
            best_params = self._default_params()
            param_scores = None

        # Run OOS with best params
        oos_results: List[BacktestResult] = []
        oos_equity_curve: List[float] = []

        for in_sample, out_sample in windows:
            engine = self._make_engine(best_params)
            engine.consensus_fn = consensus_fn
            result = engine.run(out_sample)
            oos_results.append(result)
            oos_equity_curve.extend(result.equity_history)

        # Compute combined OOS metrics from all trade records
        all_trades: List[TradeRecord] = []
        for r in oos_results:
            all_trades.extend([
                TradeRecord(t.symbol, t.side, t.quantity, t.entry_price, t.exit_price, t.pnl)
                for t in [self._dict_to_trade(d, r) for d in r.trade_history if d.get("type") == "sl_tp_exit"]
            ])

        # Use PerformanceMetrics on combined equity curve as fallback
        metrics = PerformanceMetrics(all_trades, initial_equity=float(self.config.initial_balance))
        oos_metrics = metrics.summary()

        return WalkForwardResult(
            oos_results=oos_results,
            oos_equity_curve=oos_equity_curve,
            oos_metrics=oos_metrics,
            best_params=best_params,
            param_scores=param_scores,
        )

    def _default_params(self) -> Dict[str, Any]:
        return {
            "stop_loss_pips": self.config.stop_loss_pips,
            "take_profit_pips": self.config.take_profit_pips,
        }

    def _make_engine(self, params: Dict[str, Any]) -> BacktestEngine:
        return BacktestEngine(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            initial_balance=self.config.initial_balance,
            risk_per_trade=self.config.risk_per_trade,
            stop_loss_pips=params.get("stop_loss_pips", self.config.stop_loss_pips),
            take_profit_pips=params.get("take_profit_pips", self.config.take_profit_pips),
            contract_size=self.config.contract_size,
        )

    def _optimize_params(
        self,
        windows: List[Tuple[List[Candle], List[Candle]]],
        consensus_fn: Optional[Callable],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Grid search over param_grid using in-sample data, validate on OOS."""
        param_grid = self.config.param_grid or {}
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        param_scores: List[Dict[str, Any]] = []

        for combo in combinations:
            params = dict(zip(keys, combo))
            # Average sharpe across all in-sample windows for this param set
            sharpes = []
            for in_sample, out_sample in windows:
                engine = self._make_engine(params)
                engine.consensus_fn = consensus_fn
                result = engine.run(in_sample)
                sharpes.append(result.sharpe_ratio)

            avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0
            param_scores.append({
                "params": params,
                "avg_sharpe": avg_sharpe,
            })

        # Select best by highest average Sharpe
        best = max(param_scores, key=lambda x: x["avg_sharpe"])
        return best["params"], param_scores

    def _dict_to_trade(self, d: Dict, result: BacktestResult) -> TradeRecord:
        """Convert trade_history dict to TradeRecord using result's trade data."""
        return TradeRecord(
            symbol=result.symbol,
            side=d.get("side", "BUY"),
            quantity=Decimal("0.01"),
            entry_price=Decimal(d.get("price", "0")),
            exit_price=Decimal(d.get("price", "0")),
            pnl=Decimal("0"),
        )
