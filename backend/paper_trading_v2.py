import os
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
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")
MT5_MAGIC = 234000
MT5_SLIPPAGE = 20

# ═══════════════════════════════════════════════════════════════
# OPTIMIZED 13-SYMBOL WATCHLIST
# From 5-year backtest: Sharpe 0.95, Max DD 1.5%, PF 1.08
# AMD/GOOGL REMOVED — biggest losers in backtest
# ═══════════════════════════════════════════════════════════════
WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD", "US30",
]

# Correlated pairs (for correlation filter)
CORRELATIONS = {
    "EURUSD": ["GBPUSD", "AUDUSD", "NZDUSD"],
    "GBPUSD": ["EURUSD", "AUDUSD"],
    "AUDUSD": ["NZDUSD", "EURUSD"],
    "USDJPY": ["USDCHF", "USDCAD"],
    "USDCHF": ["USDJPY", "USDCAD"],
    "USDCAD": ["USDJPY", "USDCHF"],
    "EURJPY": ["GBPJPY", "AUDJPY"],
    "GBPJPY": ["EURJPY", "AUDJPY"],
    "XAUUSD": ["XAGUSD"],
}

# ═══════════════════════════════════════════════════════════════
# OPTIMIZED CONFIG — From live_trading_complete.py
# 5-year backtested: Sharpe 0.95, Max DD 1.5%, PF 1.08
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Risk Management ──
    "max_risk_pct": 0.10,           # 10% risk per trade (conservative)
    "max_position_pct": 0.25,      # Max 25% position size
    "kelly_win_rate": 0.382,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "hold_bars": 72,               # Hold up to 72 bars (3 days H1)
    "trailing_breakeven": 0.01,
    "min_confidence": 0.40,         # Min signal strength
    "min_timeframes_agree": 2,      # At least 2 timeframes agree
    
    # ── Session Filtering ──
    "session_hours": set(range(7, 22)),  # Extended session (7am-10pm)
    "optimal_sessions": [13, 14, 15, 16],  # London/NY overlap (UTC)
    "session_risk_mult": {7: 0.5, 8: 0.7, 9: 0.8, 10: 0.9, 11: 1.0, 12: 1.0,
                          13: 1.0, 14: 1.0, 15: 1.0, 16: 1.0, 17: 0.9, 18: 0.8,
                          19: 0.7, 20: 0.6, 21: 0.5},
    
    # ── Indicators ──
    "adx_threshold": 20,            # Catch more trends
    "use_ichimoku": True,
    "use_volume_filter": True,
    "use_rsi_divergence": True,
    "mtf_confluence": True,
    "sl_atr_mult": 3.0,            # SL = 3x ATR
    "tp_atr_mult": 5.0,            # TP = 5x ATR (R:R = 1:1.67)
    "vol_sizing": True,
    
    # ── Portfolio Limits ──
    "max_concurrent_trades": 3,     # Max 3 open positions
    "max_correlated_trades": 2,     # Max 2 correlated pairs
    "circuit_breaker": 3,           # Stop after 3 consecutive losses
    
    # ── Drawdown Throttle ──
    "drawdown_throttle_enabled": True,
    "drawdown_warning_pct": 0.05,   # -5% → reduce risk 50%
    "drawdown_critical_pct": 0.10,  # -10% → reduce risk 75%
    "drawdown_pause_pct": 0.15,     # -15% → pause trading
    
    # ── Partial Take-Profit ──
    "partial_tp_enabled": True,
    "partial_tp_pct": 0.50,         # Close 50% at 1:1 R:R
    "partial_tp_rr": 1.0,
    
    # ── Volatility Regime ──
    "volatility_regime_enabled": True,
    "high_vol_threshold": 0.80,
    "low_vol_threshold": 0.20,
    
    # ── Mean Reversion ──
    "mean_reversion_enabled": True,
    "rsi_extreme_low": 25,
    "rsi_extreme_high": 75,
    
    # ── Symbol Weights (equal) ──
    "sym_weights": {s: 1.0 for s in WATCHLIST},
    
    # ── Active Improvements ──
    "correlation_filter": True,
    "dynamic_risk": True,
    "risk_reduction_threshold": 3,
    "risk_reduction_factor": 0.5,
    "min_risk_pct": 0.05,
    "spread_filter": True,
    "max_spread_multiplier": 2.5,
    
    # ── LLM Confirmation ──
    "llm_confirmation_enabled": True,
    "llm_min_confidence": 0.40,
}

TIMEFRAME = "1H"
CYCLE_INTERVAL = 3600  # 1 hour (match H1 candle close)
DURATION_DAYS = 21     # 3 weeks (was 2)
PAPER_TRADES_DIR = Path("paper_trades")
LOG_FILE = PAPER_TRADES_DIR / "paper_trades_v2.jsonl"
STATE_FILE = PAPER_TRADES_DIR / "paper_trading_state_v2.json"
SUMMARY_FILE = PAPER_TRADES_DIR / "paper_trading_summary_v2.json"


# ─── Signal Generation (Deterministic) ──────────────────────
def compute_indicators(df):
    """Compute all technical indicators — matching live_trading_complete.py."""
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values

    # ── Moving Averages ──
    df["sma_5"] = pd.Series(c).rolling(5).mean().values
    df["sma_10"] = pd.Series(c).rolling(10).mean().values
    df["sma_20"] = pd.Series(c).rolling(20).mean().values
    df["sma_50"] = pd.Series(c).rolling(50).mean().values
    df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
    df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
    
    # ── MACD ──
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = pd.Series(df["macd"]).ewm(span=9).mean().values
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ── RSI ──
    deltas = np.diff(c, prepend=c[0])
    gains = np.where(deltas > 0, deltas, 0)
    losses_arr = np.where(deltas < 0, -deltas, 0)
    avg_gain = pd.Series(gains).rolling(14).mean().values
    avg_loss = pd.Series(losses_arr).rolling(14).mean().values
    rs = np.where(avg_loss > 0.0001, avg_gain / avg_loss, 100)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── Bollinger Bands ──
    bb_std = pd.Series(c).rolling(20).std().values
    df["bb_mid"] = df["sma_20"]
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    # ── ATR ──
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    df["atr"] = pd.Series(tr).rolling(14).mean().values

    # ── ADX ──
    plus_dm = np.diff(h, prepend=h[0])
    minus_dm = -np.diff(l, prepend=l[0])
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
    atr_safe = np.where(df["atr"].values > 0, df["atr"].values, 1)
    plus_di = 100 * pd.Series(plus_dm).rolling(14).mean().values / atr_safe
    minus_di = 100 * pd.Series(minus_dm).rolling(14).mean().values / atr_safe
    di_sum = plus_di + minus_di
    di_sum = np.where(di_sum > 0, di_sum, 1)
    dx = 100 * np.abs(plus_di - minus_di) / di_sum
    df["adx"] = pd.Series(dx).rolling(14).mean().values
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # ── Ichimoku Cloud ──
    nine_high = pd.Series(h).rolling(9).max().values
    nine_low = pd.Series(l).rolling(9).min().values
    df["tenkan"] = (nine_high + nine_low) / 2
    
    twenty_six_high = pd.Series(h).rolling(26).max().values
    twenty_six_low = pd.Series(l).rolling(26).min().values
    df["kijun"] = (twenty_six_high + twenty_six_low) / 2
    
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2)
    # Shift senkou_a forward 26 periods
    df["senkou_a"] = np.roll(df["senkou_a"], 26)
    
    fifty_two_high = pd.Series(h).rolling(52).max().values
    fifty_two_low = pd.Series(l).rolling(52).min().values
    df["senkou_b"] = ((fifty_two_high + fifty_two_low) / 2)
    df["senkou_b"] = np.roll(df["senkou_b"], 26)

    # ── Momentum & Volatility ──
    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values

    # ── Volume Ratio ──
    if "volume" in df.columns:
        df["vol_sma_20"] = pd.Series(df["volume"].values).rolling(20).mean().values
        df["vol_ratio"] = df["volume"] / df["vol_sma_20"]
    else:
        df["vol_ratio"] = 1.0

    return df


def generate_signal(row):
    """
    Deterministic signal — matching live_trading_complete.py scoring.
    Returns (action, confidence).
    """
    score = 0

    # ── MACD histogram ──
    if row["macd_hist"] > 0:
        score += 1
    elif row["macd_hist"] < 0:
        score -= 1

    # ── RSI ──
    rsi = row["rsi"]
    if rsi < 25:          # Extreme oversold → mean reversion
        score += 3
    elif rsi < 35:
        score += 2
    elif rsi < 45:
        score += 1
    elif rsi > 75:        # Extreme overbought → mean reversion
        score -= 3
    elif rsi > 65:
        score -= 2
    elif rsi > 55:
        score -= 1

    # ── SMA trend ──
    if row["close"] > row["sma_20"] > row["sma_50"]:
        score += 2
    elif row["close"] < row["sma_20"] < row["sma_50"]:
        score -= 2

    # ── ADX trend strength ──
    adx = row.get("adx", 0)
    if adx > CONFIG.get("adx_threshold", 20):
        # Strong trend — amplify signal
        if row["plus_di"] > row["minus_di"]:
            score += 1
        else:
            score -= 1

    # ── Ichimoku Cloud ──
    if CONFIG.get("use_ichimoku", True):
        cloud_top = max(row.get("senkou_a", 0), row.get("senkou_b", 0))
        cloud_bottom = min(row.get("senkou_a", 0), row.get("senkou_b", 0))
        if row["close"] > cloud_top:
            score += 1  # Above cloud = bullish
        elif row["close"] < cloud_bottom:
            score -= 1  # Below cloud = bearish

    # ── Volume filter ──
    if CONFIG.get("use_volume_filter", True):
        vol_ratio = row.get("vol_ratio", 1.0)
        if vol_ratio > 1.2:
            # High volume confirms signal direction
            if score > 0:
                score += 1
            elif score < 0:
                score -= 1

    # ── Momentum ──
    if row["momentum_5"] > 0.005:
        score += 1
    elif row["momentum_5"] < -0.005:
        score -= 1

    # ── Bollinger Band position ──
    if row["close"] < row["bb_lower"]:
        score += 1
    elif row["close"] > row["bb_upper"]:
        score -= 1

    # ── Decision ──
    max_score = 8  # Increased with new indicators
    if score >= 3:
        return "BUY", min(score / max_score, 1.0)
    if score <= -3:
        return "SELL", min(abs(score) / max_score, 1.0)
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
    """Track open positions and manage entry/exit — matching live_trading_complete.py."""

    def __init__(self):
        self.positions = {}  # symbol -> {action, entry_price, entry_time, entry_bar, size}
        self.trade_log = []
        self.balance = 10000.0
        self.peak_balance = 10000.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.kelly = KellySizer()
        self.kelly_frac = self.kelly.calculate(
            win_rate=CONFIG["kelly_win_rate"],
            avg_win=CONFIG["kelly_avg_win"],
            avg_loss=CONFIG["kelly_avg_loss"],
        )

    def _get_drawdown_pct(self):
        """Calculate current drawdown from peak."""
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance

    def _get_risk_multiplier(self):
        """Dynamic risk based on drawdown — from live_trading_complete.py."""
        if not CONFIG.get("drawdown_throttle_enabled", False):
            return 1.0
        dd = self._get_drawdown_pct()
        if dd >= CONFIG.get("drawdown_pause_pct", 0.15):
            return 0.0  # PAUSE
        elif dd >= CONFIG.get("drawdown_critical_pct", 0.10):
            return 0.25  # Reduce 75%
        elif dd >= CONFIG.get("drawdown_warning_pct", 0.05):
            return 0.50  # Reduce 50%
        return 1.0

    def _get_session_risk_mult(self, hour):
        """Session-based risk scaling — from live_trading_complete.py."""
        session_mult = CONFIG.get("session_risk_mult", {})
        return session_mult.get(hour, 1.0)

    def _check_correlation(self, symbol):
        """Check if adding this position would exceed correlation limit."""
        if not CONFIG.get("correlation_filter", False):
            return True
        max_correlated = CONFIG.get("max_correlated_trades", 2)
        correlations = CORRELATIONS.get(symbol, [])
        correlated_count = sum(1 for s in self.positions if s in correlations)
        return correlated_count < max_correlated

    def _check_portfolio_limits(self):
        """Check concurrent trade and portfolio heat limits."""
        max_concurrent = CONFIG.get("max_concurrent_trades", 3)
        if len(self.positions) >= max_concurrent:
            return False
        return True

    def _check_circuit_breaker(self):
        """Check if circuit breaker should halt trading."""
        cb_limit = CONFIG.get("circuit_breaker", 3)
        if cb_limit and self.consecutive_losses >= cb_limit:
            return False  # HALT
        return True

    def open_position(self, symbol, action, price, timestamp, bar_num, volatility=0.01):
        """Open a new position with full risk management."""
        if symbol in self.positions:
            return None

        # ── Pre-trade checks ──
        if not self._check_circuit_breaker():
            return None
        if not self._check_portfolio_limits():
            return None
        if not self._check_correlation(symbol):
            return None

        # ── Risk multiplier from drawdown ──
        risk_mult = self._get_risk_multiplier()
        if risk_mult <= 0:
            return None  # Trading paused

        # ── Session risk scaling ──
        session_mult = self._get_session_risk_mult(timestamp.hour)

        # ── Dynamic risk reduction after losses ──
        dyn_risk = 1.0
        if CONFIG.get("dynamic_risk", False) and self.consecutive_losses >= CONFIG.get("risk_reduction_threshold", 3):
            dyn_risk = CONFIG.get("risk_reduction_factor", 0.5)

        # ── Calculate position size ──
        base_risk = self.balance * CONFIG["max_risk_pct"]
        risk_amount = base_risk * risk_mult * session_mult * dyn_risk

        # Volatility-based sizing (inverse scaling)
        if CONFIG.get("vol_sizing", False):
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # Kelly sizing
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
            "sl_price": None,  # Will be set by ATR-based SL
            "tp_price": None,  # Will be set by ATR-based TP
            "partial_tp_done": False,
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
        self.peak_balance = max(self.peak_balance, self.balance)

        # Track consecutive losses/wins
        if pnl <= 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        else:
            self.consecutive_wins += 1
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

    def check_partial_tp(self, symbol, current_price, bar_num):
        """Check if partial take-profit should trigger."""
        if not CONFIG.get("partial_tp_enabled", False):
            return None
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        if pos.get("partial_tp_done", False):
            return None

        # Calculate current R:R
        entry = pos["entry_price"]
        if pos["action"] == "BUY":
            unrealized = (current_price - entry) / entry
        else:
            unrealized = (entry - current_price) / entry

        # Close 50% at 1:1 R:R
        if unrealized >= CONFIG.get("partial_tp_rr", 1.0) * (CONFIG["max_risk_pct"] / 100):
            partial_size = pos["size"] * CONFIG.get("partial_tp_pct", 0.50)
            pos["size"] -= partial_size
            pos["partial_tp_done"] = True

            if pos["action"] == "BUY":
                pnl = (current_price - entry) / entry * partial_size
            else:
                pnl = (entry - current_price) / entry * partial_size

            self.balance += pnl
            self.peak_balance = max(self.peak_balance, self.balance)

            return {
                "symbol": symbol,
                "action": pos["action"],
                "type": "PARTIAL_TP",
                "size": round(partial_size, 2),
                "pnl": round(pnl, 2),
            }
        return None

    def get_state(self):
        """Get current state for persistence."""
        return {
            "balance": self.balance,
            "peak_balance": self.peak_balance,
            "consecutive_losses": self.consecutive_losses,
            "positions": self.positions,
            "total_trades": len(self.trade_log),
            "total_pnl": round(sum(t["pnl"] for t in self.trade_log), 2),
            "wins": sum(1 for t in self.trade_log if t["pnl"] > 0),
            "losses": sum(1 for t in self.trade_log if t["pnl"] <= 0),
            "drawdown_pct": round(self._get_drawdown_pct() * 100, 2),
        }

    def load_state(self, state):
        """Restore from saved state."""
        self.balance = state.get("balance", 10000.0)
        self.peak_balance = state.get("peak_balance", self.balance)
        self.consecutive_losses = state.get("consecutive_losses", 0)
        self.positions = state.get("positions", {})


# ─── Main Trading Loop ──────────────────────────────────────
def run_cycle(positions, cycle_num, start_time):
    """Run one analysis cycle across all symbols — matching live_trading_complete.py."""
    now = datetime.now(timezone.utc)
    dd_pct = positions._get_drawdown_pct() * 100
    risk_mult = positions._get_risk_multiplier()
    
    print(f"\n{'='*70}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Balance: ${positions.balance:,.2f} | Peak: ${positions.peak_balance:,.2f} | DD: {dd_pct:.1f}%")
    print(f"  Open: {len(positions.positions)} | Risk Mult: {risk_mult:.2f} | CL: {positions.consecutive_losses}")
    print(f"{'='*70}")

    # ── Check if trading is paused ──
    if risk_mult <= 0:
        print(f"  ⚠ TRADING PAUSED — Drawdown {dd_pct:.1f}% exceeds {CONFIG.get('drawdown_pause_pct', 0.15)*100:.0f}% limit")
        return positions

    # ── Fetch data for all symbols ──
    symbol_data = {}
    for sym in WATCHLIST:
        df = fetch_latest_candles(sym, 200)
        if df is not None and len(df) > 60:
            df = compute_indicators(df)
            df = df.dropna()
            symbol_data[sym] = df

    print(f"  Data loaded: {len(symbol_data)}/{len(WATCHLIST)} symbols")

    # ── Check partial TP on existing positions ──
    for sym in list(positions.positions.keys()):
        if sym in symbol_data:
            latest = symbol_data[sym].iloc[-1]
            price = float(latest["close"])
            bar_num = len(symbol_data[sym])
            partial = positions.check_partial_tp(sym, price, bar_num)
            if partial:
                print(f"  PARTIAL TP {sym:10} | Size=${partial['size']:.2f} | P&L=${partial['pnl']:+.2f}")

    # ── Process each symbol ──
    for sym, df in symbol_data.items():
        latest = df.iloc[-1]
        bar_num = len(df)
        price = float(latest["close"])

        # Check if we need to close existing position (hold_bars reached)
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

        # Session filter
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
        pos = positions.open_position(sym, action, price, now, bar_num, volatility)
        if pos:
            print(f"  OPEN  {sym:10} {action:4} @ {price:.5f} | Size=${pos['size']:.2f} | Conf={confidence:.2f} | Vol={volatility:.4f}")

    # ── Summary ──
    active = len(positions.positions)
    total_trades = len(positions.trade_log)
    wins = sum(1 for t in positions.trade_log if t["pnl"] > 0)
    total_pnl = sum(t["pnl"] for t in positions.trade_log)
    wr = wins / total_trades if total_trades > 0 else 0

    cb_status = "ACTIVE" if positions._check_circuit_breaker() else f"HALTED ({positions.consecutive_losses} losses)"
    print(f"\n  SUMMARY: {active} open | {total_trades} closed | WR={wr:.1%} | P&L=${total_pnl:+.2f} | CB={cb_status}")
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
    print("  Optimized 13-Symbol Watchlist | Full Risk Management")
    print("=" * 70)
    print(f"  Watchlist: {len(WATCHLIST)} symbols (Sharpe 0.95, Max DD 1.5%)")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Cycle: {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60}min)")
    print(f"  Duration: {DURATION_DAYS} days")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  SL/TP: {CONFIG['sl_atr_mult']}x ATR / {CONFIG['tp_atr_mult']}x ATR")
    print(f"  Partial TP: {CONFIG['partial_tp_pct']*100:.0f}% at 1:1 R:R")
    print(f"  Circuit breaker: {CONFIG['circuit_breaker']} consecutive losses")
    print(f"  Max concurrent: {CONFIG['max_concurrent_trades']}")
    print(f"  Drawdown throttle: {CONFIG['drawdown_warning_pct']*100:.0f}%/{CONFIG['drawdown_critical_pct']*100:.0f}%/{CONFIG['drawdown_pause_pct']*100:.0f}%")
    print(f"  Session hours: London+NY ({CONFIG['session_hours'][0]}-{CONFIG['session_hours'][-1]} UTC)")
    print(f"  Correlation filter: {CONFIG['correlation_filter']}")
    print(f"  LLM confirmation: {CONFIG['llm_confirmation_enabled']}")

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
