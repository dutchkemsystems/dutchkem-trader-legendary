"""
Multi-Timeframe Live Trading Engine
====================================
Scans ALL timeframes (D1 → M5) and picks the BEST trades.

Timeframe Roles:
- D1/H4: Trend direction (MUST agree)
- H1/M30: Trade direction
- M15/M10/M5: Entry precision

Strategy:
1. Check D1 + H4 trend (must be same direction)
2. Check H1 + M30 signal (confirmation)
3. Check M15/M10/M5 for best entry timing
4. Only execute when 4+ timeframes agree
5. Use ATR from H1 for stop-loss/take-profit
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

# Timeframes to scan
TIMEFRAMES = {
    "D1": mt5.TIMEFRAME_D1,
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15,
    "M10": mt5.TIMEFRAME_M10,
    "M5": mt5.TIMEFRAME_M5,
}

# Timeframe weights for final score
TF_WEIGHTS = {
    "D1": 0.25,
    "H4": 0.20,
    "H1": 0.20,
    "M30": 0.15,
    "M15": 0.10,
    "M10": 0.05,
    "M5": 0.05,
}

CONFIG = {
    "max_risk_pct": 0.05,
    "circuit_breaker": 99,
    "bad_hours": set(),
    "bad_days": set(),
    "min_confidence": 0.30,
    "max_position_pct": 0.30,
    "hold_bars": 5,
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "vol_sizing": True,
    "session_hours": set(range(7, 16)) | set(range(13, 22)),
    # Multi-timeframe settings
    "min_timeframes_agree": 4,      # Minimum 4 timeframes must agree
    "trend_timeframes": ["D1", "H4"],  # These MUST agree
    "entry_timeframes": ["H1", "M30", "M15", "M10", "M5"],
}

TIMEFRAME = "MULTI"
CYCLE_INTERVAL = 3600
DURATION_DAYS = 14
TRADES_DIR = Path("trades_mtf")
LOG_FILE = TRADES_DIR / "mtf_trades.jsonl"
STATE_FILE = TRADES_DIR / "mtf_trading_state.json"
SUMMARY_FILE = TRADES_DIR / "mtf_trading_summary.json"


# ─── Multi-Timeframe Signal Generation ─────────────────────
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

    # EMA 200 (for major trend)
    df["ema_200"] = pd.Series(c).ewm(span=200).mean().values

    return df


def generate_signal_single_tf(row):
    """Generate signal for a single timeframe. Returns (action, confidence, score)."""
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

    # EMA 200 trend (D1/H4 only - stronger signal)
    if "ema_200" in row and not np.isnan(row["ema_200"]):
        if row["close"] > row["ema_200"]:
            score += 1
        elif row["close"] < row["ema_200"]:
            score -= 1

    # Decision
    if score >= 3:
        return "BUY", min(score / 6.0, 1.0), score
    if score <= -3:
        return "SELL", min(abs(score) / 6.0, 1.0), score
    return "HOLD", 0.0, score


def generate_multitimeframe_signal(symbol):
    """
    Generate signal across ALL timeframes.
    Returns (final_action, total_score, timeframe_details).
    """
    results = {}
    buy_score = 0
    sell_score = 0
    buy_count = 0
    sell_count = 0
    total_weight = 0

    for tf_name, tf_value in TIMEFRAMES.items():
        # Fetch candles for this timeframe
        num_candles = 200 if tf_name in ["D1", "H4"] else 300
        rates = mt5.copy_rates_from_pos(symbol, tf_value, 0, num_candles)
        if rates is None or len(rates) < 60:
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        df = compute_indicators(df)
        df = df.dropna()

        if len(df) < 10:
            continue

        latest = df.iloc[-1]
        action, confidence, score = generate_signal_single_tf(latest)
        weight = TF_WEIGHTS.get(tf_name, 0.1)

        results[tf_name] = {
            "action": action,
            "confidence": confidence,
            "score": score,
            "weight": weight,
            "price": float(latest["close"]),
            "atr": float(latest["atr"]) if "atr" in latest else 0,
            "rsi": float(latest["rsi"]) if "rsi" in latest else 50,
        }

        # Accumulate weighted scores
        if action == "BUY":
            buy_score += score * weight
            buy_count += 1
        elif action == "SELL":
            sell_score += score * weight
            sell_count += 1

        total_weight += weight

    # Calculate final score
    if total_weight == 0:
        return "HOLD", 0, results

    net_score = buy_score - sell_score
    agreement = max(buy_count, sell_count)

    # Check if minimum timeframes agree
    min_agree = CONFIG["min_timeframes_agree"]
    if agreement < min_agree:
        return "HOLD", 0, results

    # Check trend timeframes MUST agree
    trend_tf = CONFIG["trend_timeframes"]
    trend_actions = [results[tf]["action"] for tf in trend_tf if tf in results]
    if len(trend_actions) >= 2:
        if trend_actions[0] != trend_actions[1]:
            return "HOLD", 0, results  # Trend timeframes disagree

    # Final decision
    if net_score > 0 and buy_count >= min_agree:
        return "BUY", net_score, results
    elif net_score < 0 and sell_count >= min_agree:
        return "SELL", abs(net_score), results

    return "HOLD", 0, results


# ─── MT5 Connection ─────────────────────────────────────────
def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"  MT5 FAILED: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    print(f"  MT5 Connected: {info.login} | {info.server} | ${info.balance:.2f}")
    return True


# ─── Real MT5 Order Execution ──────────────────────────────
class MT5TraderMTF:
    """Real MT5 order execution with multi-timeframe analysis."""

    def __init__(self):
        self.positions = {}
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
        info = mt5.account_info()
        if info:
            self.balance = info.balance
            return info
        return None

    def get_lot_size(self, symbol, price, volatility=0.01, atr=0.001):
        """Calculate lot size based on risk, volatility, ATR, and symbol weights."""
        risk_amount = self.balance * CONFIG["max_risk_pct"]

        # Apply symbol weight (optimized from Round 8)
        sym_weights = CONFIG.get("sym_weights", {})
        weight = sym_weights.get(symbol, 1.0)
        risk_amount *= weight

        # Volatility-based sizing
        if CONFIG.get("vol_sizing", False):
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # ATR-based sizing (tighter stop = bigger position)
        if atr > 0:
            atr_factor = max(0.5, min(2.0, 0.001 / atr))  # Normalize to 10 pips
            risk_amount *= atr_factor

        kelly_size = max(10, self.kelly_frac * risk_amount)
        size_usd = min(kelly_size, self.balance * CONFIG["max_position_pct"])

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.0

        lot_size = symbol_info.volume_min
        contract_size = symbol_info.trade_contract_size if hasattr(symbol_info, 'trade_contract_size') else 100000

        lots = size_usd / (price * contract_size)
        lots = max(lot_size, min(lots, symbol_info.volume_max))
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        lots = round(lots, 2)

        return lots

    def open_position(self, symbol, action, price, bar_num, volatility=0.01, atr=0.001, tf_details=None):
        """Open a real MT5 position."""
        if symbol in self.positions:
            print(f"  SKIP {symbol}: Already have position")
            return None

        lots = self.get_lot_size(symbol, price, volatility, atr)
        if lots <= 0:
            print(f"  SKIP {symbol}: Invalid lot size {lots}")
            return None

        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"  SKIP {symbol}: Cannot get tick")
            return None

        exec_price = tick.ask if action == "BUY" else tick.bid

        # Calculate SL/TP using ATR
        sl_pips = atr * 2 if atr > 0 else 0.002  # 2x ATR
        tp_pips = atr * 3 if atr > 0 else 0.003  # 3x ATR (1.5:1 R:R)

        if action == "BUY":
            sl = exec_price - sl_pips
            tp = exec_price + tp_pips
        else:
            sl = exec_price + sl_pips
            tp = exec_price - tp_pips

        mt5_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": exec_price,
            "sl": sl,
            "tp": tp,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "dutchkem_mtf",
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
            "sl": sl,
            "tp": tp,
            "tf_agreement": len(tf_details) if tf_details else 0,
        }
        self.positions[symbol] = pos

        # Print timeframe details
        tf_str = ""
        if tf_details:
            for tf, info in tf_details.items():
                if info["action"] == action:
                    tf_str += f" {tf}({info['score']:+d})"

        print(f"  OPENED {symbol:10} {action:4} #{result.order} {lots:.2f} lots @ {result.price:.5f}")
        print(f"    SL={sl:.5f} TP={tp:.5f} | TFs:{tf_str}")
        return pos

    def close_position(self, symbol, price, bar_num):
        """Close a real MT5 position."""
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)
        ticket = pos["ticket"]

        mt5_pos = mt5.positions_get(ticket=ticket)
        if not mt5_pos or len(mt5_pos) == 0:
            print(f"  CLOSE FAILED {symbol}: Position {ticket} not found")
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
            "comment": "dutchkem_mtf close",
        }

        result = mt5.order_send(close_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            print(f"  CLOSE FAILED {symbol}: {err}")
            self.positions[symbol] = pos
            return None

        bars_held = bar_num - pos["entry_bar"]
        if pos["action"] == "BUY":
            pnl = (result.price - pos["entry_price"]) / pos["entry_price"] * pos["size"]
        else:
            pnl = (pos["entry_price"] - result.price) / pos["entry_price"] * pos["size"]

        self.balance += pnl
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
            "tf_agreement": pos.get("tf_agreement", 0),
        }
        self.trade_log.append(trade)

        m = "+" if pnl > 0 else ""
        print(f"  CLOSED {symbol:10} {pos['action']:4} | P&L=${m}{pnl:.2f} | {bars_held} bars | TFs={pos.get('tf_agreement', 0)}")
        return trade

    def sync_positions(self):
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            return
        mt5_symbols = {p.symbol: p for p in mt5_positions}
        for sym in list(self.positions.keys()):
            if sym not in mt5_symbols:
                print(f"  SYNC: Position {sym} no longer in MT5")
                del self.positions[sym]

    def get_state(self):
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
        self.balance = state.get("balance", 10000.0)
        self.consecutive_losses = state.get("consecutive_losses", 0)


# ─── Main Trading Loop ──────────────────────────────────────
def run_cycle(trader, cycle_num, start_time):
    """Run one analysis cycle across all symbols and timeframes."""
    now = datetime.now(timezone.utc)
    trader.get_account_info()
    trader.sync_positions()

    print(f"\n{'='*80}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Balance: ${trader.balance:,.2f} | Open: {len(trader.positions)}")
    print(f"  Timeframes: D1 H4 H1 M30 M15 M10 M5 (7 TFs)")
    print(f"{'='*80}")

    # Analyze each symbol across all timeframes
    signals = []
    for sym in WATCHLIST:
        # Skip if already have position
        if sym in trader.positions:
            continue

        # Session filter
        session_hours = CONFIG.get("session_hours")
        if session_hours and now.hour not in session_hours:
            continue

        # Multi-timeframe analysis
        action, score, tf_details = generate_multitimeframe_signal(sym)

        if action != "HOLD" and score > 0:
            # Get volatility and ATR from H1
            h1_info = tf_details.get("H1", {})
            volatility = 0.01
            atr = 0.001
            price = 0
            if h1_info:
                volatility = h1_info.get("atr", 0.001) / h1_info.get("price", 1.0) if h1_info.get("price", 0) > 0 else 0.01
                atr = h1_info.get("atr", 0.001)
                price = h1_info.get("price", 0)

            if price > 0:
                signals.append({
                    "symbol": sym,
                    "action": action,
                    "score": score,
                    "price": price,
                    "volatility": volatility,
                    "atr": atr,
                    "tf_details": tf_details,
                })

    # Sort by score (best first)
    signals.sort(key=lambda x: x["score"], reverse=True)

    # Execute top signals (max 5 per cycle)
    executed = 0
    for sig in signals[:5]:
        print(f"\n  SIGNAL: {sig['symbol']} {sig['action']} (score={sig['score']:.2f})")
        result = trader.open_position(
            sig["symbol"],
            sig["action"],
            sig["price"],
            len(tf_details),
            sig["volatility"],
            sig["atr"],
            sig["tf_details"],
        )
        if result:
            executed += 1

    # Summary
    active = len(trader.positions)
    total_trades = len(trader.trade_log)
    wins = sum(1 for t in trader.trade_log if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in trader.trade_log)
    wr = wins / total_trades if total_trades > 0 else 0

    print(f"\n  SUMMARY: {active} open | {total_trades} closed | WR={wr:.1%} | P&L=${total_pnl:+.2f}")
    print(f"  Signals found: {len(signals)} | Executed: {executed}")
    return trader


def save_state(trader):
    TRADES_DIR.mkdir(exist_ok=True)
    state = trader.get_state()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def save_trade_log(trader):
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
    TRADES_DIR.mkdir(exist_ok=True)
    state = trader.get_state()
    elapsed = datetime.now(timezone.utc) - start_time
    summary = {
        "start_time": start_time.isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_hours": round(elapsed.total_seconds() / 3600, 1),
        "total_cycles": total_cycles,
        "config": CONFIG,
        "timeframes": list(TIMEFRAMES.keys()),
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
    print("\n" + "=" * 80)
    print("  DUTCHKEM TRADER - MULTI-TIMEFRAME LIVE TRADING")
    print("  7 Timeframes | D1→M5 | Best of the Best Execution")
    print("=" * 80)
    print(f"  Watchlist: {len(WATCHLIST)} symbols")
    print(f"  Timeframes: {', '.join(TIMEFRAMES.keys())}")
    print(f"  Cycle: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60}min)")
    print(f"  Duration: {DURATION_DAYS} days")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  Min TFs agree: {CONFIG['min_timeframes_agree']}")
    print(f"  Trend TFs: {CONFIG['trend_timeframes']}")
    print(f"  Mode: LIVE (real MT5 orders)")
    print(f"  Magic: {MT5_MAGIC}")

    print("\nConnecting to MT5...")
    if not connect_mt5():
        return

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

    print("\n" + "=" * 80)
    print("  WARNING: This will place REAL orders on your DEMO account!")
    print("  Press Ctrl+C within 5 seconds to cancel...")
    print("=" * 80)
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        mt5.shutdown()
        return

    trader = MT5TraderMTF()
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
        print("\n\n  Multi-timeframe trading stopped by user.")
    finally:
        mt5.shutdown()
        save_state(trader)
        save_trade_log(trader)
        save_summary(trader, start_time, cycle)
        print("  MT5 disconnected. State saved.")


if __name__ == "__main__":
    main()
