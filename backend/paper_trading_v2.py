"""
Paper Trading Engine V2 — Signal-Agnostic + Improvements
=========================================================
Deterministic trading using technical indicators only.
No LLM calls, no analyst signals — pure math.

Strategy (from 28-instrument optimization + seven improvements):
- MACD, RSI, SMA(20/50), Momentum(5), Bollinger Bands
- Score-based: BUY if score>=3, SELL if score<=-3
- Kelly quarter-sizing, 5% risk per trade (improved from 2%)
- Max position: 30% of balance
- Position hold: 5 bars (H1 = 5 hours)

IMPROVEMENTS APPLIED:
- IMPROVEMENT 3: Volatility-based position sizing (inverse vol scaling)
- IMPROVEMENT 4: Session-based trading (London + NY hours only)

Config: Risk5% + Vol Sizing + Sessions (from combination test)
Expected: $+47.34 P&L (backtest result at 5% risk)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from execution.kelly_sizer import KellySizer

# ─── Config ──────────────────────────────────────────────────
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"

WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP", "EURCHF",
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "US30", "US500", "UK100",
    "AAPL", "AMZN", "NVDA", "TSLA", "META", "MSFT", "GOOGL", "AMD",
]

# Winning config from optimization + seven improvements test
# Base: Risk2% noCB noBad minConf30 → $+17.22
# + Vol Sizing + Sessions + Risk5% → $+47.34 (+$30.12 improvement)
CONFIG = {
    "max_risk_pct": 0.05,        # 5% risk per trade (improved from 2%)
    "circuit_breaker": 99,       # No CB
    "bad_hours": set(),          # No hour filter (session filter replaces this)
    "bad_days": set(),           # No day filter
    "min_confidence": 0.30,      # Min signal strength
    "max_position_pct": 0.30,    # Max 30% of balance per position
    "hold_bars": 5,              # Close after 5 H1 bars
    "kelly_win_rate": 0.55,      # Expected win rate
    "kelly_avg_win": 1.5,        # Expected avg win
    "kelly_avg_loss": 1.0,       # Expected avg loss
    # IMPROVEMENT 3: Volatility-based position sizing
    "vol_sizing": True,          # Scale position by inverse volatility
    # IMPROVEMENT 4: Session-based trading
    "session_hours": set(range(7, 16)) | set(range(13, 22)),  # London + NY
}

TIMEFRAME = "1H"
CYCLE_INTERVAL = 3600  # 1 hour (match H1 candle close)
DURATION_DAYS = 14     # 2 weeks
PAPER_TRADES_DIR = Path("paper_trades")
LOG_FILE = PAPER_TRADES_DIR / "paper_trades_v2.jsonl"
STATE_FILE = PAPER_TRADES_DIR / "paper_trading_state_v2.json"
SUMMARY_FILE = PAPER_TRADES_DIR / "paper_trading_summary_v2.json"


# ─── Signal Generation (Deterministic) ──────────────────────
def compute_indicators(df):
    """Compute all technical indicators."""
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values

    df["sma_5"] = pd.Series(c).rolling(5).mean().values
    df["sma_10"] = pd.Series(c).rolling(10).mean().values
    df["sma_20"] = pd.Series(c).rolling(20).mean().values
    df["sma_50"] = pd.Series(c).rolling(50).mean().values
    df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
    df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = pd.Series(df["macd"]).ewm(span=9).mean().values
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI
    deltas = np.diff(c, prepend=c[0])
    gains = np.where(deltas > 0, deltas, 0)
    losses_arr = np.where(deltas < 0, -deltas, 0)
    avg_gain = pd.Series(gains).rolling(14).mean().values
    avg_loss = pd.Series(losses_arr).rolling(14).mean().values
    rs = np.where(avg_loss > 0.0001, avg_gain / avg_loss, 100)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    bb_std = pd.Series(c).rolling(20).std().values
    df["bb_mid"] = df["sma_20"]
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    # ATR
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    df["atr"] = pd.Series(tr).rolling(14).mean().values

    # Momentum
    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values

    return df


def generate_signal(row):
    """
    Deterministic signal from technical indicators.
    Returns (action, confidence).
    """
    score = 0

    # MACD histogram
    if row["macd_hist"] > 0:
        score += 1
    elif row["macd_hist"] < 0:
        score -= 1

    # RSI
    if row["rsi"] < 35:
        score += 2
    elif row["rsi"] < 45:
        score += 1
    elif row["rsi"] > 65:
        score -= 2
    elif row["rsi"] > 55:
        score -= 1

    # SMA trend
    if row["close"] > row["sma_20"] > row["sma_50"]:
        score += 2
    elif row["close"] < row["sma_20"] < row["sma_50"]:
        score -= 2

    # Momentum
    if row["momentum_5"] > 0.005:
        score += 1
    elif row["momentum_5"] < -0.005:
        score -= 1

    # Bollinger Band position
    if row["close"] < row["bb_lower"]:
        score += 1
    elif row["close"] > row["bb_upper"]:
        score -= 1

    # Decision
    if score >= 3:
        return "BUY", min(score / 6.0, 1.0)
    if score <= -3:
        return "SELL", min(abs(score) / 6.0, 1.0)
    return "HOLD", 0.0


# ─── MT5 Connection ─────────────────────────────────────────
def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"  MT5 FAILED: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    print(f"  MT5 Connected: {info.login} | {info.server} | ${info.balance:.2f}")
    return True


def fetch_latest_candles(symbol, num_candles=200):
    """Fetch latest candles for signal generation."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    if not info.visible:
        mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, num_candles)
    if rates is None or len(rates) < 60:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return df


# ─── Position Tracking ──────────────────────────────────────
class PositionManager:
    """Track open positions and manage entry/exit."""

    def __init__(self):
        self.positions = {}  # symbol -> {action, entry_price, entry_time, entry_bar, size}
        self.trade_log = []
        self.balance = 10000.0
        self.consecutive_losses = 0
        self.kelly = KellySizer()
        self.kelly_frac = self.kelly.calculate(
            win_rate=CONFIG["kelly_win_rate"],
            avg_win=CONFIG["kelly_avg_win"],
            avg_loss=CONFIG["kelly_avg_loss"],
        )

    def open_position(self, symbol, action, price, timestamp, bar_num, volatility=0.01):
        """Open a new position with optional volatility-based sizing."""
        if symbol in self.positions:
            return None  # Already have a position

        # Calculate base size: 5% risk per trade
        risk_amount = self.balance * CONFIG["max_risk_pct"]

        # IMPROVEMENT 3: Volatility-based position sizing
        # Lower volatility = bigger position (inverse scaling)
        if CONFIG.get("vol_sizing", False):
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # Kelly provides additional sizing guidance
        kelly_size = max(10, self.kelly_frac * risk_amount)
        size = min(kelly_size, self.balance * CONFIG["max_position_pct"])

        if size <= 0 or size > self.balance:
            return None

        pos = {
            "action": action,
            "entry_price": price,
            "entry_time": timestamp,
            "entry_bar": bar_num,
            "size": round(size, 2),
        }
        self.positions[symbol] = pos
        return pos

    def close_position(self, symbol, price, timestamp, bar_num):
        """Close a position and record trade."""
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)
        bars_held = bar_num - pos["entry_bar"]

        if pos["action"] == "BUY":
            pnl = (price - pos["entry_price"]) / pos["entry_price"] * pos["size"]
        else:
            pnl = (pos["entry_price"] - price) / pos["entry_price"] * pos["size"]

        self.balance += pnl

        # Track consecutive losses
        if pnl <= 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        trade = {
            "symbol": symbol,
            "action": pos["action"],
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "entry_time": str(pos["entry_time"]),
            "exit_time": str(timestamp),
            "bars_held": bars_held,
            "size": pos["size"],
            "pnl": round(pnl, 2),
            "balance": round(self.balance, 2),
        }
        self.trade_log.append(trade)
        return trade

    def get_state(self):
        """Get current state for persistence."""
        return {
            "balance": self.balance,
            "consecutive_losses": self.consecutive_losses,
            "positions": self.positions,
            "total_trades": len(self.trade_log),
            "total_pnl": round(sum(t["pnl"] for t in self.trade_log), 2),
            "wins": sum(1 for t in self.trade_log if t["pnl"] > 0),
            "losses": sum(1 for t in self.trade_log if t["pnl"] <= 0),
        }

    def load_state(self, state):
        """Restore from saved state."""
        self.balance = state.get("balance", 10000.0)
        self.consecutive_losses = state.get("consecutive_losses", 0)
        self.positions = state.get("positions", {})
        # Trade log not restored (append-only)


# ─── Main Trading Loop ──────────────────────────────────────
def run_cycle(positions, cycle_num, start_time):
    """Run one analysis cycle across all symbols."""
    now = datetime.now(timezone.utc)
    print(f"\n{'='*70}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Balance: ${positions.balance:,.2f} | Open: {len(positions.positions)}")
    print(f"{'='*70}")

    # Fetch data for all symbols
    symbol_data = {}
    for sym in WATCHLIST:
        df = fetch_latest_candles(sym, 200)
        if df is not None and len(df) > 60:
            df = compute_indicators(df)
            df = df.dropna()
            symbol_data[sym] = df

    print(f"  Data loaded: {len(symbol_data)}/{len(WATCHLIST)} symbols")

    # Process each symbol
    for sym, df in symbol_data.items():
        # Get latest bar
        latest = df.iloc[-1]
        bar_num = len(df)
        price = float(latest["close"])

        # Check if we need to close existing position
        if sym in positions.positions:
            pos = positions.positions[sym]
            bars_held = bar_num - pos["entry_bar"]
            if bars_held >= CONFIG["hold_bars"]:
                trade = positions.close_position(sym, price, now, bar_num)
                if trade:
                    m = "+" if trade["pnl"] > 0 else ""
                    print(f"  CLOSE {sym:10} {trade['action']:4} | P&L=${m}{trade['pnl']:.2f} | {trade['bars_held']} bars")
                continue

        # Skip if already have position
        if sym in positions.positions:
            continue

        # IMPROVEMENT 4: Session-based trading
        # Only trade during London (07-16 UTC) and NY (13-22 UTC)
        session_hours = CONFIG.get("session_hours")
        if session_hours and now.hour not in session_hours:
            continue

        # Generate signal
        action, confidence = generate_signal(latest)

        # Skip HOLD or low confidence
        if action == "HOLD" or confidence < CONFIG["min_confidence"]:
            continue

        # IMPROVEMENT 3: Get volatility for position sizing
        volatility = float(latest.get("volatility_10", 0.01))

        # Open new position
        pos = positions.open_position(sym, action, price, now, bar_num, volatility)
        if pos:
            print(f"  OPEN  {sym:10} {action:4} @ {price:.5f} | Size=${pos['size']:.2f} | Conf={confidence:.2f} | Vol={volatility:.4f}")

    # Summary
    active = len(positions.positions)
    total_trades = len(positions.trade_log)
    wins = sum(1 for t in positions.trade_log if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in positions.trade_log)
    wr = wins / total_trades if total_trades > 0 else 0

    print(f"\n  SUMMARY: {active} open | {total_trades} closed | WR={wr:.1%} | P&L=${total_pnl:+.2f}")
    return positions


def save_state(positions):
    """Save state to disk."""
    PAPER_TRADES_DIR.mkdir(exist_ok=True)
    state = positions.get_state()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def save_trade_log(positions):
    """Append new trades to log file."""
    PAPER_TRADES_DIR.mkdir(exist_ok=True)
    # Only write new trades
    existing_count = 0
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            existing_count = sum(1 for _ in f)

    new_trades = positions.trade_log[existing_count:]
    if new_trades:
        with open(LOG_FILE, "a") as f:
            for trade in new_trades:
                f.write(json.dumps(trade, default=str) + "\n")


def save_summary(positions, start_time, total_cycles):
    """Save final summary."""
    PAPER_TRADES_DIR.mkdir(exist_ok=True)
    state = positions.get_state()
    elapsed = datetime.now(timezone.utc) - start_time

    summary = {
        "start_time": start_time.isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_hours": round(elapsed.total_seconds() / 3600, 1),
        "total_cycles": total_cycles,
        "config": CONFIG,
        "watchlist": WATCHLIST,
        "results": state,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n  FINAL SUMMARY:")
    print(f"    Duration: {elapsed.days}d {elapsed.seconds//3600}h")
    print(f"    Cycles: {total_cycles}")
    print(f"    Balance: ${state['balance']:,.2f}")
    print(f"    Trades: {state['total_trades']}")
    print(f"    Wins: {state['wins']} | Losses: {state['losses']}")
    print(f"    Win Rate: {state['wins']/state['total_trades']*100:.1f}%" if state['total_trades'] > 0 else "    Win Rate: 0%")
    print(f"    P&L: ${state['total_pnl']:+.2f}")
    print(f"    Saved to: {SUMMARY_FILE}")


def main():
    print("\n" + "=" * 70)
    print("  DUTCHKEM TRADER - PAPER TRADING V2")
    print("  Signal-Agnostic | Technical Indicators Only | 2% Risk")
    print("=" * 70)
    print(f"  Watchlist: {len(WATCHLIST)} symbols")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Cycle: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60}min)")
    print(f"  Duration: {DURATION_DAYS} days")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  Min confidence: {CONFIG['min_confidence']}")
    print(f"  Circuit breaker: OFF")
    print(f"  Bad hours/days: NONE")

    # Connect MT5
    print("\nConnecting to MT5...")
    if not connect_mt5():
        return

    # Restore or create position manager
    positions = PositionManager()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            positions.load_state(state)
            print(f"\n  Restored state: ${positions.balance:,.2f} | {len(positions.positions)} open positions")
        except Exception as e:
            print(f"\n  Could not restore state: {e}")

    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(days=DURATION_DAYS)
    print(f"\n  Start: {start_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  End:   {end_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"\n  Press Ctrl+C to stop early.\n")

    cycle = 0
    try:
        while datetime.now(timezone.utc) < end_time:
            cycle += 1
            run_cycle(positions, cycle, start_time)
            save_state(positions)
            save_trade_log(positions)

            remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
            if remaining > CYCLE_INTERVAL:
                print(f"\n  Next cycle in {CYCLE_INTERVAL}s | {remaining/3600:.1f}h remaining")
                time.sleep(CYCLE_INTERVAL)
            else:
                print(f"\n  approaching end time, stopping...")
                break

    except KeyboardInterrupt:
        print("\n\n  Paper trading stopped by user.")
    finally:
        mt5.shutdown()
        save_state(positions)
        save_trade_log(positions)
        save_summary(positions, start_time, cycle)
        print("  MT5 disconnected. State saved.")


if __name__ == "__main__":
    main()
