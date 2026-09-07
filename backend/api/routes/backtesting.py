"""Backtesting API routes — exposes backtesting engine via REST."""
from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backtesting.engine import BacktestEngine
from backtesting.metrics import TradeRecord
from backtesting.monte_carlo import MonteCarloConfig, MonteCarloSimulator
from backtesting.walk_forward import WalkForwardConfig, WalkForwardOptimizer
from data.models import Candle, Timeframe

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class CandleInput(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "1H"
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    timestamp: str = ""


class BacktestRunRequest(BaseModel):
    symbol: str
    timeframe: str = "1H"
    initial_balance: float = 10000
    risk_per_trade: float = 0.01
    stop_loss_pips: float = 50
    take_profit_pips: float = 100
    contract_size: int = 100000
    candles: List[CandleInput]


class WalkForwardRequest(BaseModel):
    symbol: str
    timeframe: str = "1H"
    initial_balance: float = 10000
    in_sample_pct: float = 0.7
    n_splits: int = 5
    risk_per_trade: float = 0.01
    stop_loss_pips: float = 50
    take_profit_pips: float = 100
    contract_size: int = 100000
    param_grid: Optional[Dict[str, List[float]]] = None
    candles: List[CandleInput]


class TradeInput(BaseModel):
    symbol: str = "EURUSD"
    side: str = "BUY"
    quantity: str = "0.01"
    entry_price: str = "0"
    exit_price: str = "0"
    pnl: str = "0"


class MonteCarloRequest(BaseModel):
    trades: List[TradeInput]
    n_simulations: int = 1000
    confidence_level: float = 0.95
    initial_equity: float = 10000
    seed: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle_input_to_candle(ci: CandleInput) -> Candle:
    tf_map = {tf.value: tf for tf in Timeframe}
    tf = tf_map.get(ci.timeframe, Timeframe.ONE_HOUR)
    ts = datetime.fromisoformat(ci.timestamp) if ci.timestamp else datetime.utcnow()
    return Candle(
        symbol=ci.symbol,
        timeframe=tf,
        open=ci.open,
        high=ci.high,
        low=ci.low,
        close=ci.close,
        volume=ci.volume,
        timestamp=ts,
    )


def _safe_float(value: float) -> float | None:
    """Return None for inf/nan so JSON serialization succeeds."""
    if value != value:  # NaN
        return None
    if value == float("inf") or value == float("-inf"):
        return None
    return value


def _serialize_backtest_result(result) -> dict:
    # Sanitize metrics_summary to remove inf/nan for JSON
    clean_summary = {}
    for k, v in result.metrics_summary.items():
        if isinstance(v, float):
            clean_summary[k] = _safe_float(v)
        else:
            clean_summary[k] = v
    return {
        "symbol": result.symbol,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "win_rate": result.win_rate,
        "total_pnl": str(result.total_pnl),
        "profit_factor": _safe_float(result.profit_factor),
        "sharpe_ratio": _safe_float(result.sharpe_ratio),
        "max_drawdown_pct": result.max_drawdown_pct,
        "equity_history": result.equity_history,
        "trade_history": result.trade_history,
        "metrics_summary": clean_summary,
    }


def _serialize_walk_forward_result(result) -> dict:
    return {
        "oos_results": [_serialize_backtest_result(r) for r in result.oos_results],
        "oos_equity_curve": result.oos_equity_curve,
        "oos_metrics": result.oos_metrics,
        "best_params": result.best_params,
        "param_scores": result.param_scores,
    }


def _serialize_monte_carlo_result(result) -> dict:
    return {
        "simulated_pnl": result.simulated_pnl,
        "simulated_max_drawdown": result.simulated_max_drawdown,
        "simulated_sharpe": result.simulated_sharpe,
        "statistics": result.statistics,
        "confidence_intervals": result.confidence_intervals,
    }


# ---------------------------------------------------------------------------
# Simple strategy functions for API use
# ---------------------------------------------------------------------------

def _make_buy_and_hold() -> Callable:
    """Alternates BUY and HOLD — buys once, holds until end."""
    _bought = {"flag": False}

    async def strategy(symbol: str, timeframe: str) -> dict:
        if not _bought["flag"]:
            _bought["flag"] = True
            return {"action": "BUY", "confidence": 0.8}
        return {"action": "HOLD", "confidence": 0}

    return strategy


def _make_alternating() -> Callable:
    """Alternates BUY/SELL signals for backtest variety."""
    _state = {"count": 0}

    async def strategy(symbol: str, timeframe: str) -> dict:
        _state["count"] += 1
        if _state["count"] % 10 == 1:
            return {"action": "BUY", "confidence": 0.6}
        elif _state["count"] % 10 == 6:
            return {"action": "SELL", "confidence": 0.6}
        return {"action": "HOLD", "confidence": 0}

    return strategy


STRATEGIES = {
    "buy_and_hold": _make_buy_and_hold,
    "alternating": _make_alternating,
    "none": lambda: None,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
def run_backtest(payload: BacktestRunRequest):
    """Run a backtest with the given candles and strategy."""
    candles = [_candle_input_to_candle(c) for c in payload.candles]

    engine = BacktestEngine(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        initial_balance=Decimal(str(payload.initial_balance)),
        risk_per_trade=payload.risk_per_trade,
        stop_loss_pips=payload.stop_loss_pips,
        take_profit_pips=payload.take_profit_pips,
        contract_size=payload.contract_size,
    )
    engine.consensus_fn = _make_buy_and_hold()

    result = engine.run(candles)
    return _serialize_backtest_result(result)


@router.post("/walk-forward")
def run_walk_forward(payload: WalkForwardRequest):
    """Run walk-forward optimization with rolling windows."""
    candles = [_candle_input_to_candle(c) for c in payload.candles]

    param_grid = None
    if payload.param_grid:
        param_grid = {k: [Decimal(str(v)) for v in vals]
                      for k, vals in payload.param_grid.items()}
        # WalkForwardConfig.param_grid expects plain floats
        param_grid = payload.param_grid

    config = WalkForwardConfig(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        initial_balance=Decimal(str(payload.initial_balance)),
        in_sample_pct=payload.in_sample_pct,
        n_splits=payload.n_splits,
        risk_per_trade=payload.risk_per_trade,
        stop_loss_pips=payload.stop_loss_pips,
        take_profit_pips=payload.take_profit_pips,
        contract_size=payload.contract_size,
        param_grid=param_grid,
    )

    optimizer = WalkForwardOptimizer(config)
    result = optimizer.run(candles, consensus_fn=_make_buy_and_hold())
    return _serialize_walk_forward_result(result)


@router.post("/monte-carlo")
def run_monte_carlo(payload: MonteCarloRequest):
    """Run Monte Carlo simulation on trade records."""
    trades: List[TradeRecord] = []
    for t in payload.trades:
        trades.append(TradeRecord(
            symbol=t.symbol,
            side=t.side,
            quantity=Decimal(t.quantity),
            entry_price=Decimal(t.entry_price),
            exit_price=Decimal(t.exit_price),
            pnl=Decimal(t.pnl),
        ))

    config = MonteCarloConfig(
        n_simulations=payload.n_simulations,
        confidence_level=payload.confidence_level,
        initial_equity=payload.initial_equity,
        seed=payload.seed,
    )

    simulator = MonteCarloSimulator(config)
    result = simulator.run(trades)
    return _serialize_monte_carlo_result(result)
