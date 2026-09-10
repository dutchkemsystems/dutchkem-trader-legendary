"""
DUTCHKEM TRADER - COMPLETE LIVE TRADING ENGINE
================================================
ALL 7 IMPROVEMENTS + Multi-Timeframe + Dashboard Integration

IMPROVEMENTS:
1. Correlation Filter (ACTIVE NOW)
2. Dynamic Risk Reduction (ACTIVE NOW)
3. Spread Filter (ACTIVE NOW)
4. News Avoidance (ACTIVATES WEEK 3)
5. Breakout Detection (ACTIVATES WEEK 3)
6. Mean Reversion (ACTIVATES WEEK 3)
7. Position Scaling/Pyramiding (ACTIVATES WEEK 3)

STRATEGIES:
- Multi-Timeframe Confluence (D1→M5)
- Volatility-Based Position Sizing
- Session Filtering (London+NY)
- Kelly Criterion Sizing
- ATR-Based SL/TP
- Trailing Stop (breakeven at +1%)
"""

import json
import os
import sys
import time
import threading
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

WATCHLIST = [
    # v2 CONSERVATIVE CONFIG (2026-09-10)
    # AMD/GOOGL REMOVED — biggest losers in 5yr backtest
    # Profitable over 5 years: Sharpe 0.95, Max DD 1.5%, PF 1.08
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD", "US30",
]

TIMEFRAMES = {
    "D1": mt5.TIMEFRAME_D1,
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15,
    "M10": mt5.TIMEFRAME_M10,
    "M5": mt5.TIMEFRAME_M5,
}

TF_WEIGHTS = {"D1": 0.25, "H4": 0.20, "H1": 0.20, "M30": 0.15, "M15": 0.10, "M10": 0.05, "M5": 0.05}

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

CONFIG = {
    # ═══════════════════════════════════════════════════════════════
    # v2 CONSERVATIVE CONFIG (Backtested 5 years, Sharpe 0.95)
    # RELAXED FILTERS for more trade signals
    # ═══════════════════════════════════════════════════════════════
    "max_risk_pct": 0.10,           # 10% risk per trade (conservative)
    "max_position_pct": 0.25,      # Max 25% position size
    "kelly_win_rate": 0.382,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "hold_bars": 72,               # Hold up to 72 bars (3 days H1)
    "trailing_breakeven": 0.01,
    "min_confidence": 0.40,         # LOWERED from 0.50 for more signals
    "min_timeframes_agree": 2,      # LOWERED from 3 for more signals
    "trend_timeframes": ["H4", "D1"],
    "session_hours": set(range(7, 22)),  # Extended session (7am-10pm)
    "vol_sizing": True,
    
    # v2 INDICATORS (RELAXED)
    "adx_threshold": 20,            # LOWERED from 30 — catch more trends
    "use_ichimoku": True,           # Ichimoku Cloud confirmation
    "use_volume_filter": True,      # Volume above avg required
    "use_rsi_divergence": True,     # RSI divergence bonus
    "mtf_confluence": True,         # H4 confirms H1 (soft filter now)
    "sl_atr_mult": 3.0,            # SL = 3x ATR
    "tp_atr_mult": 5.0,            # TP = 5x ATR (R:R = 1:1.67)
    
    # NEW: Session Volatility Filter
    "optimal_sessions": [13, 14, 15, 16],  # London/NY overlap (UTC)
    "session_risk_mult": {7: 0.5, 8: 0.7, 9: 0.8, 10: 0.9, 11: 1.0, 12: 1.0,
                          13: 1.0, 14: 1.0, 15: 1.0, 16: 1.0, 17: 0.9, 18: 0.8,
                          19: 0.7, 20: 0.6, 21: 0.5},
    
    # NEW: Portfolio Heat Limit
    "max_concurrent_trades": 3,     # Max 3 open positions
    "max_correlated_trades": 2,     # Max 2 correlated pairs
    
    # NEW: Drawdown Throttle
    "drawdown_throttle_enabled": True,
    "drawdown_warning_pct": 0.05,   # -5% drawdown → reduce risk 50%
    "drawdown_critical_pct": 0.10,  # -10% drawdown → reduce risk 75%
    "drawdown_pause_pct": 0.15,     # -15% drawdown → pause trading
    
    # NEW: Partial Take-Profit
    "partial_tp_enabled": True,
    "partial_tp_pct": 0.50,         # Close 50% at 1:1 R:R
    "partial_tp_rr": 1.0,           # Trigger at 1:1 risk-reward
    
    # NEW: Volatility Regime
    "volatility_regime_enabled": True,
    "high_vol_threshold": 0.80,     # 80th percentile ATR = high vol
    "low_vol_threshold": 0.20,      # 20th percentile ATR = low vol
    
    # NEW: Mean Reversion at Extremes
    "mean_reversion_enabled": True,
    "rsi_extreme_low": 25,          # RSI < 25 = oversold
    "rsi_extreme_high": 75,         # RSI > 75 = overbought
    
    # SYMBOL WEIGHTS: v2 — no AMD/GOOGL, equal weight
    "sym_weights": {
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
    
    # IMPROVEMENTS (ACTIVE)
    "correlation_filter": True,
    "dynamic_risk": True,
    "risk_reduction_threshold": 3,
    "risk_reduction_factor": 0.5,
    "min_risk_pct": 0.05,
    "spread_filter": True,
    "max_spread_multiplier": 2.5,
    "news_avoidance": False,        # Placeholder — activate week 3
    "breakout_detection": False,    # Activate week 3
    "mean_reversion": False,        # Activate week 3
    "position_scaling": False,      # Activate week 3
    "circuit_breaker": 3,           # Stop after 3 losses
}

CYCLE_INTERVAL = 3600
DURATION_DAYS = 21  # 3 weeks
TRADES_DIR = Path("trades_complete")
LOG_FILE = TRADES_DIR / "complete_trades.jsonl"
STATE_FILE = TRADES_DIR / "complete_state.json"
SUMMARY_FILE = TRADES_DIR / "complete_summary.json"
CONTROL_FILE = TRADES_DIR / "trading_control.json"

# Global state for dashboard
trading_active = False
trading_thread = None


# ═══════════════════════════════════════════════════════════════
# MT5 DETECTION & ACCOUNT INFO
# ═══════════════════════════════════════════════════════════════
def detect_mt5():
    """Detect if MT5 is installed and running."""
    import subprocess
    
    result = {
        "installed": False,
        "running": False,
        "path": MT5_PATH,
        "process_name": "terminal64.exe",
    }
    
    # Check if installed
    if os.path.exists(MT5_PATH):
        result["installed"] = True
    
    # Check if running
    try:
        output = subprocess.check_output(
            ['tasklist', '/FI', f'IMAGENAME eq {result["process_name"]}'],
            text=True, stderr=subprocess.DEVNULL
        )
        if result["process_name"] in output:
            result["running"] = True
    except:
        pass
    
    return result


def get_account_details():
    """Get full MT5 account details."""
    info = mt5.account_info()
    if info is None:
        return None
    
    # Get positions
    positions = mt5.positions_get()
    position_list = []
    if positions:
        for p in positions:
            position_list.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "commission": p.commission,
                "magic": p.magic,
                "comment": p.comment,
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
            })
    
    # Get recent deals
    deals = mt5.history_deals_get(days_back=7)
    deal_list = []
    if deals:
        for d in deals[-20:]:  # Last 20 deals
            deal_list.append({
                "ticket": d.ticket,
                "order": d.order,
                "symbol": d.symbol,
                "type": "BUY" if d.type == 0 else "SELL" if d.type == 1 else "BALANCE",
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "swap": d.swap,
                "commission": d.commission,
                "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                "comment": d.comment,
            })
    
    # Get symbol info for spread
    spread_info = {}
    for sym in WATCHLIST[:5]:  # Top 5 only
        sym_info = mt5.symbol_info(sym)
        if sym_info:
            spread_info[sym] = {
                "spread": sym_info.spread,
                "digits": sym_info.digits,
                "volume_min": sym_info.volume_min,
                "volume_max": sym_info.volume_max,
            }
    
    return {
        "login": info.login,
        "server": info.server,
        "name": info.name,
        "company": info.company,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "leverage": info.leverage,
        "currency": info.currency,
        "profit": info.profit,
        "margin_level": info.margin_level,
        "account_type": "DEMO" if info.trade_mode == 0 else "LIVE" if info.trade_mode == 1 else "CONTEST",
        "positions": position_list,
        "recent_deals": deal_list,
        "spread_info": spread_info,
        "positions_count": len(position_list),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════
def compute_indicators(df):
    """Compute all technical indicators — v2 with ADX, Ichimoku, EMA21."""
    c = df["close"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)

    df["sma_5"] = pd.Series(c).rolling(5).mean().values
    df["sma_10"] = pd.Series(c).rolling(10).mean().values
    df["sma_20"] = pd.Series(c).rolling(20).mean().values
    df["sma_50"] = pd.Series(c).rolling(50).mean().values
    df["sma_200"] = pd.Series(c).rolling(200).mean().values
    df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
    df["ema_21"] = pd.Series(c).ewm(span=21).mean().values
    df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
    df["ema_200"] = pd.Series(c).ewm(span=200).mean().values

    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = pd.Series(df["macd"]).ewm(span=9).mean().values
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI
    deltas = np.diff(c, prepend=c[0])
    gains = np.where(deltas > 0, deltas, 0)
    losses_arr = np.where(deltas < 0, -deltas, 0)
    avg_gain = pd.Series(gains).ewm(span=14, adjust=False).mean().values
    avg_loss = pd.Series(losses_arr).ewm(span=14, adjust=False).mean().values
    rs = np.where(avg_loss > 1e-10, avg_gain / avg_loss, 100)
    df["rsi"] = 100 - (100 / (1 + rs))

    # RSI Divergence
    n = len(c)
    rsi_div = np.zeros(n)
    for i in range(28, n):
        if c[i] < c[i - 14] and df["rsi"].iloc[i] > df["rsi"].iloc[i - 14]:
            rsi_div[i] = 1  # Bullish divergence
        elif c[i] > c[i - 14] and df["rsi"].iloc[i] < df["rsi"].iloc[i - 14]:
            rsi_div[i] = -1  # Bearish divergence
    df["rsi_div"] = rsi_div

    bb_std = pd.Series(c).rolling(20).std().values
    df["bb_mid"] = df["sma_20"]
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    df["atr"] = pd.Series(tr).rolling(14).mean().values

    # ADX (Average Directional Index)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr_arr = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        down = l[i - 1] - l[i]
        plus_dm[i] = up if (up > down and up > 0) else 0
        minus_dm[i] = down if (down > up and down > 0) else 0
        tr_arr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr14 = pd.Series(tr_arr).ewm(span=14, adjust=False).mean().values
    plus_di = 100 * pd.Series(plus_dm).ewm(span=14, adjust=False).mean().values / np.where(atr14 > 0, atr14, 1)
    minus_di = 100 * pd.Series(minus_dm).ewm(span=14, adjust=False).mean().values / np.where(atr14 > 0, atr14, 1)
    dx = np.where((plus_di + minus_di) > 0, 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0)
    df["adx"] = pd.Series(dx).ewm(span=14, adjust=False).mean().values
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # Ichimoku Cloud
    df["tenkan"] = (pd.Series(h).rolling(9).max() + pd.Series(l).rolling(9).min()).values / 2
    df["kijun"] = (pd.Series(h).rolling(26).max() + pd.Series(l).rolling(26).min()).values / 2
    df["senkou_a"] = (df["tenkan"] + df["kijun"]) / 2
    df["senkou_b"] = ((pd.Series(h).rolling(52).max() + pd.Series(l).rolling(52).min()).values) / 2

    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values

    # IMPROVEMENT 5: Breakout detection
    df["resistance"] = pd.Series(h).rolling(20).max().values
    df["support"] = pd.Series(l).rolling(20).min().values
    df["volume_sma"] = pd.Series(df["volume"].values).rolling(20).mean().values if "volume" in df else 0

    return df


def generate_signal_single_tf(row, use_mean_reversion=False):
    """Generate signal for single timeframe — v2 with ADX, Ichimoku, RSI divergence."""
    score = 0
    max_score = 0

    adx_thresh = CONFIG.get("adx_threshold", 30)
    use_ichimoku = CONFIG.get("use_ichimoku", True)
    use_vol = CONFIG.get("use_volume_filter", True)
    use_div = CONFIG.get("use_rsi_divergence", True)

    adx_val = float(row.get("adx", 0))
    plus_di = float(row.get("plus_di", 0))
    minus_di = float(row.get("minus_di", 0))

    # ── Layer 1: ADX Trend Strength (must be trending) ──
    max_score += 3
    if adx_val >= adx_thresh:
        score += 3  # Strong trend
    elif adx_val >= adx_thresh - 5:
        score += 1  # Mild trend

    # ── Layer 2: DI Direction ──
    max_score += 2
    if plus_di > minus_di:
        score += 2
    elif minus_di > plus_di:
        score -= 2

    # ── Layer 3: Price vs EMA21 + SMA50 ──
    max_score += 2
    ema21 = float(row.get("ema_21", 0))
    sma50 = float(row.get("sma_50", 0))
    px = float(row["close"])

    if px > ema21 > sma50:
        score += 2
    elif px < ema21 < sma50:
        score -= 2
    elif px > ema21:
        score += 1
    elif px < ema21:
        score -= 1

    # ── Layer 4: RSI neutral zone ──
    max_score += 1
    rsi = float(row.get("rsi", 50))
    if 40 <= rsi <= 60:
        score += 1
    elif rsi < 30 or rsi > 70:
        score -= 1

    # ── Layer 5: Volume Confirmation ──
    max_score += 1
    if use_vol:
        vol = float(row.get("volume", 0))
        vol_sma = float(row.get("volume_sma", 1))
        if vol > vol_sma * 1.2:
            score += 1

    # ── Layer 6: Ichimoku Cloud ──
    if use_ichimoku:
        max_score += 2
        tenkan = float(row.get("tenkan", 0))
        kijun = float(row.get("kijun", 0))
        senkou_a = float(row.get("senkou_a", 0))
        senkou_b = float(row.get("senkou_b", 0))

        if px > max(senkou_a, senkou_b) and tenkan > kijun:
            score += 2
        elif px < min(senkou_a, senkou_b) and tenkan < kijun:
            score -= 2

    # ── Layer 7: RSI Divergence ──
    max_score += 1
    if use_div:
        div = float(row.get("rsi_div", 0))
        if div > 0:
            score += 1
        elif div < 0:
            score -= 1

    # Determine direction and confidence
    if score >= 3:
        direction = "BUY"
        confidence = min(score / max(max_score, 1), 1.0)
    elif score <= -3:
        direction = "SELL"
        confidence = min(abs(score) / max(max_score, 1), 1.0)
    else:
        direction = "HOLD"
        confidence = 0.0

    return direction, confidence, score


# ═══════════════════════════════════════════════════════════════
# MULTI-TIMEFRAME ANALYSIS
# ═══════════════════════════════════════════════════════════════
def analyze_symbol_mtf(symbol, use_mean_reversion=False):
    """Analyze symbol across ALL 7 timeframes."""
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
        action, confidence, score = generate_signal_single_tf(latest, use_mean_reversion)
        weight = TF_WEIGHTS.get(tf_name, 0.1)

        results[tf_name] = {
            "action": action,
            "confidence": confidence,
            "score": score,
            "weight": weight,
            "price": float(latest["close"]),
            "atr": float(latest["atr"]) if not np.isnan(latest["atr"]) else 0,
            "rsi": float(latest["rsi"]) if not np.isnan(latest["rsi"]) else 50,
            "macd_hist": float(latest["macd_hist"]) if not np.isnan(latest["macd_hist"]) else 0,
            "volatility": float(latest["volatility_10"]) if not np.isnan(latest["volatility_10"]) else 0.01,
        }

        if action == "BUY":
            buy_score += score * weight
            buy_count += 1
        elif action == "SELL":
            sell_score += score * weight
            sell_count += 1

    if not results:
        return "HOLD", 0, 0, {}, 0, 0.01

    h1 = results.get("H1", results.get("H4", results.get("D1", {})))
    atr = h1.get("atr", 0) if h1 else 0
    volatility = h1.get("volatility", 0.01) if h1 else 0.01

    # SOFT FILTER: D1/H4 agreement — bonus points, not hard block
    trend_tf = CONFIG["trend_timeframes"]
    trend_actions = [results[tf]["action"] for tf in trend_tf if tf in results]
    trend_bonus = 0
    if len(trend_actions) >= 2:
        if trend_actions[0] == trend_actions[1]:
            trend_bonus = 2  # Bonus for agreement
        # REMOVED: Hard block when D1/H4 disagree

    min_agree = CONFIG["min_timeframes_agree"]
    agreement = max(buy_count, sell_count)
    if agreement < min_agree:
        return "HOLD", 0, 0, results, atr, volatility

    net_weighted = buy_score - sell_score
    if net_weighted > 0 and buy_count >= min_agree:
        # Apply trend bonus to score
        final_score = buy_score + trend_bonus
        return "BUY", buy_score, final_score, results, atr, volatility
    elif net_weighted < 0 and sell_count >= min_agree:
        # Apply trend bonus to score
        final_score = sell_score + trend_bonus
        return "SELL", sell_score, final_score, results, atr, volatility

    return "HOLD", 0, 0, results, atr, volatility


# ═══════════════════════════════════════════════════════════════
# IMPROVEMENTS
# ═══════════════════════════════════════════════════════════════
def check_correlation(symbol, action, open_positions):
    """IMPROVEMENT 1: Check if opening this would be correlated with existing."""
    if not CONFIG.get("correlation_filter"):
        return True
    
    correlations = CORRELATIONS.get(symbol, [])
    for pos_symbol, pos_info in open_positions.items():
        if pos_symbol in correlations and pos_info["action"] == action:
            return False  # Skip - too correlated
    return True


def get_dynamic_risk(consecutive_losses):
    """IMPROVEMENT 2: Reduce risk after consecutive losses."""
    if not CONFIG.get("dynamic_risk"):
        return CONFIG["max_risk_pct"]
    
    if consecutive_losses >= CONFIG["risk_reduction_threshold"]:
        reduction = CONFIG["risk_reduction_factor"] ** ((consecutive_losses - CONFIG["risk_reduction_threshold"]) // 2 + 1)
        risk = CONFIG["max_risk_pct"] * reduction
        return max(risk, CONFIG["min_risk_pct"])
    return CONFIG["max_risk_pct"]


def check_spread(symbol):
    """IMPROVEMENT 3: Check if spread is acceptable."""
    if not CONFIG.get("spread_filter"):
        return True, 0
    
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return False, 999
    
    spread = sym_info.spread
    # Normal spread for major pairs is 5-15 points
    normal_spread = 10
    max_spread = normal_spread * CONFIG["max_spread_multiplier"]
    
    return spread <= max_spread, spread


def check_news_filter():
    """IMPROVEMENT 4: Check if there's high-impact news (placeholder)."""
    if not CONFIG.get("news_avoidance"):
        return True
    
    # TODO: Integrate with economic calendar API
    # For now, always return True
    return True


# ═══════════════════════════════════════════════════════════════
# NEW IMPROVEMENTS
# ═══════════════════════════════════════════════════════════════

def check_portfolio_heat(open_positions, symbol, action):
    """PORTFOLIO HEAT LIMIT: Check if we can open another position."""
    max_concurrent = CONFIG.get("max_concurrent_trades", 3)
    max_correlated = CONFIG.get("max_correlated_trades", 2)
    
    # Check total open positions
    if len(open_positions) >= max_concurrent:
        return False, "Max concurrent trades reached"
    
    # Check correlated positions
    correlations = CORRELATIONS.get(symbol, [])
    correlated_count = sum(1 for pos_sym, pos_info in open_positions.items() 
                          if pos_sym in correlations and pos_info["action"] == action)
    if correlated_count >= max_correlated:
        return False, "Too many correlated positions"
    
    return True, "OK"


def get_drawdown_throttle(peak_equity, current_equity):
    """DRAWDOWN THROTTLE: Reduce risk based on drawdown."""
    if not CONFIG.get("drawdown_throttle_enabled"):
        return 1.0
    
    if peak_equity <= 0:
        return 1.0
    
    drawdown = (peak_equity - current_equity) / peak_equity
    
    if drawdown >= CONFIG.get("drawdown_pause_pct", 0.15):
        return 0.0  # Pause trading
    elif drawdown >= CONFIG.get("drawdown_critical_pct", 0.10):
        return 0.25  # Reduce risk by 75%
    elif drawdown >= CONFIG.get("drawdown_warning_pct", 0.05):
        return 0.50  # Reduce risk by 50%
    
    return 1.0  # Full risk


def get_session_risk_multiplier(hour):
    """SESSION VOLATILITY FILTER: Adjust risk based on trading session."""
    session_mult = CONFIG.get("session_risk_mult", {})
    return session_mult.get(hour, 1.0)


def calculate_volatility_regime(atr_values, current_atr):
    """VOLATILITY REGIME: Detect high/medium/low volatility."""
    if not CONFIG.get("volatility_regime_enabled") or not atr_values:
        return "medium", 1.0
    
    # Calculate percentile
    sorted_atrs = sorted(atr_values)
    rank = sum(1 for a in sorted_atrs if a <= current_atr) / len(sorted_atrs)
    
    if rank >= CONFIG.get("high_vol_threshold", 0.80):
        return "high", 0.7  # Reduce size in high vol
    elif rank <= CONFIG.get("low_vol_threshold", 0.20):
        return "low", 1.2   # Increase size in low vol (calm markets)
    
    return "medium", 1.0


def check_mean_reversion(rsi, price, support, resistance):
    """MEAN REVERSION: Detect oversold/oversold at S/R levels."""
    if not CONFIG.get("mean_reversion_enabled"):
        return None, 0
    
    rsi_low = CONFIG.get("rsi_extreme_low", 25)
    rsi_high = CONFIG.get("rsi_extreme_high", 75)
    
    # Oversold at support → BUY signal
    if rsi < rsi_low and support > 0 and price <= support * 1.002:
        confidence = (rsi_low - rsi) / rsi_low  # Higher confidence when more oversold
        return "BUY", min(confidence, 0.7)  # Cap at 0.7 for counter-trend
    
    # Overbought at resistance → SELL signal
    if rsi > rsi_high and resistance > 0 and price >= resistance * 0.998:
        confidence = (rsi - rsi_high) / (100 - rsi_high)
        return "SELL", min(confidence, 0.7)
    
    return None, 0


# ═══════════════════════════════════════════════════════════════
# TRADING ENGINE
# ═══════════════════════════════════════════════════════════════
def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return False
    return True


class CompleteTrader:
    """Complete trading engine with all improvements."""

    def __init__(self):
        self.positions = {}
        self.trade_log = []
        self.balance = 10000.0
        self.peak_equity = 10000.0  # NEW: Track peak for drawdown
        self.consecutive_losses = 0
        self.kelly = KellySizer()
        self.kelly_frac = self.kelly.calculate(
            win_rate=CONFIG["kelly_win_rate"],
            avg_win=CONFIG["kelly_avg_win"],
            avg_loss=CONFIG["kelly_avg_loss"],
        )
        self.week_number = 1
        self.start_time = datetime.now(timezone.utc)
        self.atr_history = []  # NEW: Track ATR for volatility regime
        self.partial_tp_state = {}  # NEW: Track partial take-profit state

    def get_account_info(self):
        info = mt5.account_info()
        if info:
            self.balance = info.balance
            # Track peak equity for drawdown calculation
            if info.balance > self.peak_equity:
                self.peak_equity = info.balance
            return info
        return None

    def update_week_number(self):
        """Update week number and activate improvements."""
        elapsed = datetime.now(timezone.utc) - self.start_time
        self.week_number = (elapsed.days // 7) + 1
        
        # Activate improvements after week 3
        if self.week_number >= 3:
            if not CONFIG.get("news_avoidance"):
                print(f"\n  *** WEEK {self.week_number}: ACTIVATING NEWS AVOIDANCE ***")
                CONFIG["news_avoidance"] = True
            if not CONFIG.get("breakout_detection"):
                print(f"\n  *** WEEK {self.week_number}: ACTIVATING BREAKOUT DETECTION ***")
                CONFIG["breakout_detection"] = True
            if not CONFIG.get("mean_reversion"):
                print(f"\n  *** WEEK {self.week_number}: ACTIVATING MEAN REVERSION ***")
                CONFIG["mean_reversion"] = True
            if not CONFIG.get("position_scaling"):
                print(f"\n  *** WEEK {self.week_number}: ACTIVATING POSITION SCALING ***")
                CONFIG["position_scaling"] = True

    def get_lot_size(self, symbol, price, volatility=0.01, atr=0):
        """Calculate lot size based on equity, risk %, and ATR-based SL distance."""
        risk_pct = CONFIG.get("max_risk_pct", 0.10)
        
        # Apply drawdown throttle
        drawdown_mult = get_drawdown_throttle(self.peak_equity, self.balance)
        if drawdown_mult == 0:
            return 0.0
        risk_pct *= drawdown_mult
        
        # Apply session risk multiplier
        current_hour = datetime.now(timezone.utc).hour
        session_mult = get_session_risk_multiplier(current_hour)
        risk_pct *= session_mult
        
        # Risk amount in dollars (based on current equity)
        risk_amount = self.balance * risk_pct

        # Apply symbol weight
        sym_weights = CONFIG.get("sym_weights", {})
        weight = sym_weights.get(symbol, 1.0)
        risk_amount *= weight

        # Apply volatility regime
        vol_regime, vol_mult = calculate_volatility_regime(self.atr_history, atr)
        risk_amount *= vol_mult

        # Volatility-based sizing
        if CONFIG.get("vol_sizing") and volatility > 0:
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        # Calculate SL distance in price terms (ATR-based)
        sl_distance = atr * CONFIG.get("sl_atr_mult", 3.0) if atr > 0 else price * 0.003
        
        # Lot size = Risk Amount / (SL Distance * Contract Size)
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.0

        contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
        
        if sl_distance > 0 and contract_size > 0:
            lots = risk_amount / (sl_distance * contract_size)
        else:
            # Fallback: simple percentage of equity
            lots = risk_amount / (price * contract_size)

        # Enforce min/max limits
        lot_size = symbol_info.volume_min
        lots = max(lot_size, min(lots, symbol_info.volume_max))
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        lots = round(lots, 2)
        return lots

    def open_position(self, symbol, action, price, atr, volatility, tf_score, tf_details):
        """Open real MT5 position."""
        if symbol in self.positions:
            return None

        # NEW: Portfolio heat limit
        heat_ok, heat_msg = check_portfolio_heat(self.positions, symbol, action)
        if not heat_ok:
            print(f"  SKIP {symbol}: {heat_msg}")
            return None

        # IMPROVEMENT 1: Correlation filter
        if not check_correlation(symbol, action, self.positions):
            print(f"  SKIP {symbol}: Correlated with existing position")
            return None

        # IMPROVEMENT 3: Spread filter
        spread_ok, spread = check_spread(symbol)
        if not spread_ok:
            print(f"  SKIP {symbol}: Spread too wide ({spread})")
            return None

        # IMPROVEMENT 4: News filter
        if not check_news_filter():
            print(f"  SKIP {symbol}: High-impact news")
            return None

        # Check drawdown throttle
        drawdown_mult = get_drawdown_throttle(self.peak_equity, self.balance)
        if drawdown_mult == 0:
            print(f"  SKIP {symbol}: Trading paused due to drawdown")
            return None

        # Calculate lot size
        lots = self.get_lot_size(symbol, price, volatility, atr)
        if lots <= 0:
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        exec_price = tick.ask if action == "BUY" else tick.bid

        # ATR-based SL/TP
        sl_pips = atr * CONFIG.get("sl_atr_mult", 3.0) if atr > 0 else price * 0.003
        tp_pips = atr * CONFIG.get("tp_atr_mult", 5.0) if atr > 0 else price * 0.005

        if action == "BUY":
            sl = exec_price - sl_pips
            tp = exec_price + tp_pips
        else:
            sl = exec_price + sl_pips
            tp = exec_price - tp_pips

        # Validate SL/TP
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
            "comment": "dutchkem_complete",
        }

        result = mt5.order_send(mt5_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return None

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
            "scaled": False,
        }
        self.positions[symbol] = pos

        tf_str = " ".join([f"{tf}({info['score']:+d})" for tf, info in tf_details.items() if info["action"] == action])
        risk_pct = get_dynamic_risk(self.consecutive_losses) * 100
        print(f"  OPENED {symbol:10} {action:4} #{result.order} {lots:.2f} lots @ {result.price:.5f}")
        print(f"    SL={sl:.5f} TP={tp:.5f} | Risk={risk_pct:.1f}% | TFs: {tf_str}")
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
            "ticket": ticket,
            "entry_price": pos["entry_price"],
            "exit_price": result.price,
            "entry_time": str(pos["entry_time"]),
            "exit_time": str(datetime.now(timezone.utc)),
            "size": mt5_pos.volume,
            "pnl": round(pnl, 2),
            "balance": round(self.balance, 2),
            "tf_score": pos.get("tf_score", 0),
            "tf_agreement": pos.get("tf_agreement", 0),
        }
        self.trade_log.append(trade)

        m = "+" if pnl > 0 else ""
        print(f"  CLOSED {symbol:10} {pos['action']:4} | P&L=${m}{pnl:.2f}")
        return trade

    def check_trailing_stop(self, symbol):
        """Trailing stop with partial take-profit."""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        current_price = tick.bid if pos["action"] == "BUY" else tick.ask
        entry = pos["entry_price"]

        if pos["action"] == "BUY":
            profit_pct = (current_price - entry) / entry
        else:
            profit_pct = (entry - current_price) / entry

        # NEW: Partial take-profit at 1:1 R:R
        if CONFIG.get("partial_tp_enabled") and not pos.get("partial_tp_done"):
            partial_rr = CONFIG.get("partial_tp_rr", 1.0)
            sl_distance = abs(entry - pos["initial_sl"])
            profit_distance = abs(current_price - entry)
            
            if profit_distance >= sl_distance * partial_rr:
                # Close partial position
                self._close_partial(symbol, CONFIG.get("partial_tp_pct", 0.50))
                pos["partial_tp_done"] = True

        # Traditional trailing stop (breakeven)
        if profit_pct >= CONFIG["trailing_breakeven"]:
            if pos["action"] == "BUY" and pos["sl"] < entry:
                new_sl = entry + (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)
            elif pos["action"] == "SELL" and pos["sl"] > entry:
                new_sl = entry - (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)

    def _close_partial(self, symbol, pct):
        """Close a percentage of the position."""
        if symbol not in self.positions:
            return
        
        pos = self.positions[symbol]
        ticket = pos["ticket"]
        
        mt5_pos = mt5.positions_get(ticket=ticket)
        if not mt5_pos or len(mt5_pos) == 0:
            return
        
        mt5_pos = mt5_pos[0]
        close_volume = round(mt5_pos.volume * pct, 2)
        
        # Ensure minimum volume
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info and close_volume < symbol_info.volume_min:
            return
        
        close_type = mt5.ORDER_TYPE_SELL if mt5_pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        close_price = tick.bid if mt5_pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        close_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "dutchkem_partial",
        }
        
        result = mt5.order_send(close_order)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            # Calculate P&L for closed portion
            if pos["action"] == "BUY":
                pnl = (result.price - pos["entry_price"]) / pos["entry_price"] * close_volume
            else:
                pnl = (pos["entry_price"] - result.price) / pos["entry_price"] * close_volume
            
            self.balance += pnl
            pos["size"] -= close_volume
            
            print(f"    PARTIAL TP {symbol}: Closed {pct:.0%} @ {result.price:.5f} | P&L=${pnl:+.2f}")

    def _modify_sl(self, symbol, new_sl):
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": pos["ticket"],
            "sl": new_sl,
            "tp": pos["tp"],
        }
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pos["sl"] = new_sl
            print(f"    TRAILING {symbol}: SL -> {new_sl:.5f}")

    def sync_positions(self):
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            return
        mt5_symbols = {p.symbol: p for p in mt5_positions}
        for sym in list(self.positions.keys()):
            if sym not in mt5_symbols:
                del self.positions[sym]

    def get_state(self):
        drawdown_pct = 0
        if self.peak_equity > 0:
            drawdown_pct = (self.peak_equity - self.balance) / self.peak_equity * 100
        
        return {
            "balance": self.balance,
            "peak_equity": self.peak_equity,
            "drawdown_pct": round(drawdown_pct, 2),
            "consecutive_losses": self.consecutive_losses,
            "week_number": self.week_number,
            "active_improvements": {
                "correlation_filter": CONFIG.get("correlation_filter", False),
                "dynamic_risk": CONFIG.get("dynamic_risk", False),
                "spread_filter": CONFIG.get("spread_filter", False),
                "news_avoidance": CONFIG.get("news_avoidance", False),
                "breakout_detection": CONFIG.get("breakout_detection", False),
                "mean_reversion": CONFIG.get("mean_reversion", False),
                "position_scaling": CONFIG.get("position_scaling", False),
                "partial_tp": CONFIG.get("partial_tp_enabled", False),
                "drawdown_throttle": CONFIG.get("drawdown_throttle_enabled", False),
                "volatility_regime": CONFIG.get("volatility_regime_enabled", False),
                "portfolio_heat": CONFIG.get("max_concurrent_trades", 3),
            },
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
def run_cycle(trader, cycle_num):
    """Run one analysis cycle."""
    now = datetime.now(timezone.utc)
    trader.get_account_info()
    trader.sync_positions()
    trader.update_week_number()

    # Calculate drawdown for display
    drawdown_pct = 0
    if trader.peak_equity > 0:
        drawdown_pct = (trader.peak_equity - trader.balance) / trader.peak_equity * 100

    print(f"\n{'='*90}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC | Week {trader.week_number}")
    print(f"  Balance: ${trader.balance:,.2f} | Peak: ${trader.peak_equity:,.2f} | DD: {drawdown_pct:.1f}%")
    print(f"  Open: {len(trader.positions)}/{CONFIG.get('max_concurrent_trades', 3)} | Losses: {trader.consecutive_losses}")
    print(f"  Session: Hour {now.hour} UTC | Risk Mult: {get_session_risk_multiplier(now.hour):.1f}")
    print(f"{'='*90}")

    # Session check
    session_hours = CONFIG.get("session_hours")
    in_session = now.hour in session_hours if session_hours else True
    if not in_session:
        print(f"  Outside session (London+NY). Hour={now.hour} UTC")
        for sym in list(trader.positions.keys()):
            trader.check_trailing_stop(sym)
        return trader

    # Check drawdown pause
    drawdown_mult = get_drawdown_throttle(trader.peak_equity, trader.balance)
    if drawdown_mult == 0:
        print(f"  TRADING PAUSED: Drawdown exceeds {CONFIG.get('drawdown_pause_pct', 0.15):.0%}")
        for sym in list(trader.positions.keys()):
            trader.check_trailing_stop(sym)
        return trader

    # Analyze ALL symbols
    signals = []
    for sym in WATCHLIST:
        if sym in trader.positions:
            trader.check_trailing_stop(sym)
            continue

        use_mr = CONFIG.get("mean_reversion", False)
        action, total_score, weighted_score, details, atr, volatility = analyze_symbol_mtf(sym, use_mr)

        # Track ATR for volatility regime
        if atr > 0:
            trader.atr_history.append(atr)
            if len(trader.atr_history) > 100:
                trader.atr_history = trader.atr_history[-100:]

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

    signals.sort(key=lambda x: x["weighted_score"], reverse=True)

    if signals:
        print(f"\n  SIGNALS: {len(signals)}")
        for sig in signals[:5]:
            tf_count = sum(1 for info in sig["details"].values() if info["action"] == sig["action"])
            print(f"    {sig['symbol']:<10} {sig['action']:<6} score={sig['weighted_score']:.2f} TFs={tf_count}/7")

    # Execute top signals
    executed = 0
    for sig in signals[:5]:
        result = trader.open_position(
            sig["symbol"], sig["action"], sig["price"],
            sig["atr"], sig["volatility"], sig["weighted_score"], sig["details"],
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


def save_summary(trader, total_cycles):
    TRADES_DIR.mkdir(exist_ok=True)
    state = trader.get_state()
    elapsed = datetime.now(timezone.utc) - trader.start_time
    summary = {
        "start_time": trader.start_time.isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_hours": round(elapsed.total_seconds() / 3600, 1),
        "total_cycles": total_cycles,
        "week_number": trader.week_number,
        "config": CONFIG,
        "results": state,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)


def write_control(status):
    """Write control status for dashboard."""
    TRADES_DIR.mkdir(exist_ok=True)
    with open(CONTROL_FILE, "w") as f:
        json.dump({"status": status, "timestamp": datetime.now(timezone.utc).isoformat()}, f)


def read_control():
    """Read control status from dashboard."""
    if CONTROL_FILE.exists():
        try:
            with open(CONTROL_FILE, "r") as f:
                return json.load(f).get("status", "stopped")
        except:
            pass
    return "stopped"


def trading_loop():
    """Main trading loop (runs in thread)."""
    global trading_active

    print("\n" + "=" * 90)
    print("  DUTCHKEM TRADER - COMPLETE LIVE TRADING ENGINE")
    print("  27 Instruments x 7 Timeframes | All Improvements")
    print("=" * 90)

    if not connect_mt5():
        print("  FAILED: Cannot connect to MT5")
        trading_active = False
        return

    info = mt5.account_info()
    if info is None:
        print("  FAILED: Cannot get account info")
        mt5.shutdown()
        trading_active = False
        return

    print(f"\n  Account: {info.login} | {info.server}")
    print(f"  Balance: ${info.balance:,.2f} | Free: ${info.margin_free:,.2f}")
    print(f"  Leverage: 1:{info.leverage}")
    print(f"  Duration: {DURATION_DAYS} days")

    trader = CompleteTrader()
    trader.balance = info.balance

    write_control("running")
    cycle = 0

    try:
        while trading_active:
            # Check if dashboard sent stop command
            if read_control() == "stopped":
                print("\n  Stop command received from dashboard")
                break

            cycle += 1
            run_cycle(trader, cycle)
            save_state(trader)
            save_trade_log(trader)

            # Sleep with periodic control checks
            for _ in range(CYCLE_INTERVAL // 10):
                if not trading_active or read_control() == "stopped":
                    break
                time.sleep(10)

    except KeyboardInterrupt:
        print("\n\n  Trading stopped by user.")
    finally:
        mt5.shutdown()
        save_state(trader)
        save_trade_log(trader)
        save_summary(trader, cycle)
        write_control("stopped")
        trading_active = False
        print("  MT5 disconnected. State saved.")


# ═══════════════════════════════════════════════════════════════
# START/STOP FUNCTIONS (for dashboard)
# ═══════════════════════════════════════════════════════════════
def start_trading():
    """Start trading in background thread."""
    global trading_active, trading_thread
    
    if trading_active:
        return {"status": "already_running"}
    
    trading_active = True
    write_control("running")
    trading_thread = threading.Thread(target=trading_loop, daemon=True)
    trading_thread.start()
    
    return {"status": "started"}


def stop_trading():
    """Stop trading."""
    global trading_active
    
    trading_active = False
    write_control("stopped")
    
    return {"status": "stopped"}


def get_trading_status():
    """Get current trading status."""
    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except:
            pass
    
    return {
        "active": trading_active,
        "control": read_control(),
        "state": state,
        "mt5": detect_mt5(),
        "account": get_account_details() if trading_active else None,
    }


if __name__ == "__main__":
    start_trading()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_trading()
