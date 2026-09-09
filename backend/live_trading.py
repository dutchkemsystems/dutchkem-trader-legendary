"""
Live Trading Engine — Real MT5 Order Execution
================================================
Uses V2 signal-agnostic strategy with real MT5 orders.

Strategy (deterministic):
- MACD, RSI, SMA(20/50), Momentum(5), Bollinger Bands
- Score-based: BUY if score>=3, SELL if score<=-3
- Kelly quarter-sizing, 5% risk per trade
- Max position: 30% of balance
- Position hold: 5 bars (H1 = 5 hours)
- Volatility-based sizing + Session filter (London + NY)

IMPROVEMENTS APPLIED:
- Volatility-based position sizing (inverse vol scaling)
- Session-based trading (London + NY hours only)

MT5 Settings:
- Account: 476963617 (Exness-MT5Trial9 Demo)
- Magic: 234000
- Slippage: 20
- Comment: dutchkem
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal

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
MT5_MAGIC = 234000
MT5_SLIPPAGE = 20

WATCHLIST = [
    # OPTIMIZED: Round 8 production config (2026-09-10)
    # Excluded: NVDA, XAGUSD, US500, UK100, TSLA, AAPL, ETHUSD, BTCUSD, MSFT, META, AMZN
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD",
    "US30",
    "AMD", "GOOGL",
]

CONFIG = {
    # ═══════════════════════════════════════════════════════════════
    # OPTIMIZED PRODUCTION CONFIG (Round 8 - 2026-09-10)
    # Best result: +$597.01 P&L, 50.4% WR, 478 trades
    # Key: risk50 + no circuit breaker + AMD focus
    # ═══════════════════════════════════════════════════════════════
    "max_risk_pct": 0.50,           # 50% risk per trade (optimized)
    "circuit_breaker": 99,          # No circuit breaker (let winners run)
    "bad_hours": set(),             # No hour filter
    "bad_days": set(),              # No day filter
    "min_confidence": 0.30,         # Min signal strength
    "max_position_pct": 0.50,      # Max 50% of balance per position
    "hold_bars": 10,               # Hold 10 bars (optimized)
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "vol_sizing": True,
    "session_hours": set(range(7, 22)),  # Extended session (7am-10pm)
    # SYMBOL WEIGHTS: Optimized from Round 8
    "sym_weights": {
        "AMD": 3.0,      # Consistently biggest winner
        "GOOGL": 1.0,
        "XAUUSD": 1.0,
        "USDJPY": 1.0,
        "EURJPY": 1.0,
        "GBPJPY": 1.0,
        "NZDUSD": 1.0,
        "USDCAD": 1.0,
        "AUDJPY": 1.0,
        "USDCHF": 1.0,
        "US30": 1.0,
        "EURUSD": 1.0,
        "GBPUSD": 1.0,
        "AUDUSD": 1.0,
        "EURGBP": 1.0,
    },
}

TIMEFRAME = "1H"
CYCLE_INTERVAL = 3600  # 1 hour (match H1 candle close)
DURATION_DAYS = 14     # 2 weeks
TRADES_DIR = Path("trades")
LOG_FILE = TRADES_DIR / "live_trades.jsonl"
STATE_FILE = TRADES_DIR / "live_trading_state.json"
SUMMARY_FILE = TRADES_DIR / "live_trading_summary.json"


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
    """Deterministic signal from technical indicators. Returns (action, confidence)."""
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


# ─── Real MT5 Order Execution ──────────────────────────────
class MT5Trader:
    """Real MT5 order execution with position tracking."""

    def __init__(self):
        self.positions = {}  # symbol -> {ticket, action, entry_price, entry_time, entry_bar, size}
        self.trade_log = []
        self.balance = 10000.0
        self.consecutive_losses = 0
        self.kelly = KellySizer()
        self.kelly_frac = self.kelly.calculate(
            win_rate=CONFIG["kelly_win_rate"],
            avg_win=CONFIG["kelly_avg_win"],
            avg_loss=CONFIG["kelly_avg_loss"],
        )

    def get_account_info(self):
        """Get current MT5 account info."""
        info = mt5.account_info()
        if info:
            self.balance = info.balance
            return info
        return None

    def get_lot_size(self, symbol, price, volatility=0.01):
        """Calculate lot size based on risk, volatility, and symbol weight."""
        # Base risk per trade
        risk_amount = self.balance * CONFIG["max_risk_pct"]

        # Apply symbol weight (optimized from Round 8)
        sym_weights = CONFIG.get("sym_weights", {})
        weight = sym_weights.get(symbol, 1.0)
        risk_amount *= weight

        # Volatility-based sizing (inverse scaling)
        if CONFIG.get("vol_sizing", False):
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # Kelly sizing
        kelly_size = max(10, self.kelly_frac * risk_amount)
        size_usd = min(kelly_size, self.balance * CONFIG["max_position_pct"])

        # Convert USD to lots
        # For forex: 1 lot = 100,000 units, value = price * 100,000
        # For stocks: 1 lot = 100 shares (varies by broker)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.0

        lot_size = symbol_info.volume_min
        contract_size = symbol_info.trade_contract_size if hasattr(symbol_info, 'trade_contract_size') else 100000

        # Calculate lots
        lots = size_usd / (price * contract_size)
        lots = max(lot_size, min(lots, symbol_info.volume_max))
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        lots = round(lots, 2)

        return lots

    def open_position(self, symbol, action, price, bar_num, volatility=0.01):
        """Open a real MT5 position."""
        if symbol in self.positions:
            print(f"  SKIP {symbol}: Already have position")
            return None

        # Calculate lot size
        lots = self.get_lot_size(symbol, price, volatility)
        if lots <= 0:
            print(f"  SKIP {symbol}: Invalid lot size {lots}")
            return None

        # Place order
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"  SKIP {symbol}: Cannot get tick")
            return None

        exec_price = tick.ask if action == "BUY" else tick.bid

        mt5_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": exec_price,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "dutchkem",
        }

        result = mt5.order_send(mt5_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            code = result.retcode if result else "N/A"
            print(f"  FAILED {symbol}: {err} (code={code})")
            return None

        # Record position
        pos = {
            "ticket": result.order,
            "action": action,
            "entry_price": result.price,
            "entry_time": datetime.now(timezone.utc),
            "entry_bar": bar_num,
            "size": lots,
        }
        self.positions[symbol] = pos

        print(f"  OPENED {symbol:10} {action:4} #{result.order} {lots:.2f} lots @ {result.price:.5f}")
        return pos

    def close_position(self, symbol, price, bar_num):
        """Close a real MT5 position."""
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)
        ticket = pos["ticket"]

        # Get current position info
        mt5_pos = mt5.positions_get(ticket=ticket)
        if not mt5_pos or len(mt5_pos) == 0:
            print(f"  CLOSE FAILED {symbol}: Position {ticket} not found in MT5")
            return None

        mt5_pos = mt5_pos[0]
        close_type = mt5.ORDER_TYPE_SELL if mt5_pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        close_price = tick.bid if mt5_pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        close_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": mt5_pos.volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "dutchkem close",
        }

        result = mt5.order_send(close_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            print(f"  CLOSE FAILED {symbol}: {err}")
            # Keep position in tracking
            self.positions[symbol] = pos
            return None

        # Calculate P&L
        bars_held = bar_num - pos["entry_bar"]
        if pos["action"] == "BUY":
            pnl = (result.price - pos["entry_price"]) / pos["entry_price"] * pos["size"]
        else:
            pnl = (pos["entry_price"] - result.price) / pos["entry_price"] * pos["size"]

        self.balance += pnl

        # Track consecutive losses
        if pnl <= 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        trade = {
            "symbol": symbol,
            "action": pos["action"],
            "ticket_open": ticket,
            "ticket_close": result.order,
            "entry_price": pos["entry_price"],
            "exit_price": result.price,
            "entry_time": str(pos["entry_time"]),
            "exit_time": str(datetime.now(timezone.utc)),
            "bars_held": bars_held,
            "size": mt5_pos.volume,
            "pnl": round(pnl, 2),
            "balance": round(self.balance, 2),
        }
        self.trade_log.append(trade)

        m = "+" if pnl > 0 else ""
        print(f"  CLOSED {symbol:10} {pos['action']:4} | P&L=${m}{pnl:.2f} | {bars_held} bars")
        return trade

    def sync_positions(self):
        """Sync tracked positions with MT5 state."""
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            return

        mt5_symbols = {p.symbol: p for p in mt5_positions}

        # Remove positions that no longer exist in MT5
        for sym in list(self.positions.keys()):
            if sym not in mt5_symbols:
                print(f"  SYNC: Position {sym} no longer in MT5, removing from tracking")
                del self.positions[sym]

    def get_state(self):
        """Get current state for persistence."""
        return {
            "balance": self.balance,
            "consecutive_losses": self.consecutive_losses,
            "positions": {s: {k: v for k, v in p.items() if k != "entry_time"} for s, p in self.positions.items()},
            "total_trades": len(self.trade_log),
            "total_pnl": round(sum(t["pnl"] for t in self.trade_log), 2),
            "wins": sum(1 for t in self.trade_log if t["pnl"] > 0),
            "losses": sum(1 for t in self.trade_log if t["pnl"] <= 0),
        }

    def load_state(self, state):
        """Restore from saved state."""
        self.balance = state.get("balance", 10000.0)
        self.consecutive_losses = state.get("consecutive_losses", 0)
        # Note: MT5 positions are restored from MT5 itself, not from state


# ─── Main Trading Loop ──────────────────────────────────────
def run_cycle(trader, cycle_num, start_time):
    """Run one analysis cycle across all symbols."""
    now = datetime.now(timezone.utc)
    trader.get_account_info()
    trader.sync_positions()

    print(f"\n{'='*70}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Balance: ${trader.balance:,.2f} | Open: {len(trader.positions)}")
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
        latest = df.iloc[-1]
        bar_num = len(df)
        price = float(latest["close"])

        # Check if we need to close existing position
        if sym in trader.positions:
            pos = trader.positions[sym]
            bars_held = bar_num - pos["entry_bar"]
            if bars_held >= CONFIG["hold_bars"]:
                trader.close_position(sym, price, bar_num)
                continue

        # Skip if already have position
        if sym in trader.positions:
            continue

        # Session filter (London + NY hours only)
        session_hours = CONFIG.get("session_hours")
        if session_hours and now.hour not in session_hours:
            continue

        # Generate signal
        action, confidence = generate_signal(latest)

        # Skip HOLD or low confidence
        if action == "HOLD" or confidence < CONFIG["min_confidence"]:
            continue

        # Get volatility for position sizing
        volatility = float(latest.get("volatility_10", 0.01))

        # Open new position
        trader.open_position(sym, action, price, bar_num, volatility)

    # Summary
    active = len(trader.positions)
    total_trades = len(trader.trade_log)
    wins = sum(1 for t in trader.trade_log if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in trader.trade_log)
    wr = wins / total_trades if total_trades > 0 else 0

    print(f"\n  SUMMARY: {active} open | {total_trades} closed | WR={wr:.1%} | P&L=${total_pnl:+.2f}")
    return trader


def save_state(trader):
    """Save state to disk."""
    TRADES_DIR.mkdir(exist_ok=True)
    state = trader.get_state()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def save_trade_log(trader):
    """Append new trades to log file."""
    TRADES_DIR.mkdir(exist_ok=True)
    existing_count = 0
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            existing_count = sum(1 for _ in f)

    new_trades = trader.trade_log[existing_count:]
    if new_trades:
        with open(LOG_FILE, "a") as f:
            for trade in new_trades:
                f.write(json.dumps(trade, default=str) + "\n")


def save_summary(trader, start_time, total_cycles):
    """Save final summary."""
    TRADES_DIR.mkdir(exist_ok=True)
    state = trader.get_state()
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
    wr = state['wins']/state['total_trades']*100 if state['total_trades'] > 0 else 0
    print(f"    Win Rate: {wr:.1f}%")
    print(f"    P&L: ${state['total_pnl']:+.2f}")
    print(f"    Saved to: {SUMMARY_FILE}")


def main():
    print("\n" + "=" * 70)
    print("  DUTCHKEM TRADER - LIVE TRADING (REAL MT5 ORDERS)")
    print("  Signal-Agnostic | Technical Indicators Only | 5% Risk")
    print("=" * 70)
    print(f"  Watchlist: {len(WATCHLIST)} symbols")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Cycle: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60}min)")
    print(f"  Duration: {DURATION_DAYS} days")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  Min confidence: {CONFIG['min_confidence']}")
    print(f"  Circuit breaker: OFF")
    print(f"  Bad hours/days: NONE")
    print(f"  Mode: LIVE (real MT5 orders)")
    print(f"  Magic: {MT5_MAGIC}")

    # Connect MT5
    print("\nConnecting to MT5...")
    if not connect_mt5():
        return

    # Verify account
    info = mt5.account_info()
    if info is None:
        print("  FAILED: Cannot get account info")
        mt5.shutdown()
        return

    print(f"\n  Account: {info.login}")
    print(f"  Server: {info.server}")
    print(f"  Balance: ${info.balance:,.2f}")
    print(f"  Free Margin: ${info.margin_free:,.2f}")
    print(f"  Leverage: 1:{info.leverage}")

    # Confirm before trading
    print("\n" + "=" * 70)
    print("  WARNING: This will place REAL orders on your DEMO account!")
    print("  Press Ctrl+C within 5 seconds to cancel...")
    print("=" * 70)
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        mt5.shutdown()
        return

    # Create trader
    trader = MT5Trader()
    trader.balance = info.balance

    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(days=DURATION_DAYS)
    print(f"\n  Start: {start_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  End:   {end_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"\n  Press Ctrl+C to stop early.\n")

    cycle = 0
    try:
        while datetime.now(timezone.utc) < end_time:
            cycle += 1
            run_cycle(trader, cycle, start_time)
            save_state(trader)
            save_trade_log(trader)

            remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
            if remaining > CYCLE_INTERVAL:
                print(f"\n  Next cycle in {CYCLE_INTERVAL}s | {remaining/3600:.1f}h remaining")
                time.sleep(CYCLE_INTERVAL)
            else:
                print(f"\n  approaching end time, stopping...")
                break

    except KeyboardInterrupt:
        print("\n\n  Live trading stopped by user.")
    finally:
        mt5.shutdown()
        save_state(trader)
        save_trade_log(trader)
        save_summary(trader, start_time, cycle)
        print("  MT5 disconnected. State saved.")


if __name__ == "__main__":
    main()
