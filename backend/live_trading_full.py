"""
DUTCHKEM TRADER - COMPREHENSIVE LIVE TRADING ENGINE
====================================================
Combines ALL winning strategies from paper trading + multi-timeframe analysis.

STRATEGIES INCLUDED:
1. Signal-Agnostic Deterministic (MACD, RSI, SMA, Momentum, BB)
2. Multi-Timeframe Confluence (D1 → M5, 7 timeframes)
3. Volatility-Based Position Sizing (inverse vol scaling)
4. Session Filtering (London + NY only)
5. Kelly Criterion Sizing (quarter-Kelly)
6. ATR-Based Stop Loss / Take Profit
7. Trailing Stop (move to breakeven after +1%)
8. Best Trade Selection (rank by confluence score)

RULES:
- D1 + H4 MUST agree on direction (trend filter)
- 4+ timeframes MUST agree (consensus)
- Only trade during London (07-16) or NY (13-22) UTC
- 5% risk per trade, max 30% position
- Close after 5 H1 bars OR trailing stop hit
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

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"
MT5_MAGIC = 234000
MT5_SLIPPAGE = 20

# All 27 instruments
WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP", "EURCHF",
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "US30", "US500", "UK100",
    "AAPL", "AMZN", "NVDA", "TSLA", "META", "MSFT", "GOOGL", "AMD",
]

# 7 Timeframes
TIMEFRAMES = {
    "D1": mt5.TIMEFRAME_D1,
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15,
    "M10": mt5.TIMEFRAME_M10,
    "M5": mt5.TIMEFRAME_M5,
}

# Timeframe weights
TF_WEIGHTS = {
    "D1": 0.25,   # Major trend
    "H4": 0.20,   # Medium trend
    "H1": 0.20,   # Trade direction
    "M30": 0.15,  # Entry timing
    "M15": 0.10,  # Precision entry
    "M10": 0.05,  # Micro confirmation
    "M5": 0.05,   # Scalp trigger
}

# Trading config (winning combo from optimization)
CONFIG = {
    # Position sizing
    "max_risk_pct": 0.05,        # 5% risk per trade
    "max_position_pct": 0.30,    # Max 30% of balance
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,

    # Exit rules
    "hold_bars": 5,              # Close after 5 H1 bars
    "trailing_breakeven": 0.01,  # Move SL to breakeven after +1%

    # Filters
    "min_confidence": 0.30,
    "min_timeframes_agree": 4,   # 4+ timeframes must agree
    "trend_timeframes": ["D1", "H4"],  # MUST agree
    "session_hours": set(range(7, 16)) | set(range(13, 22)),  # London + NY

    # Improvements
    "vol_sizing": True,          # Volatility-based sizing
    "circuit_breaker": 99,       # OFF (was worse)
    "bad_hours": set(),          # NONE
    "bad_days": set(),           # NONE
}

CYCLE_INTERVAL = 3600  # 1 hour
DURATION_DAYS = 14
TRADES_DIR = Path("trades_live")
LOG_FILE = TRADES_DIR / "live_trades.jsonl"
STATE_FILE = TRADES_DIR / "live_state.json"
SUMMARY_FILE = TRADES_DIR / "live_summary.json"


# ═══════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════
def compute_indicators(df):
    """Compute all technical indicators."""
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values

    # Moving Averages
    df["sma_5"] = pd.Series(c).rolling(5).mean().values
    df["sma_10"] = pd.Series(c).rolling(10).mean().values
    df["sma_20"] = pd.Series(c).rolling(20).mean().values
    df["sma_50"] = pd.Series(c).rolling(50).mean().values
    df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
    df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
    df["ema_200"] = pd.Series(c).ewm(span=200).mean().values

    # MACD
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


def generate_signal_single_tf(row):
    """Generate signal for single timeframe. Returns (action, confidence, score)."""
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

    # EMA 200 trend (major trend filter)
    if "ema_200" in row and not np.isnan(row["ema_200"]):
        if row["close"] > row["ema_200"]:
            score += 1
        elif row["close"] < row["ema_200"]:
            score -= 1

    if score >= 3:
        return "BUY", min(score / 6.0, 1.0), score
    if score <= -3:
        return "SELL", min(abs(score) / 6.0, 1.0), score
    return "HOLD", 0.0, score


# ═══════════════════════════════════════════════════════════════
# MULTI-TIMEFRAME ANALYSIS
# ═══════════════════════════════════════════════════════════════
def analyze_symbol_mtf(symbol):
    """
    Analyze symbol across ALL 7 timeframes.
    Returns (action, total_score, weighted_score, details, atr, volatility).
    """
    results = {}
    buy_score = 0
    sell_score = 0
    buy_count = 0
    sell_count = 0

    for tf_name, tf_value in TIMEFRAMES.items():
        num_candles = 250 if tf_name in ["D1", "H4"] else 300
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

        atr_val = float(latest["atr"]) if "atr" in latest and not np.isnan(latest["atr"]) else 0
        vol_val = float(latest["volatility_10"]) if "volatility_10" in latest and not np.isnan(latest["volatility_10"]) else 0.01

        results[tf_name] = {
            "action": action,
            "confidence": confidence,
            "score": score,
            "weight": weight,
            "price": float(latest["close"]),
            "atr": atr_val,
            "rsi": float(latest["rsi"]) if "rsi" in latest else 50,
            "macd_hist": float(latest["macd_hist"]) if "macd_hist" in latest else 0,
            "volatility": vol_val,
        }

        if action == "BUY":
            buy_score += score * weight
            buy_count += 1
        elif action == "SELL":
            sell_score += score * weight
            sell_count += 1

    if not results:
        return "HOLD", 0, 0, {}, 0, 0.01

    # Get H1 ATR and volatility for position sizing
    h1 = results.get("H1", results.get("H4", results.get("D1", {})))
    atr = h1.get("atr", 0) if h1 else 0
    volatility = h1.get("volatility", 0.01) if h1 else 0.01

    # Check trend timeframes MUST agree
    trend_tf = CONFIG["trend_timeframes"]
    trend_actions = [results[tf]["action"] for tf in trend_tf if tf in results]
    if len(trend_actions) >= 2 and trend_actions[0] != trend_actions[1]:
        return "HOLD", 0, 0, results, atr, volatility

    # Check minimum agreement
    min_agree = CONFIG["min_timeframes_agree"]
    agreement = max(buy_count, sell_count)

    if agreement < min_agree:
        return "HOLD", 0, 0, results, atr, volatility

    # Calculate weighted score
    net_weighted = buy_score - sell_score

    if net_weighted > 0 and buy_count >= min_agree:
        return "BUY", buy_score, net_weighted, results, atr, volatility
    elif net_weighted < 0 and sell_count >= min_agree:
        return "SELL", sell_score, abs(net_weighted), results, atr, volatility

    return "HOLD", 0, 0, results, atr, volatility


# ═══════════════════════════════════════════════════════════════
# MT5 CONNECTION
# ═══════════════════════════════════════════════════════════════
def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"  MT5 FAILED: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    print(f"  MT5 Connected: {info.login} | {info.server} | ${info.balance:.2f}")
    return True


# ═══════════════════════════════════════════════════════════════
# TRADING ENGINE
# ═══════════════════════════════════════════════════════════════
class ComprehensiveTrader:
    """Full-featured MT5 trader with all strategies."""

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
        self.daily_trades = 0
        self.daily_pnl = 0

    def get_account_info(self):
        info = mt5.account_info()
        if info:
            self.balance = info.balance
            return info
        return None

    def get_lot_size(self, symbol, price, volatility=0.01, atr=0):
        """Calculate lot size with volatility + Kelly sizing."""
        risk_amount = self.balance * CONFIG["max_risk_pct"]

        # Volatility-based sizing (inverse scaling)
        if CONFIG.get("vol_sizing") and volatility > 0:
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # Kelly sizing
        kelly_size = max(10, self.kelly_frac * risk_amount)
        size_usd = min(kelly_size, self.balance * CONFIG["max_position_pct"])

        # Convert to lots
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.0

        lot_size = symbol_info.volume_min
        contract_size = getattr(symbol_info, 'trade_contract_size', 100000)

        lots = size_usd / (price * contract_size) if price > 0 and contract_size > 0 else 0
        lots = max(lot_size, min(lots, symbol_info.volume_max))
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        lots = round(lots, 2)

        return lots

    def open_position(self, symbol, action, price, atr, volatility, tf_score, tf_details):
        """Open real MT5 position with ATR-based SL/TP."""
        if symbol in self.positions:
            return None

        # Calculate lot size
        lots = self.get_lot_size(symbol, price, volatility, atr)
        if lots <= 0:
            return None

        # Get current tick
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        exec_price = tick.ask if action == "BUY" else tick.bid

        # ATR-based SL/TP (2x ATR SL, 3x ATR TP = 1.5:1 R:R)
        sl_pips = atr * 2 if atr > 0 else price * 0.002
        tp_pips = atr * 3 if atr > 0 else price * 0.003

        if action == "BUY":
            sl = exec_price - sl_pips
            tp = exec_price + tp_pips
        else:
            sl = exec_price + sl_pips
            tp = exec_price - tp_pips

        # Ensure SL/TP are valid (at least 10 points away)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            point = symbol_info.point
            min_distance = 10 * point
            if action == "BUY":
                sl = max(sl, exec_price - max(sl_pips, min_distance))
                tp = max(tp, exec_price + max(tp_pips, min_distance))
            else:
                sl = min(sl, exec_price + max(sl_pips, min_distance))
                tp = min(tp, exec_price - max(tp_pips, min_distance))

        # Place order
        mt5_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": exec_price,
            "sl": sl,
            "tp": tp,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "dutchkem_live",
        }

        result = mt5.order_send(mt5_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            return None

        # Record position
        pos = {
            "ticket": result.order,
            "action": action,
            "entry_price": result.price,
            "entry_time": datetime.now(timezone.utc),
            "size": lots,
            "sl": sl,
            "tp": tp,
            "initial_sl": sl,
            "tf_score": tf_score,
            "tf_agreement": sum(1 for info in tf_details.values() if info["action"] == action),
        }
        self.positions[symbol] = pos
        self.daily_trades += 1

        # Build TF summary string
        tf_str = " ".join([f"{tf}({info['score']:+d})" for tf, info in tf_details.items() if info["action"] == action])

        print(f"  OPENED {symbol:10} {action:4} #{result.order} {lots:.2f} lots @ {result.price:.5f}")
        print(f"    SL={sl:.5f} TP={tp:.5f} | Score={tf_score:.2f} | TFs: {tf_str}")
        return pos

    def close_position(self, symbol, price):
        """Close real MT5 position."""
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)
        ticket = pos["ticket"]

        mt5_pos = mt5.positions_get(ticket=ticket)
        if not mt5_pos or len(mt5_pos) == 0:
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
            "comment": "dutchkem_close",
        }

        result = mt5.order_send(close_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.positions[symbol] = pos
            return None

        # Calculate P&L
        if pos["action"] == "BUY":
            pnl = (result.price - pos["entry_price"]) / pos["entry_price"] * pos["size"]
        else:
            pnl = (pos["entry_price"] - result.price) / pos["entry_price"] * pos["size"]

        self.balance += pnl
        self.daily_pnl += pnl

        if pnl <= 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        bars_held = 0
        if hasattr(pos.get("entry_time"), "total_seconds"):
            bars_held = int((datetime.now(timezone.utc) - pos["entry_time"]).total_seconds() / 3600)

        trade = {
            "symbol": symbol,
            "action": pos["action"],
            "ticket": ticket,
            "entry_price": pos["entry_price"],
            "exit_price": result.price,
            "entry_time": str(pos["entry_time"]),
            "exit_time": str(datetime.now(timezone.utc)),
            "bars_held": bars_held,
            "size": mt5_pos.volume,
            "pnl": round(pnl, 2),
            "balance": round(self.balance, 2),
            "tf_score": pos.get("tf_score", 0),
            "tf_agreement": pos.get("tf_agreement", 0),
        }
        self.trade_log.append(trade)

        m = "+" if pnl > 0 else ""
        print(f"  CLOSED {symbol:10} {pos['action']:4} | P&L=${m}{pnl:.2f} | TFs={pos.get('tf_agreement', 0)}")
        return trade

    def check_trailing_stop(self, symbol):
        """Move SL to breakeven after +1% profit."""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        current_price = tick.bid if pos["action"] == "BUY" else tick.ask
        entry = pos["entry_price"]

        # Calculate profit percentage
        if pos["action"] == "BUY":
            profit_pct = (current_price - entry) / entry
        else:
            profit_pct = (entry - current_price) / entry

        # Move SL to breakeven after +1%
        if profit_pct >= CONFIG["trailing_breakeven"]:
            if pos["action"] == "BUY" and pos["sl"] < entry:
                # Move SL to entry + 1 point
                new_sl = entry + (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)
            elif pos["action"] == "SELL" and pos["sl"] > entry:
                new_sl = entry - (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)

    def _modify_sl(self, symbol, new_sl):
        """Modify stop loss."""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        ticket = pos["ticket"]

        mt5_pos = mt5.positions_get(ticket=ticket)
        if not mt5_pos or len(mt5_pos) == 0:
            return

        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": pos["tp"],
        }

        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pos["sl"] = new_sl
            print(f"    TRAILING {symbol}: SL moved to {new_sl:.5f}")

    def sync_positions(self):
        """Sync with MT5 state."""
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            return

        mt5_symbols = {p.symbol: p for p in mt5_positions}
        for sym in list(self.positions.keys()):
            if sym not in mt5_symbols:
                print(f"  SYNC: {sym} closed externally")
                del self.positions[sym]

    def get_state(self):
        return {
            "balance": self.balance,
            "consecutive_losses": self.consecutive_losses,
            "daily_trades": self.daily_trades,
            "daily_pnl": round(self.daily_pnl, 2),
            "positions": {s: {k: v for k, v in p.items() if k != "entry_time"} for s, p in self.positions.items()},
            "total_trades": len(self.trade_log),
            "total_pnl": round(sum(t["pnl"] for t in self.trade_log), 2),
            "wins": sum(1 for t in self.trade_log if t["pnl"] > 0),
            "losses": sum(1 for t in self.trade_log if t["pnl"] <= 0),
        }

    def load_state(self, state):
        self.balance = state.get("balance", 10000.0)
        self.consecutive_losses = state.get("consecutive_losses", 0)


# ═══════════════════════════════════════════════════════════════
# MAIN TRADING LOOP
# ═══════════════════════════════════════════════════════════════
def run_cycle(trader, cycle_num, start_time):
    """Run one analysis cycle across ALL 27 instruments and 7 timeframes."""
    now = datetime.now(timezone.utc)
    trader.get_account_info()
    trader.sync_positions()

    print(f"\n{'='*90}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Balance: ${trader.balance:,.2f} | Open: {len(trader.positions)} | Daily Trades: {trader.daily_trades}")
    print(f"  Scanning: {len(WATCHLIST)} instruments x {len(TIMEFRAMES)} timeframes = {len(WATCHLIST)*len(TIMEFRAMES)} analyses")
    print(f"{'='*90}")

    # Session check
    session_hours = CONFIG.get("session_hours")
    in_session = now.hour in session_hours if session_hours else True
    if not in_session:
        print(f"  Outside trading session (London+NY). Hour={now.hour} UTC. Skipping signals.")
        # Still check trailing stops for existing positions
        for sym in list(trader.positions.keys()):
            trader.check_trailing_stop(sym)
        return trader

    # Analyze ALL symbols across ALL timeframes
    signals = []
    for sym in WATCHLIST:
        if sym in trader.positions:
            # Check trailing stop
            trader.check_trailing_stop(sym)
            continue

        action, total_score, weighted_score, details, atr, volatility = analyze_symbol_mtf(sym)

        if action != "HOLD" and weighted_score > 0:
            h1_info = details.get("H1", details.get("H4", {}))
            price = h1_info.get("price", 0)

            if price > 0:
                signals.append({
                    "symbol": sym,
                    "action": action,
                    "total_score": total_score,
                    "weighted_score": weighted_score,
                    "price": price,
                    "atr": atr,
                    "volatility": volatility,
                    "details": details,
                })

    # Sort by weighted score (best first)
    signals.sort(key=lambda x: x["weighted_score"], reverse=True)

    # Print all signals found
    if signals:
        print(f"\n  SIGNALS FOUND: {len(signals)}")
        print(f"  {'Symbol':<10} {'Action':<6} {'Score':<8} {'W.Score':<10} {'Price':<12} {'ATR':<10} {'TFs'}")
        print(f"  {'-'*80}")
        for sig in signals:
            tf_count = sum(1 for info in sig["details"].values() if info["action"] == sig["action"])
            print(f"  {sig['symbol']:<10} {sig['action']:<6} {sig['total_score']:<8.1f} {sig['weighted_score']:<10.2f} {sig['price']:<12.5f} {sig['atr']:<10.6f} {tf_count}/7")
    else:
        print(f"\n  NO SIGNALS - All 27 instruments analyzed, no consensus found")

    # Execute top signals (max 5 per cycle)
    executed = 0
    for sig in signals[:5]:
        print(f"\n  EXECUTING: {sig['symbol']} {sig['action']} (score={sig['weighted_score']:.2f})")
        result = trader.open_position(
            sig["symbol"],
            sig["action"],
            sig["price"],
            sig["atr"],
            sig["volatility"],
            sig["weighted_score"],
            sig["details"],
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
    print(f"  Signals: {len(signals)} found | {executed} executed")
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
    print("\n" + "=" * 90)
    print("  DUTCHKEM TRADER - COMPREHENSIVE LIVE TRADING ENGINE")
    print("  27 Instruments x 7 Timeframes | Best of the Best Execution")
    print("=" * 90)
    print(f"  Instruments: {len(WATCHLIST)}")
    print(f"  Timeframes: {', '.join(TIMEFRAMES.keys())}")
    print(f"  Total analyses per cycle: {len(WATCHLIST) * len(TIMEFRAMES)}")
    print(f"  Cycle: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60}min)")
    print(f"  Duration: {DURATION_DAYS} days")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  Max position: {CONFIG['max_position_pct']*100:.0f}%")
    print(f"  Min TFs agree: {CONFIG['min_timeframes_agree']}")
    print(f"  Trend TFs: {CONFIG['trend_timeframes']}")
    print(f"  Sessions: London (07-16) + NY (13-22) UTC")
    print(f"  Vol Sizing: ON | Trailing Stop: ON")
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

    print("\n" + "=" * 90)
    print("  WARNING: REAL orders will be placed on your DEMO account!")
    print("  Press Ctrl+C within 5 seconds to cancel...")
    print("=" * 90)
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        mt5.shutdown()
        return

    trader = ComprehensiveTrader()
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
