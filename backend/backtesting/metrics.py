"""Performance metrics for backtesting results."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List


@dataclass
class TradeRecord:
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal


class PerformanceMetrics:
    def __init__(self, trades: List[TradeRecord], initial_equity: float = 10000):
        self._trades = trades
        self._initial_equity = initial_equity

    @property
    def total_trades(self) -> int:
        return len(self._trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self._trades if t.pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self._trades if t.pnl < 0)

    @property
    def win_rate(self) -> float:
        if not self._trades:
            return 0
        return self.winning_trades / len(self._trades)

    @property
    def total_pnl(self) -> Decimal:
        return sum(t.pnl for t in self._trades)

    @property
    def avg_win(self) -> Decimal:
        wins = [t.pnl for t in self._trades if t.pnl > 0]
        return sum(wins) / len(wins) if wins else Decimal("0")

    @property
    def avg_loss(self) -> Decimal:
        losses = [t.pnl for t in self._trades if t.pnl < 0]
        return sum(losses) / len(losses) if losses else Decimal("0")

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self._trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self._trades if t.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0
        return float(gross_profit / gross_loss)

    @property
    def sharpe_ratio(self) -> float:
        if len(self._trades) < 2:
            return 0
        returns = [float(t.pnl) for t in self._trades]
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std = var ** 0.5
        if std == 0:
            return 0
        return mean_r / std

    @property
    def max_drawdown_pct(self) -> float:
        if not self._trades:
            return 0
        equity = Decimal(str(self._initial_equity))
        peak = equity
        max_dd = Decimal("0")
        for t in self._trades:
            equity += t.pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return float(max_dd)

    def summary(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": str(self.total_pnl),
            "avg_win": str(self.avg_win),
            "avg_loss": str(self.avg_loss),
            "profit_factor": round(self.profit_factor, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
        }
