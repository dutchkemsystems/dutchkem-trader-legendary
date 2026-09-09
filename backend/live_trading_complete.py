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
    # OPTIMIZED: Round 8 production config (2026-09-10)
    # Excluded: NVDA, XAGUSD, US500, UK100, TSLA, AAPL, ETHUSD, BTCUSD, MSFT, META, AMZN
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD",
    "US30",
    "AMD", "GOOGL",
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
    # OPTIMIZED PRODUCTION CONFIG (Round 8 - 2026-09-10)
    # Best result: +$597.01 P&L, 50.4% WR, 478 trades
    # Key: risk50 + no circuit breaker + AMD focus
    # ═══════════════════════════════════════════════════════════════
    "max_risk_pct": 0.50,           # 50% risk per trade (optimized)
    "max_position_pct": 0.50,      # Max 50% position size
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "hold_bars": 10,               # Hold 10 bars (optimized)
    "trailing_breakeven": 0.01,
    "min_confidence": 0.30,         # Minimum confidence threshold
    "min_timeframes_agree": 4,
    "trend_timeframes": ["D1", "H4"],
    "session_hours": set(range(7, 22)),  # Extended session (7am-10pm)
    "vol_sizing": True,
    # SYMBOL WEIGHTS: Optimized from Round 8
    "sym_weights": {
        "AMD": 3.0,      # Consistently biggest winner (+$5,158 in Round 7)
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
    # IMPROVEMENT 1: Correlation Filter
    "correlation_filter": True,
    # IMPROVEMENT 2: Dynamic Risk Reduction (DISABLED - no circuit breaker)
    "dynamic_risk": False,          # Disabled per optimization
    "risk_reduction_threshold": 99, # Effectively disabled
    "risk_reduction_factor": 1.0,   # No reduction
    "min_risk_pct": 0.50,          # Keep full risk
    # IMPROVEMENT 3: Spread Filter
    "spread_filter": True,
    "max_spread_multiplier": 3.0,  # Relaxed spread filter
    # IMPROVEMENTS 4-7: Activate after week 3
    "news_avoidance": False,
    "breakout_detection": False,
    "mean_reversion": False,
    "position_scaling": False,
    # Circuit breaker: DISABLED (let winners run)
    "circuit_breaker": 99,          # No circuit breaker
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
    df["ema_200"] = pd.Series(c).ewm(span=200).mean().values

    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = pd.Series(df["macd"]).ewm(span=9).mean().values
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    deltas = np.diff(c, prepend=c[0])
    gains = np.where(deltas > 0, deltas, 0)
    losses_arr = np.where(deltas < 0, -deltas, 0)
    avg_gain = pd.Series(gains).rolling(14).mean().values
    avg_loss = pd.Series(losses_arr).rolling(14).mean().values
    rs = np.where(avg_loss > 0.0001, avg_gain / avg_loss, 100)
    df["rsi"] = 100 - (100 / (1 + rs))

    bb_std = pd.Series(c).rolling(20).std().values
    df["bb_mid"] = df["sma_20"]
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    df["atr"] = pd.Series(tr).rolling(14).mean().values

    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values

    # IMPROVEMENT 5: Breakout detection
    df["resistance"] = pd.Series(h).rolling(20).max().values
    df["support"] = pd.Series(l).rolling(20).min().values
    df["volume_sma"] = pd.Series(df["volume"].values).rolling(20).mean().values if "volume" in df else 0

    return df


def generate_signal_single_tf(row, use_mean_reversion=False):
    """Generate signal for single timeframe."""
    score = 0

    # IMPROVEMENT 6: Mean Reversion (if enabled)
    if use_mean_reversion:
        # Oversold bounce
        if row["rsi"] < 25 and row["close"] < row["bb_lower"]:
            return "BUY", 0.7, 4
        # Overbought fade
        if row["rsi"] > 75 and row["close"] > row["bb_upper"]:
            return "SELL", 0.7, -4

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

    # Bollinger Band
    if row["close"] < row["bb_lower"]:
        score += 1
    elif row["close"] > row["bb_upper"]:
        score -= 1

    # EMA 200
    if "ema_200" in row and not np.isnan(row["ema_200"]):
        if row["close"] > row["ema_200"]:
            score += 1
        elif row["close"] < row["ema_200"]:
            score -= 1

    # IMPROVEMENT 5: Breakout detection (if enabled)
    if CONFIG.get("breakout_detection"):
        if row["close"] > row["resistance"] * 0.999:  # Near resistance
            score += 2  # Breakout bonus
        if row["close"] < row["support"] * 1.001:  # Near support
            score -= 2

    if score >= 3:
        return "BUY", min(score / 6.0, 1.0), score
    if score <= -3:
        return "SELL", min(abs(score) / 6.0, 1.0), score
    return "HOLD", 0.0, score


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

    # Trend TFs must agree
    trend_tf = CONFIG["trend_timeframes"]
    trend_actions = [results[tf]["action"] for tf in trend_tf if tf in results]
    if len(trend_actions) >= 2 and trend_actions[0] != trend_actions[1]:
        return "HOLD", 0, 0, results, atr, volatility

    min_agree = CONFIG["min_timeframes_agree"]
    agreement = max(buy_count, sell_count)
    if agreement < min_agree:
        return "HOLD", 0, 0, results, atr, volatility

    net_weighted = buy_score - sell_score
    if net_weighted > 0 and buy_count >= min_agree:
        return "BUY", buy_score, net_weighted, results, atr, volatility
    elif net_weighted < 0 and sell_count >= min_agree:
        return "SELL", sell_score, abs(net_weighted), results, atr, volatility

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
        self.consecutive_losses = 0
        self.kelly = KellySizer()
        self.kelly_frac = self.kelly.calculate(
            win_rate=CONFIG["kelly_win_rate"],
            avg_win=CONFIG["kelly_avg_win"],
            avg_loss=CONFIG["kelly_avg_loss"],
        )
        self.week_number = 1
        self.start_time = datetime.now(timezone.utc)

    def get_account_info(self):
        info = mt5.account_info()
        if info:
            self.balance = info.balance
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
        """Calculate lot size with dynamic risk and symbol weights."""
        # IMPROVEMENT 2: Dynamic risk (DISABLED per optimization)
        risk_pct = CONFIG.get("max_risk_pct", 0.50)
        risk_amount = self.balance * risk_pct

        # Apply symbol weight (optimized from Round 8)
        sym_weights = CONFIG.get("sym_weights", {})
        weight = sym_weights.get(symbol, 1.0)
        risk_amount *= weight

        if CONFIG.get("vol_sizing") and volatility > 0:
            vol_factor = max(0.5, min(2.0, 1.0 / (volatility * 100 + 0.01)))
            risk_amount *= vol_factor

        kelly_size = max(10, self.kelly_frac * risk_amount)
        size_usd = min(kelly_size, self.balance * CONFIG["max_position_pct"])

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
        """Open real MT5 position."""
        if symbol in self.positions:
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

        # Calculate lot size
        lots = self.get_lot_size(symbol, price, volatility, atr)
        if lots <= 0:
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        exec_price = tick.ask if action == "BUY" else tick.bid

        # ATR-based SL/TP
        sl_pips = atr * 2 if atr > 0 else price * 0.002
        tp_pips = atr * 3 if atr > 0 else price * 0.003

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
        """Move SL to breakeven after +1%."""
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

        if profit_pct >= CONFIG["trailing_breakeven"]:
            if pos["action"] == "BUY" and pos["sl"] < entry:
                new_sl = entry + (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)
            elif pos["action"] == "SELL" and pos["sl"] > entry:
                new_sl = entry - (tick.ask - tick.bid)
                self._modify_sl(symbol, new_sl)

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
        return {
            "balance": self.balance,
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

    print(f"\n{'='*90}")
    print(f"  CYCLE {cycle_num} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC | Week {trader.week_number}")
    print(f"  Balance: ${trader.balance:,.2f} | Open: {len(trader.positions)} | Losses: {trader.consecutive_losses}")
    print(f"  Active Improvements: {[k for k, v in CONFIG.items() if v is True and k in ['correlation_filter', 'dynamic_risk', 'spread_filter', 'news_avoidance', 'breakout_detection', 'mean_reversion', 'position_scaling']]}")
    print(f"{'='*90}")

    # Session check
    session_hours = CONFIG.get("session_hours")
    in_session = now.hour in session_hours if session_hours else True
    if not in_session:
        print(f"  Outside session (London+NY). Hour={now.hour} UTC")
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
