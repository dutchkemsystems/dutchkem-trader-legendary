"""Monte Carlo Simulator — trade resampling for confidence intervals."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from backtesting.metrics import TradeRecord


@dataclass
class MonteCarloConfig:
    n_simulations: int = 1000
    confidence_level: float = 0.95
    initial_equity: float = 10000
    seed: Optional[int] = None


@dataclass
class MonteCarloResult:
    simulated_pnl: List[float]
    simulated_max_drawdown: List[float]
    simulated_sharpe: List[float]
    statistics: Dict[str, float]
    confidence_intervals: Dict[str, float]


class MonteCarloSimulator:
    """Resamples trade sequences to estimate P&L distribution and confidence intervals.

    Each simulation randomly resamples (with replacement) from the original trade list,
    computes cumulative equity, max drawdown, and Sharpe ratio.
    """

    def __init__(self, config: MonteCarloConfig):
        self.config = config

    def run(self, trades: List[TradeRecord]) -> MonteCarloResult:
        if not trades:
            return MonteCarloResult(
                simulated_pnl=[],
                simulated_max_drawdown=[],
                simulated_sharpe=[],
                statistics={},
                confidence_intervals={},
            )

        rng = random.Random(self.config.seed)
        n = self.config.n_simulations
        n_trades = len(trades)

        pnl_list: List[float] = []
        dd_list: List[float] = []
        sharpe_list: List[float] = []

        for _ in range(n):
            # Resample trades with replacement
            sample = [trades[rng.randint(0, n_trades - 1)] for _ in range(n_trades)]

            equity = self.config.initial_equity
            peak = equity
            max_dd = 0.0
            returns: List[float] = []

            for t in sample:
                pnl = float(t.pnl)
                equity += pnl
                returns.append(pnl)
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

            total_pnl = equity - self.config.initial_equity
            pnl_list.append(total_pnl)
            dd_list.append(max_dd)

            # Sharpe ratio of the resampled sequence
            if len(returns) >= 2:
                mean_r = sum(returns) / len(returns)
                var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
                std = var ** 0.5
                sharpe = mean_r / std if std > 0 else 0.0
            else:
                sharpe = 0.0
            sharpe_list.append(sharpe)

        stats = self._compute_statistics(pnl_list, dd_list, sharpe_list)
        ci = self._compute_confidence_intervals(pnl_list, dd_list, sharpe_list)

        return MonteCarloResult(
            simulated_pnl=pnl_list,
            simulated_max_drawdown=dd_list,
            simulated_sharpe=sharpe_list,
            statistics=stats,
            confidence_intervals=ci,
        )

    def _compute_statistics(
        self, pnl: List[float], dd: List[float], sharpe: List[float]
    ) -> Dict[str, float]:
        def _stats(values: List[float], prefix: str) -> Dict[str, float]:
            if not values:
                return {}
            n = len(values)
            sorted_v = sorted(values)
            mean = sum(values) / n
            var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
            return {
                f"{prefix}_mean": mean,
                f"{prefix}_median": sorted_v[n // 2],
                f"{prefix}_std": var ** 0.5,
                f"{prefix}_min": sorted_v[0],
                f"{prefix}_max": sorted_v[-1],
            }

        stats: Dict[str, float] = {}
        stats.update(_stats(pnl, "pnl"))
        stats.update(_stats(dd, "drawdown"))
        stats.update(_stats(sharpe, "sharpe"))
        return stats

    def _compute_confidence_intervals(
        self, pnl: List[float], dd: List[float], sharpe: List[float]
    ) -> Dict[str, float]:
        def _ci(values: List[float], prefix: str) -> Dict[str, float]:
            if not values:
                return {}
            sorted_v = sorted(values)
            n = len(sorted_v)
            alpha = 1 - self.config.confidence_level
            lo_idx = int(n * alpha / 2)
            hi_idx = int(n * (1 - alpha / 2)) - 1
            lo_idx = max(0, min(lo_idx, n - 1))
            hi_idx = max(0, min(hi_idx, n - 1))
            return {
                f"{prefix}_lower": sorted_v[lo_idx],
                f"{prefix}_upper": sorted_v[hi_idx],
            }

        ci: Dict[str, float] = {}
        ci.update(_ci(pnl, "pnl"))
        ci.update(_ci(dd, "drawdown"))
        ci.update(_ci(sharpe, "sharpe"))
        return ci
