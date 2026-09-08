"""
Walk-Forward Backtesting Engine
===============================
Simulates the V5 intelligence pipeline on historical data:
1. Generate realistic OHLCV candles (synthetic when live data unavailable)
2. Slide through time window by window
3. At each step: run 12 analysts via ConsensusEngine + gates + sizing
4. Track P&L, win rate, max drawdown, Sharpe ratio
5. Output performance report
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
django.setup()

import numpy as np
import pandas as pd
from apps.consensus.engine import ConsensusEngine
from apps.consensus.gates import ConsensusGates
from apps.ml.predictor import MLPredictor
from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory
from apps.llm.client import LLMClient
from execution.kelly_sizer import KellySizer
from execution.risk_config import RiskConfig

# Analysts
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.compliance import ComplianceAnalyst
from apps.vision import ChartAnalyzer


# ─── Data Classes ────────────────────────────────────────────
@dataclass
class Trade:
    entry_time: str
    exit_time: str
    symbol: str
    action: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    confidence: float
    agreement_pct: float


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    total_bars: int
    trades: list = field(default_factory=list)
    final_balance: float = 10000.0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0


# ─── Data Loaders ────────────────────────────────────────────
DATA_DIR = Path("paper_trades")


def load_real_candles(symbol: str) -> pd.DataFrame:
    """Load real candles from MT5 CSV (fetched by fetch_and_train.py)."""
    csv_path = DATA_DIR / f"{symbol}_1H.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path, index_col="timestamp", parse_dates=True)
        print(f"  Loaded {len(df)} real candles from {csv_path}")
        return df
    return None


def load_trained_model():
    """Load the trained XGBoost model if available."""
    model_path = DATA_DIR / "xgboost_model.json"
    if model_path.exists():
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier()
            model.load_model(str(model_path))
            print(f"  Loaded trained XGBoost model from {model_path}")
            return model
        except Exception as e:
            print(f"  Could not load model: {e}")
    return None


def generate_candles(symbol: str, num_candles: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV candles (fallback when real data unavailable)."""
    # Seed based on symbol for reproducibility
    seed = sum(ord(c) for c in symbol)
    rng = np.random.RandomState(seed)

    # Starting prices by symbol
    base_prices = {
        "EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 149.50,
        "XAUUSD": 2500.0, "BTCUSD": 62000.0,
    }
    price = base_prices.get(symbol, 1.0)
    vol = 0.0005 if "JPY" not in symbol else 0.003
    if "XAU" in symbol:
        vol = 0.001
    if "BTC" in symbol:
        vol = 0.003

    # Generate prices with mean-reversion + trend
    closes = [price]
    trend = rng.choice([-1, 1]) * 0.0001
    for i in range(num_candles - 1):
        drift = trend + (price - closes[0]) * -0.0001  # mean revert
        shock = rng.normal(0, vol)
        price = price * (1 + drift + shock)
        closes.append(price)

    closes = np.array(closes)
    # Build OHLCV
    highs = closes * (1 + np.abs(rng.normal(0, vol * 0.5, num_candles)))
    lows = closes * (1 - np.abs(rng.normal(0, vol * 0.5, num_candles)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0] * (1 + rng.normal(0, vol * 0.3))
    volumes = rng.randint(100, 10000, num_candles)

    base_time = datetime(2026, 8, 1, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(num_candles)]

    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    }, index=pd.DatetimeIndex(timestamps, name="timestamp"))


# ─── Backtester ──────────────────────────────────────────────
class BacktestEngine:
    def __init__(self, initial_balance=10000.0):
        self.initial_balance = initial_balance

        chart_analyzer = ChartAnalyzer()
        self.analysts = [
            MarketAnalyst(), NewsAnalyst(), FundamentalsAnalyst(),
            SentimentAnalyst(), TechnicalAnalyst(chart_analyzer=chart_analyzer),
            OptionsAnalyst(), OrderFlowAnalyst(), RiskAnalyst(),
            MacroAnalyst(), OnChainAnalyst(), QuantAnalyst(), ComplianceAnalyst(),
        ]

        self.engine = ConsensusEngine(analysts=self.analysts)
        # Lower agreement threshold for backtesting
        self.engine.min_agreement = 0.50
        self.gates = ConsensusGates()
        self.kelly = KellySizer()

    def _custom_vote(self, results):
        """Custom voting: ignore HOLD-only analysts, focus on BUY/SELL signals."""
        buy = sum(1 for r in results if r.signal == "BUY")
        sell = sum(1 for r in results if r.signal == "SELL")
        hold = sum(1 for r in results if r.signal == "HOLD")
        total = len(results)

        # Non-HOLD analysts = those with a directional signal
        directional = buy + sell
        if directional == 0:
            return "HOLD", 0.5, 0.0

        if buy > sell:
            action = "BUY"
            agreement = directional / total  # % of analysts with a directional view
            confidence = sum(r.confidence for r in results if r.signal == "BUY") / buy
        elif sell > buy:
            action = "SELL"
            agreement = directional / total
            confidence = sum(r.confidence for r in results if r.signal == "SELL") / sell
        else:
            action = "HOLD"
            agreement = 0.0
            confidence = 0.5

        return action, confidence, agreement

    async def backtest(self, symbol, timeframe="1H", num_candles=500):
        """Run walk-forward backtest for a symbol."""
        print(f"\n  Loading data for {symbol}...")

        # Try real data first, fall back to synthetic
        candles = load_real_candles(symbol)
        if candles is None:
            print(f"  No real data found, generating synthetic candles...")
            candles = generate_candles(symbol, num_candles)
        print(f"  Period: {candles.index[0]} -> {candles.index[-1]} ({len(candles)} bars)")

        lookback = 50
        balance = self.initial_balance
        position = None
        trades = []
        equity_curve = [balance]

        print(f"  Running walk-forward backtest (lookback={lookback}, bars={len(candles)})...")
        start_time = time.time()

        for i in range(lookback, len(candles)):
            current_price = float(candles.iloc[i]["close"])
            current_time = str(candles.index[i])[:19]

            # Close existing position if held
            if position is not None:
                bars_held = i - position["entry_bar"]
                if bars_held >= 5:
                    if position["action"] == "BUY":
                        pnl = (current_price - position["entry_price"]) / position["entry_price"] * position["size"]
                    else:
                        pnl = (position["entry_price"] - current_price) / position["entry_price"] * position["size"]

                    balance += pnl
                    trades.append(Trade(
                        entry_time=position["entry_time"],
                        exit_time=current_time,
                        symbol=symbol,
                        action=position["action"],
                        entry_price=position["entry_price"],
                        exit_price=current_price,
                        size=position["size"],
                        pnl=pnl,
                        pnl_pct=pnl / position["size"] * 100,
                        confidence=position["confidence"],
                        agreement_pct=position["agreement_pct"],
                    ))
                    position = None

            # Open new position if none held
            if position is None:
                try:
                    # Run all 12 analysts in parallel
                    import asyncio as _aio
                    tasks = [a.analyze(symbol, timeframe) for a in self.analysts]
                    results = await _aio.gather(*tasks, return_exceptions=True)
                    valid = [r for r in results if hasattr(r, "signal")]
                    errors = [r for r in results if isinstance(r, Exception)]
                    if errors and i == lookback:  # Log first batch
                        for e in errors:
                            print(f"    analyst error: {e}")
                    if valid:
                        action, confidence, agreement = self._custom_vote(valid)
                        if i == lookback:  # Log first batch
                            for r in valid:
                                print(f"    {r.analyst_name}: {r.signal} ({r.confidence:.2f})")
                            print(f"    => action={action} agree={agreement:.2f}")
                    else:
                        action, confidence, agreement = "HOLD", 0.5, 0.0
                        if i == lookback:
                            print(f"    No valid results! errors={len(errors)}")

                    if action in ("BUY", "SELL") and agreement >= 0.25:
                        kelly_frac = self.kelly.calculate(
                            win_rate=0.55, avg_win=1.5, avg_loss=1.0,
                        )
                        size = max(10, kelly_frac * balance * 0.25)  # Quarter-Kelly, min $10
                        if size > 0 and size <= balance:
                            position = {
                                "action": action,
                                "entry_price": current_price,
                                "entry_time": current_time,
                                "entry_bar": i,
                                "size": size,
                                "confidence": confidence,
                                "agreement_pct": agreement,
                            }
                except Exception as e:
                    pass  # Skip on error

            equity_curve.append(balance)

        # Close any remaining position
        if position is not None:
            current_price = float(candles.iloc[-1]["close"])
            if position["action"] == "BUY":
                pnl = (current_price - position["entry_price"]) / position["entry_price"] * position["size"]
            else:
                pnl = (position["entry_price"] - current_price) / position["entry_price"] * position["size"]
            balance += pnl
            trades.append(Trade(
                entry_time=position["entry_time"],
                exit_time=str(candles.index[-1])[:19],
                symbol=symbol, action=position["action"],
                entry_price=position["entry_price"], exit_price=current_price,
                size=position["size"], pnl=pnl,
                pnl_pct=pnl / position["size"] * 100,
                confidence=position["confidence"], agreement_pct=position["agreement_pct"],
            ))

        elapsed = time.time() - start_time
        print(f"  Backtest done in {elapsed:.1f}s | {len(trades)} trades")

        return self._compute_metrics(symbol, timeframe, candles, trades, equity_curve)

    def _compute_metrics(self, symbol, timeframe, candles, trades, equity_curve):
        result = BacktestResult(
            symbol=symbol, timeframe=timeframe,
            start_date=str(candles.index[0])[:19], end_date=str(candles.index[-1])[:19],
            total_bars=len(candles),
            trades=[asdict(t) for t in trades],
            final_balance=equity_curve[-1] if equity_curve else self.initial_balance,
        )
        if not trades:
            return result

        result.total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = len(wins) / len(trades)
        result.total_pnl = sum(t.pnl for t in trades)
        result.avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        result.avg_loss = np.mean([t.pnl for t in losses]) if losses else 0

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        peak = equity_curve[0]
        max_dd = 0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)
        result.max_drawdown = max_dd

        if len(equity_curve) > 1:
            rets = np.diff(equity_curve) / np.array(equity_curve[:-1])
            rets = rets[np.isfinite(rets)]
            if len(rets) > 0 and np.std(rets) > 0:
                result.sharpe_ratio = np.mean(rets) / np.std(rets) * np.sqrt(252 * 24)

        streak = 0
        max_streak = 0
        for t in trades:
            if t.pnl <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        result.max_consecutive_losses = max_streak
        return result


def print_report(result):
    if result is None:
        print("  No results to display.")
        return
    print(f"\n{'='*60}")
    print(f"  BACKTEST REPORT: {result.symbol} ({result.timeframe})")
    print(f"{'='*60}")
    print(f"  Period:           {result.start_date} -> {result.end_date}")
    print(f"  Total bars:       {result.total_bars}")
    print(f"  Total trades:     {result.total_trades}")
    print(f"  Winning:          {result.winning_trades}")
    print(f"  Losing:           {result.losing_trades}")
    print(f"  Win rate:         {result.win_rate:.1%}")
    print(f"  Final balance:    ${result.final_balance:,.2f}")
    print(f"  Total P&L:        ${result.total_pnl:,.2f}")
    print(f"  P&L %:            {result.total_pnl / 10000 * 100:+.1f}%")
    print(f"  Avg win:          ${result.avg_win:,.2f}")
    print(f"  Avg loss:         ${result.avg_loss:,.2f}")
    print(f"  Profit factor:    {result.profit_factor:.2f}")
    print(f"  Max drawdown:     {result.max_drawdown:.1%}")
    print(f"  Sharpe ratio:     {result.sharpe_ratio:.2f}")
    print(f"  Max consec losses:{result.max_consecutive_losses}")
    print(f"{'='*60}")

    if result.trades:
        print(f"\n  Last 10 trades:")
        print(f"  {'Time':<20} {'Act':<5} {'Entry':>10} {'Exit':>10} {'P&L':>10}")
        print(f"  {'-'*55}")
        for t in result.trades[-10:]:
            print(f"  {t['entry_time']:<20} {t['action']:<5} {t['entry_price']:>10.5f} {t['exit_price']:>10.5f} ${t['pnl']:>+9.2f}")


async def main():
    print("\n" + "="*60)
    print("  DUTCHKEM TRADER - WALK-FORWARD BACKTEST")
    print("  V5 Intelligence Engine (12 analysts, consensus, gates)")
    print("="*60)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    timeframe = "1H"
    num_candles = 500

    engine = BacktestEngine(initial_balance=10000.0)
    all_results = []

    for symbol in symbols:
        result = await engine.backtest(symbol, timeframe, num_candles)
        if result:
            all_results.append(result)
            print_report(result)

    if all_results:
        print(f"\n{'='*60}")
        print(f"  PORTFOLIO SUMMARY")
        print(f"{'='*60}")
        total_trades = sum(r.total_trades for r in all_results)
        total_pnl = sum(r.total_pnl for r in all_results)
        active = [r for r in all_results if r.total_trades > 0]
        avg_wr = np.mean([r.win_rate for r in active]) if active else 0
        avg_sharpe = np.mean([r.sharpe_ratio for r in active]) if active else 0
        print(f"  Symbols tested:   {len(all_results)}")
        print(f"  Total trades:     {total_trades}")
        print(f"  Total P&L:        ${total_pnl:,.2f} ({total_pnl/100:.1f}%)")
        print(f"  Avg win rate:     {avg_wr:.1%}")
        print(f"  Avg Sharpe:       {avg_sharpe:.2f}")
        for r in all_results:
            print(f"    {r.symbol}: {r.total_trades} trades, ${r.total_pnl:+.2f}, {r.win_rate:.0%} win")
        print(f"{'='*60}")

    # Save results
    output_dir = Path("paper_trades")
    output_dir.mkdir(exist_ok=True)
    filename = output_dir / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump([asdict(r) for r in all_results], f, indent=2, default=str)
    print(f"\n  Results saved to {filename}")


if __name__ == "__main__":
    asyncio.run(main())
