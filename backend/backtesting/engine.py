"""BacktestEngine — main orchestrator for strategy simulation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from data.models import Candle, Timeframe
from backtesting.portfolio import Portfolio
from backtesting.metrics import PerformanceMetrics, TradeRecord


@dataclass
class BacktestResult:
    symbol: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: Decimal
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    equity_history: List[float]
    trade_history: List[Dict]
    metrics_summary: Dict


class BacktestEngine:
    """Simulates trading on historical candle data.

    Usage:
        engine = BacktestEngine(symbol="EURUSD", timeframe="1H",
                                initial_balance=Decimal("10000"))
        engine.consensus_fn = my_consensus_function  # async(symbol, timeframe) -> dict
        result = engine.run(candles)
    """

    def __init__(self, symbol: str, timeframe: str = "1H",
                 initial_balance: Decimal = Decimal("10000"),
                 risk_per_trade: float = 0.01, stop_loss_pips: float = 50,
                 take_profit_pips: float = 100, contract_size: int = 100000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.stop_loss_pips = stop_loss_pips
        self.take_profit_pips = take_profit_pips
        self.contract_size = contract_size
        self.consensus_fn: Optional[Callable] = None
        self._portfolio = Portfolio(initial_balance, contract_size=contract_size)

    def run(self, candles: List[Candle]) -> BacktestResult:
        """Run backtest on historical candles."""
        equity_history = [float(self.initial_balance)]
        trade_history: List[Dict] = []

        if not candles:
            return self._build_result(equity_history, trade_history)

        for i, candle in enumerate(candles):
            self._portfolio.update_prices({
                self.symbol: {
                    "bid": Decimal(str(candle.close)),
                    "high": Decimal(str(candle.high)),
                    "low": Decimal(str(candle.low)),
                }
            })

            hits = self._portfolio.check_sl_tp_hits()
            for idx, exit_price in sorted(hits, reverse=True):
                self._portfolio.close_position(idx, exit_price)
                trade_history.append({
                    "type": "sl_tp_exit", "price": str(exit_price),
                    "candle_index": i,
                })

            if self.consensus_fn:
                consensus = self._run_consensus()
                action = consensus.get("action", "HOLD")
                confidence = consensus.get("confidence", 0)

                if action == "BUY" and not self._has_position("BUY"):
                    qty = self._calc_lot_size(confidence)
                    entry = Decimal(str(candle.close))
                    sl = entry - Decimal(str(self.stop_loss_pips * 0.0001))
                    tp = entry + Decimal(str(self.take_profit_pips * 0.0001))
                    self._portfolio.open_position(
                        self.symbol, "BUY", qty, entry, sl, tp
                    )
                    trade_history.append({
                        "type": "open", "side": "BUY", "price": str(entry),
                        "quantity": str(qty), "candle_index": i,
                    })

                elif action == "SELL" and not self._has_position("SELL"):
                    qty = self._calc_lot_size(confidence)
                    entry = Decimal(str(candle.close))
                    sl = entry + Decimal(str(self.stop_loss_pips * 0.0001))
                    tp = entry - Decimal(str(self.take_profit_pips * 0.0001))
                    self._portfolio.open_position(
                        self.symbol, "SELL", qty, entry, sl, tp
                    )
                    trade_history.append({
                        "type": "open", "side": "SELL", "price": str(entry),
                        "quantity": str(qty), "candle_index": i,
                    })

            equity_history.append(float(self._portfolio.equity))

        if candles:
            last_price = Decimal(str(candles[-1].close))
            while self._portfolio.open_positions:
                self._portfolio.close_position(0, last_price)

        return self._build_result(equity_history, trade_history)

    def _run_consensus(self) -> Dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, self.consensus_fn(self.symbol, self.timeframe)
                )
                return future.result()
        else:
            return asyncio.run(self.consensus_fn(self.symbol, self.timeframe))

    def _has_position(self, side: str) -> bool:
        return any(p.side == side for p in self._portfolio.open_positions)

    def _calc_lot_size(self, confidence: float) -> Decimal:
        risk_pct = 0.005 + confidence * 0.015
        balance = float(self._portfolio.balance)
        risk_amount = balance * risk_pct
        pip_value = self.stop_loss_pips * 10
        if pip_value <= 0:
            return Decimal("0.01")
        lots = risk_amount / pip_value
        return Decimal(str(round(max(0.01, lots), 2)))

    def _build_result(self, equity_history: List[float],
                      trade_history: List[Dict]) -> BacktestResult:
        trades = [
            TradeRecord(t.symbol, t.side, t.quantity, t.entry_price, t.exit_price, t.pnl)
            for t in self._portfolio.closed_trades
        ]
        metrics = PerformanceMetrics(trades, initial_equity=float(self.initial_balance))

        return BacktestResult(
            symbol=self.symbol,
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            win_rate=metrics.win_rate,
            total_pnl=metrics.total_pnl,
            profit_factor=metrics.profit_factor,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown_pct=metrics.max_drawdown_pct,
            equity_history=equity_history,
            trade_history=trade_history,
            metrics_summary=metrics.summary(),
        )
