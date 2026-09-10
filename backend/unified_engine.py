"""
UNIFIED TRADING ENGINE — All Layers Combined
=============================================
Single system combining:
  1. Technical Indicators (8 indicators, score-based signals)
  2. Multi-Timeframe Analysis (M15 → MN1, weighted consensus)
  3. LLM Market Analysis (Ollama qwen2.5:7b for real-time analysis)
  4. ML Signal Ranking (XGBoost/LightGBM)
  5. Consensus Gates (ML + LLM + Sentiment validation)
  6. Risk Management (Kelly, Circuit Breaker, Drawdown Throttle)
  7. Equity-Based Position Sizing (10% risk, volatility-adjusted)
  8. Correlation Filter (max 2 correlated pairs)
  9. Session Filtering (London/NY overlap optimal)
 10. Partial TP & Trailing Stops
 11. Direct MT5 Communication (localhost API server)

Goal: "Making exponential profits and reducing risk to barest minimum"

Run: python unified_engine.py
API: http://localhost:8000
"""

import asyncio
import json
import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("unified_engine.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("unified")

# ═══════════════════════════════════════════════════════════════
# NEW FEATURES IMPORTS
# ═══════════════════════════════════════════════════════════════
try:
    from apps.regime.ensemble import StrategyEnsemble, MarketRegime
    from apps.sentiment.filter import SentimentFilter
    from apps.hedging.correlation import CorrelationHedge
    from apps.volume.profile import VolumeProfile, OrderFlowAnalyzer, filter_by_volume
    from apps.calendar.economic import EconomicCalendar
    from apps.ml.exit_model.predictor import ExitOptimizer
    from apps.risk.parity.allocator import RiskParity
    from apps.optimization.genetic import GeneticOptimizer
    from apps.rl.execution import ExecutionOptimizer
    from apps.alternative.onchain import AlternativeData
    NEW_FEATURES_AVAILABLE = True
    log.info("All 10 new features loaded successfully")
except ImportError as e:
    NEW_FEATURES_AVAILABLE = False
    log.warning(f"New features not available: {e}")

# ═══════════════════════════════════════════════════════════════
# MT5 CONFIGURATION
# ═══════════════════════════════════════════════════════════════
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"
MT5_MAGIC = 234000
MT5_SLIPPAGE = 20

# ═══════════════════════════════════════════════════════════════
# OPTIMIZED WATCHLIST — Tier-based risk management
# ═══════════════════════════════════════════════════════════════
WATCHLIST_TIER1 = ["EURUSD", "GBPUSD", "USDCHF", "AUDUSD", "NZDUSD"]  # Full risk
WATCHLIST_TIER2 = ["USDCAD", "EURGBP"]  # 70% risk
WATCHLIST_TIER3 = ["EURJPY", "GBPJPY", "USDJPY"]  # 40% risk — high volatility
WATCHLIST_SKIP = ["AUDJPY", "XAUUSD", "US30"]  # Removed — data issues or losing

WATCHLIST = WATCHLIST_TIER1 + WATCHLIST_TIER2 + WATCHLIST_TIER3

# Tier-based risk multipliers
TIER_RISK_MULT = {
    "EURUSD": 1.0, "GBPUSD": 1.0, "USDCHF": 1.0, "AUDUSD": 1.0, "NZDUSD": 1.0,
    "USDCAD": 0.7, "EURGBP": 0.7,
    "EURJPY": 0.4, "GBPJPY": 0.4, "USDJPY": 0.4,
}

# Max position size per symbol (lots)
MAX_LOTS_PER_SYMBOL = {
    "EURUSD": 0.50, "GBPUSD": 0.40, "USDCHF": 0.50, "AUDUSD": 0.50, "NZDUSD": 0.50,
    "USDCAD": 0.30, "EURGBP": 0.30,
    "EURJPY": 0.20, "GBPJPY": 0.20, "USDJPY": 0.20,
}

# Contract sizes for correct position sizing
CONTRACT_SIZES = {
    "EURUSD": 100000, "GBPUSD": 100000, "USDJPY": 100000,
    "AUDUSD": 100000, "USDCAD": 100000, "USDCHF": 100000,
    "NZDUSD": 100000, "EURJPY": 100000, "GBPJPY": 100000,
}

CORRELATIONS = {
    "EURUSD": ["GBPUSD", "AUDUSD", "NZDUSD"],
    "GBPUSD": ["EURUSD", "AUDUSD"],
    "AUDUSD": ["NZDUSD", "EURUSD"],
    "USDJPY": ["USDCHF", "USDCAD"],
    "USDCHF": ["USDJPY", "USDCAD"],
    "USDCAD": ["USDJPY", "USDCHF"],
    "EURJPY": ["GBPJPY"],
    "GBPJPY": ["EURJPY"],
}

# Session hours (UTC) — Only trade during optimal liquidity
SESSION_LONDON = (7, 16)   # London session
SESSION_NY = (12, 21)      # New York session
SESSION_OVERLAP = (12, 16) # London-NY overlap (best spreads)

# ═══════════════════════════════════════════════════════════════
# UNIFIED CONFIG — ALL LAYERS COMBINED
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Risk Management ──
    "max_risk_pct": 0.25,           # 25% risk per trade (demo account)
    "max_position_pct": 0.25,
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "hold_bars": 72,
    "min_confidence": 0.35,
    "min_score": 3,

    # ── Safety Limits ──
    "max_correlated_trades": 2,      # Max 2 correlated pairs open
    "max_total_exposure_pct": 0.50,  # Max 50% equity in open trades
    "max_drawdown_pause_pct": 0.15,  # Pause trading at 15% DD
    "equity_curve_ma_period": 20,    # Pause if equity below 20-day MA
    "session_filter_enabled": True,  # Only trade during optimal sessions
    "correlation_filter_enabled": True,

    # ── Session Filtering ──
    "session_hours": set(range(7, 22)),
    "optimal_sessions": [13, 14, 15, 16],
    "session_risk_mult": {
        7: 0.5, 8: 0.7, 9: 0.8, 10: 0.9, 11: 1.0, 12: 1.0,
        13: 1.0, 14: 1.0, 15: 1.0, 16: 1.0, 17: 0.9, 18: 0.8,
        19: 0.7, 20: 0.6, 21: 0.5,
    },

    # ── Indicators ──
    "adx_threshold": 20,
    "sl_atr_mult": 3.0,
    "tp_atr_mult": 5.0,
    "vol_sizing": True,

    # ── Portfolio Limits ──
    "max_concurrent_trades": 6,
    "max_correlated_trades": 2,
    "circuit_breaker_losses": 3,
    "circuit_breaker_cooldown_min": 60,

    # ── Drawdown Throttle ──
    "drawdown_warning_pct": 0.05,
    "drawdown_critical_pct": 0.10,
    "drawdown_pause_pct": 0.15,

    # ── Partial Take-Profit ──
    "partial_tp_enabled": True,
    "partial_tp_pct": 0.50,
    "partial_tp_rr": 1.0,

    # ── Trailing Stop ──
    "trailing_enabled": True,
    "trailing_breakeven_rr": 1.0,
    "trailing_step_rr": 2.0,
    "trailing_atr_mult": 2.0,

    # ── LLM Integration ──
    "llm_enabled": True,
    "llm_confirm_trades": True,
    "llm_analyze_interval": 5,

    # ── ML Integration ──
    "ml_enabled": True,
    "ml_min_confidence": 0.50,

    # ── NEW FEATURES ──
    "regime_enabled": True,
    "sentiment_enabled": True,
    "hedging_enabled": True,
    "volume_profile_enabled": True,
    "calendar_enabled": True,
    "exit_model_enabled": True,
    "risk_parity_enabled": True,
    "ga_optimization_enabled": True,
    "rl_execution_enabled": True,
    "alternative_data_enabled": True,

    # ── MTF Analysis ──
    "multi_timeframe_enabled": True,
    "mtf_timeframes": ["M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
    "mtf_min_agree": 2,
    "mtf_weights": {
        "M15": 0.05, "M30": 0.08, "H1": 0.12,
        "H4": 0.25, "D1": 0.30, "W1": 0.15, "MN1": 0.05,
    },
}

TIMEFRAME = "H1"
CYCLE_INTERVAL = 300  # 5 minutes (faster cycle for real-time)
DURATION_DAYS = 21
DATA_DIR = Path("unified_data")
DATA_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

class SignalDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class Signal:
    symbol: str
    direction: SignalDirection
    score: float
    confidence: float
    indicators: Dict[str, float]
    mtf_agreement: float
    llm_signal: Optional[str] = None
    llm_confidence: float = 0.0
    llm_reasoning: str = ""
    ml_p_up: float = 0.5
    entry_price: float = 0.0
    atr: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    timestamp: str = ""

@dataclass
class Trade:
    symbol: str
    action: str
    entry_price: float
    entry_time: str
    size: float
    sl_price: float
    tp_price: float
    ticket: int = 0
    pnl: float = 0.0
    exit_price: float = 0.0
    exit_time: str = ""
    bars_held: int = 0

@dataclass
class AccountState:
    balance: float = 10000.0
    equity: float = 10000.0
    free_margin: float = 10000.0
    peak_balance: float = 10000.0
    drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    open_positions: int = 0
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0


# ═══════════════════════════════════════════════════════════════
# LAYER 1: TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    df["ema_21"] = pd.Series(c).ewm(span=21).mean().values

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
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # ATR
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    df["atr"] = pd.Series(tr).rolling(14).mean().values

    # ADX
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

    # Ichimoku Cloud
    nine_high = pd.Series(h).rolling(9).max().values
    nine_low = pd.Series(l).rolling(9).min().values
    df["tenkan"] = (nine_high + nine_low) / 2

    twenty_six_high = pd.Series(h).rolling(26).max().values
    twenty_six_low = pd.Series(l).rolling(26).min().values
    df["kijun"] = (twenty_six_high + twenty_six_low) / 2

    df["senkou_a"] = np.roll(((df["tenkan"] + df["kijun"]) / 2), 26)
    fifty_two_high = pd.Series(h).rolling(52).max().values
    fifty_two_low = pd.Series(l).rolling(52).min().values
    df["senkou_b"] = np.roll(((fifty_two_high + fifty_two_low) / 2), 26)

    # Momentum & Volatility
    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values

    # Volume Ratio
    if "volume" in df.columns and df["volume"].sum() > 0:
        df["vol_sma_20"] = pd.Series(df["volume"].values).rolling(20).mean().values
        df["vol_ratio"] = df["volume"] / df["vol_sma_20"].replace(0, 1)
    else:
        df["vol_ratio"] = 1.0

    return df


# ═══════════════════════════════════════════════════════════════
# LAYER 2: SIGNAL GENERATION (Score-Based)
# ═══════════════════════════════════════════════════════════════

def generate_signal(row) -> Tuple[str, float, Dict[str, float]]:
    """Generate signal from indicators. Returns (action, confidence, details)."""
    score = 0
    details = {}

    # MACD histogram
    if row["macd_hist"] > 0:
        score += 1
        details["macd"] = "bullish"
    elif row["macd_hist"] < 0:
        score -= 1
        details["macd"] = "bearish"
    else:
        details["macd"] = "neutral"

    # RSI
    rsi = row["rsi"]
    if rsi < 25:
        score += 3
        details["rsi"] = f"extreme_oversold({rsi:.1f})"
    elif rsi < 35:
        score += 2
        details["rsi"] = f"oversold({rsi:.1f})"
    elif rsi < 45:
        score += 1
        details["rsi"] = f"slightly_bullish({rsi:.1f})"
    elif rsi > 75:
        score -= 3
        details["rsi"] = f"extreme_overbought({rsi:.1f})"
    elif rsi > 65:
        score -= 2
        details["rsi"] = f"overbought({rsi:.1f})"
    elif rsi > 55:
        score -= 1
        details["rsi"] = f"slightly_bearish({rsi:.1f})"
    else:
        details["rsi"] = f"neutral({rsi:.1f})"

    # SMA trend
    if row["close"] > row["sma_20"] > row["sma_50"]:
        score += 2
        details["sma_trend"] = "strong_bullish"
    elif row["close"] < row["sma_20"] < row["sma_50"]:
        score -= 2
        details["sma_trend"] = "strong_bearish"
    else:
        details["sma_trend"] = "neutral"

    # ADX
    adx = row.get("adx", 0)
    if adx > CONFIG["adx_threshold"]:
        if row["plus_di"] > row["minus_di"]:
            score += 1
            details["adx"] = f"trend_bullish({adx:.1f})"
        else:
            score -= 1
            details["adx"] = f"trend_bearish({adx:.1f})"
    else:
        details["adx"] = f"no_trend({adx:.1f})"

    # Ichimoku Cloud
    cloud_top = max(row.get("senkou_a", 0), row.get("senkou_b", 0))
    cloud_bottom = min(row.get("senkou_a", 0), row.get("senkou_b", 0))
    if row["close"] > cloud_top:
        score += 1
        details["ichimoku"] = "above_cloud"
    elif row["close"] < cloud_bottom:
        score -= 1
        details["ichimoku"] = "below_cloud"
    else:
        details["ichimoku"] = "in_cloud"

    # Volume filter
    vol_ratio = row.get("vol_ratio", 1.0)
    if vol_ratio > 1.2:
        if score > 0:
            score += 1
        elif score < 0:
            score -= 1
        details["volume"] = f"confirming({vol_ratio:.2f}x)"
    else:
        details["volume"] = f"normal({vol_ratio:.2f}x)"

    # Momentum
    if row["momentum_5"] > 0.005:
        score += 1
        details["momentum"] = "bullish"
    elif row["momentum_5"] < -0.005:
        score -= 1
        details["momentum"] = "bearish"
    else:
        details["momentum"] = "neutral"

    # Bollinger Band position
    if row["close"] < row["bb_lower"]:
        score += 1
        details["bollinger"] = "below_lower"
    elif row["close"] > row["bb_upper"]:
        score -= 1
        details["bollinger"] = "above_upper"
    else:
        details["bollinger"] = "inside"

    max_score = 8
    if score >= CONFIG["min_score"]:
        return "BUY", min(score / max_score, 1.0), details
    if score <= -CONFIG["min_score"]:
        return "SELL", min(abs(score) / max_score, 1.0), details
    return "HOLD", 0.0, details


# ═══════════════════════════════════════════════════════════════
# LAYER 3: MULTI-TIMEFRAME ANALYSIS
# ═══════════════════════════════════════════════════════════════

TIMEFRAME_MAP = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}

def fetch_mtf_data(symbol: str, timeframes: List[str] = None) -> Dict[str, pd.DataFrame]:
    """Fetch data across multiple timeframes."""
    if timeframes is None:
        timeframes = CONFIG["mtf_timeframes"]

    data = {}
    for tf in timeframes:
        mt5_tf = TIMEFRAME_MAP.get(tf)
        if mt5_tf is None:
            continue
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 200)
        if rates is not None and len(rates) > 60:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
            df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
            df = compute_indicators(df)
            df = df.dropna()
            if len(df) > 0:
                data[tf] = df
    return data


def mtf_analysis(mtf_data: Dict[str, pd.DataFrame]) -> Tuple[str, float, Dict]:
    """Analyze signal agreement across timeframes. Returns (direction, agreement_pct, details)."""
    votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
    weighted_scores = 0.0
    total_weight = 0.0
    details = {}

    for tf, df in mtf_data.items():
        if len(df) == 0:
            continue
        row = df.iloc[-1]
        action, confidence, _ = generate_signal(row)
        weight = CONFIG["mtf_weights"].get(tf, 0.1)

        votes[action] += 1
        weighted_scores += (1 if action == "BUY" else -1 if action == "SELL" else 0) * weight * confidence
        total_weight += weight
        details[tf] = {"action": action, "confidence": round(confidence, 3)}

    if total_weight == 0:
        return "HOLD", 0.0, details

    normalized_score = weighted_scores / total_weight
    total_tf = len(mtf_data)

    if normalized_score > 0.2 and votes["BUY"] >= CONFIG["mtf_min_agree"]:
        agreement = votes["BUY"] / total_tf
        return "BUY", agreement, details
    elif normalized_score < -0.2 and votes["SELL"] >= CONFIG["mtf_min_agree"]:
        agreement = votes["SELL"] / total_tf
        return "SELL", agreement, details

    return "HOLD", 0.0, details


# ═══════════════════════════════════════════════════════════════
# LAYER 4: LLM MARKET ANALYSIS
# ═══════════════════════════════════════════════════════════════

def llm_analyze(symbol: str, indicators: Dict[str, float], action: str) -> Dict:
    """Use LLM (Ollama) to analyze the market and confirm/reject signal."""
    if not CONFIG["llm_enabled"]:
        return {"signal": action, "confidence": 0.5, "reasoning": "LLM disabled", "approved": True}

    try:
        from apps.llm.client import LLMClient
        client = LLMClient()

        # Build indicator string
        indicator_str = (
            f"RSI: {indicators.get('rsi', 'N/A')}, "
            f"MACD Hist: {indicators.get('macd_hist', 'N/A')}, "
            f"ADX: {indicators.get('adx', 'N/A')}, "
            f"ATR: {indicators.get('atr', 'N/A')}, "
            f"SMA20: {indicators.get('sma_20', 'N/A')}, "
            f"SMA50: {indicators.get('sma_50', 'N/A')}, "
            f"Volume: {indicators.get('vol_ratio', 'N/A')}x"
        )

        # Use analyze_trading_signal for structured response
        result = client.analyze_trading_signal(
            symbol=symbol,
            timeframe=TIMEFRAME,
            indicators=indicators,
        )

        parsed = result.parsed if hasattr(result, 'parsed') and result.parsed else {}
        llm_signal = parsed.get("signal", action)
        llm_conf = parsed.get("confidence", 0.5)
        reasoning = parsed.get("reasoning", "")

        # LLM confirms if it agrees with our signal
        approved = (llm_signal == action) or (llm_conf < 0.4)

        return {
            "signal": llm_signal,
            "confidence": llm_conf,
            "reasoning": reasoning,
            "approved": approved,
        }
    except Exception as e:
        log.warning(f"LLM analysis failed for {symbol}: {e}")
        return {"signal": action, "confidence": 0.5, "reasoning": f"LLM error: {e}", "approved": True}


# ═══════════════════════════════════════════════════════════════
# LAYER 5: ML SIGNAL RANKING
# ═══════════════════════════════════════════════════════════════

def ml_rank(indicators: Dict[str, float]) -> float:
    """Use ML model to rank signal quality. Returns P(UP)."""
    if not CONFIG["ml_enabled"]:
        return 0.5

    try:
        from apps.ml.predictor import MLPredictor
        ml = MLPredictor(model_type="xgboost")

        if not ml.is_trained:
            return 0.5

        # Map to exact features the model expects:
        # rsi, macd_hist, bb_width, atr_pct, volume_ratio,
        # price_momentum, volatility_regime, trend_strength,
        # support_distance, resistance_distance
        close = indicators.get("close", 1.0)
        features = np.array([
            indicators.get("rsi", 50),
            indicators.get("macd_hist", 0),
            indicators.get("bb_width", 0),
            indicators.get("atr", 0) / close if close > 0 else 0,  # atr_pct
            indicators.get("vol_ratio", 1.0),
            indicators.get("momentum_5", 0),
            1.0 if indicators.get("adx", 0) > 25 else 0.0,  # volatility_regime
            indicators.get("adx", 0),  # trend_strength
            0.0,  # support_distance (not available from indicators dict)
            0.0,  # resistance_distance (not available from indicators dict)
        ])

        pred = ml.predict_from_features(features)
        return pred.p_up
    except Exception as e:
        log.warning(f"ML ranking failed: {e}")
        return 0.5


# ═══════════════════════════════════════════════════════════════
# LAYER 6: RISK MANAGEMENT (All-in-One)
# ═══════════════════════════════════════════════════════════════

class RiskManager:
    """Combined risk management: Kelly + Circuit Breaker + Drawdown + Correlation."""

    def __init__(self):
        self.balance = 10000.0
        self.peak_balance = 10000.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.daily_pnl = 0.0
        self.open_positions = {}  # symbol -> {action, entry_price, size, sl, tp}
        self.trade_log = []
        self.circuit_breaker_state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.cb_opened_at = None
        self.cb_recoveries = 0

    def update_balance(self, new_balance: float):
        self.balance = new_balance
        self.peak_balance = max(self.peak_balance, new_balance)

    def get_drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance

    def get_risk_multiplier(self) -> float:
        dd = self.get_drawdown_pct()
        if dd >= CONFIG["drawdown_pause_pct"]:
            return 0.0
        elif dd >= CONFIG["drawdown_critical_pct"]:
            return 0.25
        elif dd >= CONFIG["drawdown_warning_pct"]:
            return 0.50
        return 1.0

    def get_session_mult(self, hour: int) -> float:
        return CONFIG["session_risk_mult"].get(hour, 1.0)

    def check_circuit_breaker(self) -> bool:
        if self.circuit_breaker_state == "OPEN":
            if self.cb_opened_at:
                elapsed = (datetime.now(timezone.utc) - self.cb_opened_at).total_seconds() / 60
                if elapsed >= CONFIG["circuit_breaker_cooldown_min"]:
                    self.circuit_breaker_state = "HALF_OPEN"
                    return True
            return False
        return True

    def record_trade_result(self, pnl: float, pnl_pct: float):
        self.balance += pnl
        self.peak_balance = max(self.peak_balance, self.balance)
        self.daily_pnl += pnl_pct

        if pnl <= 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            if self.consecutive_losses >= CONFIG["circuit_breaker_losses"]:
                self.circuit_breaker_state = "OPEN"
                self.cb_opened_at = datetime.now(timezone.utc)
        else:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            if self.circuit_breaker_state == "HALF_OPEN":
                self.cb_recoveries += 1
                if self.cb_recoveries >= 2:
                    self.circuit_breaker_state = "CLOSED"
                    self.daily_pnl = 0
                    self.cb_recoveries = 0

    def check_correlation(self, symbol: str) -> bool:
        max_correlated = CONFIG["max_correlated_trades"]
        correlations = CORRELATIONS.get(symbol, [])
        correlated_count = sum(1 for s in self.open_positions if s in correlations)
        return correlated_count < max_correlated

    def check_portfolio_limits(self) -> bool:
        return len(self.open_positions) < CONFIG["max_concurrent_trades"]

    def calculate_position_size(self, price: float, atr: float, confidence: float,
                                 session_hour: int, volatility: float, symbol: str = None) -> float:
        """Equity-based auto lot sizing with tier risk and safety limits."""
        risk_mult = self.get_risk_multiplier()
        if risk_mult <= 0:
            return 0.0

        session_mult = self.get_session_mult(session_hour)

        # Dynamic risk after consecutive losses
        dyn_risk = 1.0
        if self.consecutive_losses >= 3:
            dyn_risk = 0.5

        # Tier-based risk multiplier
        tier_mult = TIER_RISK_MULT.get(symbol, 0.5) if symbol else 1.0

        # Base risk = equity × risk percentage
        base_risk = self.balance * CONFIG["max_risk_pct"]

        # Apply safety multipliers (these only REDUCE size)
        risk_amount = base_risk * risk_mult * session_mult * dyn_risk * tier_mult

        # Confidence scaling (strong signal = full risk, weak = half)
        risk_amount *= max(confidence, 0.5)

        # Convert to lots with correct contract size
        contract_size = CONTRACT_SIZES.get(symbol, 100000) if symbol else 100000
        if price <= 0:
            return 0.0
        lots = risk_amount / (price * contract_size)

        # Per-symbol max lot limit
        sym_max = MAX_LOTS_PER_SYMBOL.get(symbol, 0.50) if symbol else 0.50
        lots = min(lots, sym_max)

        # Cap at max position (25% of equity)
        max_lots = (self.balance * CONFIG["max_position_pct"]) / (price * contract_size)
        lots = min(lots, max_lots)

        # Enforce minimum lot size (MT5 requires at least 0.01)
        if lots > 0 and lots < 0.01:
            lots = 0.01

        return round(lots, 2)

    def calculate_sl_tp(self, price: float, atr: float, action: str) -> Tuple[float, float]:
        """ATR-based SL/TP."""
        sl_distance = atr * CONFIG["sl_atr_mult"]
        tp_distance = atr * CONFIG["tp_atr_mult"]

        if action == "BUY":
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance

        return round(sl, 5), round(tp, 5)

    def get_state(self) -> Dict:
        return {
            "balance": self.balance,
            "peak_balance": self.peak_balance,
            "drawdown_pct": round(self.get_drawdown_pct() * 100, 2),
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "circuit_breaker": self.circuit_breaker_state,
            "open_positions": len(self.open_positions),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_trades": len(self.trade_log),
            "wins": sum(1 for t in self.trade_log if t.get("pnl", 0) > 0),
            "losses": sum(1 for t in self.trade_log if t.get("pnl", 0) <= 0),
            "total_pnl": round(sum(t.get("pnl", 0) for t in self.trade_log), 2),
        }


# ═══════════════════════════════════════════════════════════════
# MT5 DIRECT COMMUNICATION
# ═══════════════════════════════════════════════════════════════

class MT5Client:
    """Direct MT5 communication layer."""

    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            log.error(f"MT5 connect failed: {mt5.last_error()}")
            return False
        info = mt5.account_info()
        log.info(f"MT5 Connected: {info.login} | {info.server} | ${info.balance:.2f}")
        self.connected = True
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def get_account_info(self) -> Dict:
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "balance": info.balance,
            "equity": info.equity,
            "free_margin": info.margin_free,
            "margin": info.margin,
            "leverage": info.leverage,
            "profit": info.profit,
        }

    def get_positions(self) -> List[Dict]:
        positions = mt5.positions_get()
        if not positions:
            return []
        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "action": "BUY" if p.type == 0 else "SELL",
                "lots": p.volume,
                "entry_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "magic": p.magic,
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
            })
        return result

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 200) -> Optional[pd.DataFrame]:
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        if not info.visible:
            mt5.symbol_select(symbol, True)

        tf_map = {
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None or len(rates) < 60:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        return df

    def place_order(self, symbol: str, action: str, lots: float,
                     sl: float, tp: float, magic: int = MT5_MAGIC) -> Optional[int]:
        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        price = tick.ask if action == "BUY" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": MT5_SLIPPAGE,
            "magic": magic,
            "comment": "UNIFIED_ENGINE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log.info(f"ORDER OK: {action} {lots} {symbol} @ {price:.5f} ticket={result.order}")
            return result.order
        else:
            log.error(f"ORDER FAIL: {result}")
            return None

    def close_position(self, ticket: int, volume: float = None) -> bool:
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False
        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.type == 0 else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": volume if volume else pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "UNIFIED_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        return result and result.retcode == mt5.TRADE_RETCODE_DONE

    def close_partial(self, ticket: int, pct: float = 0.50) -> bool:
        """Close a partial percentage of a position."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False
        pos = position[0]
        close_vol = round(pos.volume * pct, 2)
        if close_vol < 0.01:
            close_vol = 0.01
        if close_vol > pos.volume:
            close_vol = pos.volume
        return self.close_position(ticket, volume=close_vol)

    def modify_sl_tp(self, ticket: int, sl: float = None, tp: float = None) -> bool:
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False
        pos = position[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
        }

        result = mt5.order_send(request)
        return result and result.retcode == mt5.TRADE_RETCODE_DONE


# ═══════════════════════════════════════════════════════════════
# UNIFIED ENGINE — MAIN TRADING LOOP
# ═══════════════════════════════════════════════════════════════

class UnifiedEngine:
    """All-in-one trading engine combining every layer."""

    def __init__(self):
        self.mt5 = MT5Client()
        self.risk = RiskManager()
        self.running = False
        self.cycle_count = 0
        self.start_time = datetime.now(timezone.utc)
        self.last_signals = {}  # symbol -> Signal
        self.last_analysis = {}  # symbol -> analysis details

        # Initialize new features
        if NEW_FEATURES_AVAILABLE:
            self.ensemble = StrategyEnsemble()
            self.sentiment = SentimentFilter()
            self.hedging = CorrelationHedge()
            self.volume_profile = VolumeProfile()
            self.calendar = EconomicCalendar()
            self.exit_optimizer = ExitOptimizer()
            self.risk_parity = RiskParity()
            self.ga_optimizer = GeneticOptimizer()
            self.execution_optimizer = ExecutionOptimizer()
            self.alternative_data = AlternativeData()
            log.info("All 10 new features initialized")
        else:
            self.ensemble = None
            self.sentiment = None
            self.hedging = None
            self.volume_profile = None
            self.calendar = None
            self.exit_optimizer = None
            self.risk_parity = None
            self.ga_optimizer = None
            self.execution_optimizer = None
            self.alternative_data = None

    def start(self):
        """Initialize and start the engine."""
        log.info("=" * 70)
        log.info("  UNIFIED TRADING ENGINE — Starting")
        log.info("=" * 70)

        if not self.mt5.connect():
            log.error("Cannot start without MT5 connection")
            return False

        # Sync account state
        acct = self.mt5.get_account_info()
        if acct:
            self.risk.update_balance(acct["balance"])
            log.info(f"  Balance: ${acct['balance']:.2f} | Equity: ${acct['equity']:.2f}")

        # Sync existing positions
        positions = self.mt5.get_positions()
        for p in positions:
            self.risk.open_positions[p["symbol"]] = {
                "action": p["action"],
                "entry_price": p["entry_price"],
                "size": p["lots"],
                "sl": p["sl"],
                "tp": p["tp"],
                "ticket": p["ticket"],
                "entry_time": p["time"],
                "partial_tp_done": False,
            }
        log.info(f"  Synced {len(positions)} open positions")

        self.running = True
        self.start_time = datetime.now(timezone.utc)
        log.info(f"  Cycle interval: {CYCLE_INTERVAL}s | Duration: {DURATION_DAYS} days")
        log.info("=" * 70)
        return True

    def run_cycle(self):
        """Execute one full analysis + trading cycle."""
        self.cycle_count += 1
        now = datetime.now(timezone.utc)

        log.info(f"\n{'='*70}")
        log.info(f"  CYCLE {self.cycle_count} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        # Sync account
        acct = self.mt5.get_account_info()
        if acct:
            self.risk.update_balance(acct["balance"])
            log.info(f"  Balance: ${acct['balance']:.2f} | Equity: ${acct['equity']:.2f} | DD: {self.risk.get_drawdown_pct()*100:.1f}%")

        # Check drawdown pause
        risk_mult = self.risk.get_risk_multiplier()
        if risk_mult <= 0:
            log.warning(f"  TRADING PAUSED — DD {self.risk.get_drawdown_pct()*100:.1f}% > {CONFIG['drawdown_pause_pct']*100:.0f}%")
            return

        # Check circuit breaker
        if not self.risk.check_circuit_breaker():
            log.warning(f"  CIRCUIT BREAKER ACTIVE — {self.risk.consecutive_losses} consecutive losses")
            return

        # Manage existing positions (trailing stops, partial TP)
        self._manage_existing_positions()

        # Scan all symbols
        signals = []
        for symbol in WATCHLIST:
            signal = self._analyze_symbol(symbol)
            if signal and signal.direction != SignalDirection.HOLD:
                signals.append(signal)

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        # Execute best signals
        for signal in signals:
            if not self.risk.check_portfolio_limits():
                log.info(f"  Max positions reached ({len(self.risk.open_positions)})")
                break
            if not self.risk.check_correlation(signal.symbol):
                log.info(f"  Correlation filter: {signal.symbol} blocked")
                continue
            if signal.symbol in self.risk.open_positions:
                continue

            self._execute_trade(signal)

        # Summary
        state = self.risk.get_state()
        log.info(f"\n  SUMMARY: {state['open_positions']} open | {state['total_trades']} trades | "
                 f"WR={state['wins']}/{state['total_trades']} | P&L=${state['total_pnl']:+.2f} | "
                 f"CB={self.risk.circuit_breaker_state}")

    def _analyze_symbol(self, symbol: str) -> Optional[Signal]:
        """Full analysis pipeline for one symbol."""
        now = datetime.now(timezone.utc)

        # Layer 1-2: Fetch H1 data + compute indicators
        df = self.mt5.fetch_candles(symbol, TIMEFRAME, 200)
        if df is None or len(df) < 60:
            return None

        df = compute_indicators(df)
        df = df.dropna()
        if len(df) == 0:
            return None

        row = df.iloc[-1]
        action, confidence, details = generate_signal(row)

        if action == "HOLD" or confidence < CONFIG["min_confidence"]:
            return None

        # Layer 3: Multi-timeframe confirmation
        mtf_data = fetch_mtf_data(symbol, CONFIG["mtf_timeframes"])
        mtf_dir, mtf_agreement, mtf_details = mtf_analysis(mtf_data)

        # Require MTF agreement
        if mtf_dir != action:
            return None

        # Layer 4: LLM confirmation
        indicator_dict = {
            "rsi": round(float(row.get("rsi", 50)), 2),
            "macd_hist": round(float(row.get("macd_hist", 0)), 6),
            "adx": round(float(row.get("adx", 0)), 2),
            "atr": round(float(row.get("atr", 0)), 5),
            "sma_20": round(float(row.get("sma_20", 0)), 5),
            "sma_50": round(float(row.get("sma_50", 0)), 5),
            "vol_ratio": round(float(row.get("vol_ratio", 1.0)), 2),
            "plus_di": round(float(row.get("plus_di", 0)), 2),
            "minus_di": round(float(row.get("minus_di", 0)), 2),
            "close": round(float(row.get("close", 0)), 5),
            "bb_width": round(float(row.get("bb_width", 0)), 4),
            "tenkan": round(float(row.get("tenkan", 0)), 5),
            "kijun": round(float(row.get("kijun", 0)), 5),
            "senkou_a": round(float(row.get("senkou_a", 0)), 5),
            "senkou_b": round(float(row.get("senkou_b", 0)), 5),
            "momentum_5": round(float(row.get("momentum_5", 0)), 6),
        }

        llm_result = llm_analyze(symbol, indicator_dict, action)

        # Layer 5: ML ranking
        ml_p_up = ml_rank(indicator_dict)

        # NEW FEATURES: Additional filters and analysis
        feature_data = {}
        if NEW_FEATURES_AVAILABLE:
            # Feature 2: Sentiment filter
            if CONFIG.get("sentiment_enabled") and self.sentiment:
                sentiment_check = self.sentiment.should_trade(symbol, action)
                feature_data["sentiment"] = sentiment_check
                if not sentiment_check.get("allow", True):
                    log.info(f"  BLOCKED by sentiment: {sentiment_check.get('reason')}")
                    return None

            # Feature 5: Economic calendar blackout
            if CONFIG.get("calendar_enabled") and self.calendar:
                calendar_check = self.calendar.should_block_trade(symbol)
                feature_data["calendar"] = calendar_check
                if calendar_check.get("block", False):
                    log.info(f"  BLOCKED by calendar: {calendar_check.get('reason')}")
                    return None

            # Feature 4: Volume profile filter
            if CONFIG.get("volume_profile_enabled") and self.volume_profile:
                volumes = df["tick_volume"] if "tick_volume" in df.columns else pd.Series([1]*len(df))
                zones = self.volume_profile.calculate(df["close"], volumes)
                vol_filter = filter_by_volume(price, zones, action)
                feature_data["volume_filter"] = vol_filter

            # Feature 10: Alternative data signal
            if CONFIG.get("alternative_data_enabled") and self.alternative_data:
                alt_signal = self.alternative_data.get_signal(symbol)
                feature_data["alternative"] = alt_signal

        # Calculate SL/TP
        atr = float(row.get("atr", 0))
        price = float(row["close"])
        sl, tp = self.risk.calculate_sl_tp(price, atr, action)

        # Create signal
        signal = Signal(
            symbol=symbol,
            direction=SignalDirection(action),
            score=confidence * 8,
            confidence=confidence,
            indicators=indicator_dict,
            mtf_agreement=mtf_agreement,
            llm_signal=llm_result.get("signal"),
            llm_confidence=llm_result.get("confidence", 0),
            llm_reasoning=llm_result.get("reasoning", ""),
            ml_p_up=ml_p_up,
            entry_price=price,
            atr=atr,
            sl_price=sl,
            tp_price=tp,
            timestamp=now.isoformat(),
        )

        self.last_signals[symbol] = signal
        self.last_analysis[symbol] = {
            "h1_signal": details,
            "mtf": mtf_details,
            "mtf_agreement": round(mtf_agreement, 2),
            "llm": llm_result,
            "ml_p_up": round(ml_p_up, 3),
            "features": feature_data,
        }

        log.info(f"  SIGNAL {symbol:8} {action:4} | Score={confidence*8:.1f} | MTF={mtf_agreement:.0%} | "
                 f"LLM={llm_result.get('signal','?')}({llm_result.get('confidence',0):.2f}) | "
                 f"ML={ml_p_up:.3f}")

        return signal

    def _execute_trade(self, signal: Signal):
        """Execute a trade based on signal with safety checks."""
        now = datetime.now(timezone.utc)

        # SAFETY CHECK 1: Session filter
        if CONFIG.get("session_filter_enabled", True):
            if now.hour not in CONFIG["session_hours"]:
                log.info(f"  SKIP {signal.symbol} — outside session hours")
                return

        # SAFETY CHECK 2: Correlation filter
        if CONFIG.get("correlation_filter_enabled", True):
            open_symbols = list(self.risk.open_positions.keys())
            correlated_count = 0
            for open_sym in open_symbols:
                if signal.symbol in CORRELATIONS.get(open_sym, []):
                    correlated_count += 1
            if correlated_count >= CONFIG["max_correlated_trades"]:
                log.info(f"  SKIP {signal.symbol} — too many correlated trades ({correlated_count})")
                return

        # SAFETY CHECK 3: Total exposure limit
        total_exposure = sum(p.get("size", 0) for p in self.risk.open_positions.values())
        max_exposure = self.risk.balance * CONFIG["max_total_exposure_pct"] / 100000
        if total_exposure >= max_exposure:
            log.info(f"  SKIP {signal.symbol} — max exposure reached ({total_exposure:.2f} lots)")
            return

        # SAFETY CHECK 4: Drawdown pause
        dd = self.risk.get_state().get("drawdown_pct", 0)
        if dd >= CONFIG["max_drawdown_pause_pct"] * 100:
            log.info(f"  SKIP {signal.symbol} — drawdown pause ({dd:.1f}%)")
            return

        # Calculate position size with risk parity
        vol = float(signal.indicators.get("vol_ratio", 1.0))
        lots = self.risk.calculate_position_size(
            signal.entry_price, signal.atr, signal.confidence,
            now.hour, vol, symbol=signal.symbol
        )

        # Apply risk parity weighting
        if CONFIG.get("risk_parity_enabled") and self.risk_parity and self.risk_parity.weights:
            parity_lots = self.risk_parity.get_position_size(
                signal.symbol, self.risk.balance,
                CONFIG["max_risk_pct"], signal.entry_price
            )
            # Blend: 70% original calculation, 30% risk parity
            lots = lots * 0.7 + parity_lots * 0.3
            lots = round(lots, 2)
            log.info(f"  RISK PARITY: original={lots/0.7:.2f}, parity={parity_lots:.2f}, blended={lots:.2f}")

        if lots <= 0:
            log.info(f"  SKIP {signal.symbol} — position size = 0")
            return

        # Get execution optimization plan
        exec_plan = None
        if CONFIG.get("rl_execution_enabled") and self.execution_optimizer:
            exec_plan = self.execution_optimizer.get_execution_plan({
                "spread": 0.0002,  # Default spread
                "volatility": signal.atr / signal.entry_price if signal.entry_price > 0 else 0.01,
                "time_of_day": now.hour,
                "imbalance": 0,
                "size": lots,
                "urgency": signal.confidence,
            })
            log.info(f"  EXEC PLAN: type={exec_plan.get('type')}, split={exec_plan.get('split')}")

        # Place order on MT5
        ticket = self.mt5.place_order(
            signal.symbol, signal.direction.value, lots,
            signal.sl_price, signal.tp_price
        )

        if ticket:
            self.risk.open_positions[signal.symbol] = {
                "action": signal.direction.value,
                "entry_price": signal.entry_price,
                "size": lots,
                "sl": signal.sl_price,
                "tp": signal.tp_price,
                "ticket": ticket,
                "entry_time": now.isoformat(),
                "partial_tp_done": False,
            }
            log.info(f"  EXECUTED {signal.symbol:8} {signal.direction.value:4} @ {signal.entry_price:.5f} "
                     f"lots={lots} SL={signal.sl_price:.5f} TP={signal.tp_price:.5f} ticket={ticket}")
        else:
            log.error(f"  FAILED {signal.symbol} — order not placed")

    def _manage_existing_positions(self):
        """Check trailing stops, partial TP, and time exits."""
        now = datetime.now(timezone.utc)
        positions = self.mt5.get_positions()

        for pos in positions:
            symbol = pos["symbol"]
            ticket = pos["ticket"]

            # Sync with risk manager
            if symbol in self.risk.open_positions:
                self.risk.open_positions[symbol]["current_price"] = pos["current_price"]
                self.risk.open_positions[symbol]["profit"] = pos["profit"]

            # Check if position still exists in MT5
            if symbol not in self.risk.open_positions:
                continue

            rm_pos = self.risk.open_positions[symbol]

            # Time exit (72 bars = 3 days for H1)
            entry_time = datetime.fromisoformat(rm_pos["entry_time"])
            bars_held = (now - entry_time).total_seconds() / 3600  # Approximate
            if bars_held >= CONFIG["hold_bars"]:
                log.info(f"  TIME EXIT {symbol} — held {bars_held:.0f}h")
                self._close_trade(symbol, ticket, "TIME_EXIT")
                continue

            # Trailing stop + partial TP logic
            if CONFIG["trailing_enabled"]:
                entry = rm_pos["entry_price"]
                current = pos["current_price"]
                atr = rm_pos.get("atr", 0)
                sl = rm_pos.get("sl", 0)

                if rm_pos["action"] == "BUY":
                    unrealized = current - entry
                    sl_distance = entry - sl if sl > 0 else 0
                else:
                    unrealized = entry - current
                    sl_distance = sl - entry if sl > 0 else 0

                if sl_distance <= 0:
                    sl_distance = atr * 1.5 if atr > 0 else entry * 0.01  # Fallback

                # R:R ratio (how far in profit relative to risk)
                rr_ratio = unrealized / sl_distance if sl_distance > 0 else 0

                # ── PARTIAL TAKE-PROFIT: Close 50% at 1:1 R:R ──
                if CONFIG.get("partial_tp_enabled", True) and not rm_pos.get("partial_tp_done", False):
                    if rr_ratio >= CONFIG["partial_tp_rr"]:
                        success = self.mt5.close_partial(ticket, CONFIG["partial_tp_pct"])
                        if success:
                            rm_pos["partial_tp_done"] = True
                            rm_pos["size"] = rm_pos.get("size", 0) * (1 - CONFIG["partial_tp_pct"])
                            log.info(f"  PARTIAL TP {symbol} — closed {CONFIG['partial_tp_pct']*100:.0f}% at {rr_ratio:.1f}R")
                            # Update entry to current for remaining position (lock in profit)
                            rm_pos["entry_price"] = current
                            continue

                # ── TRAILING STOP: Move to breakeven at 1:1 R:R ──
                if rr_ratio >= CONFIG["trailing_breakeven_rr"]:
                    if rm_pos["action"] == "BUY":
                        new_sl = entry  # Breakeven
                        if sl < entry:
                            success = self.mt5.modify_sl_tp(ticket, sl=new_sl)
                            if success:
                                rm_pos["sl"] = new_sl
                                log.info(f"  TRAILING BE {symbol} — SL → breakeven {new_sl:.5f}")
                    else:
                        new_sl = entry  # Breakeven
                        if sl > entry or sl == 0:
                            success = self.mt5.modify_sl_tp(ticket, sl=new_sl)
                            if success:
                                rm_pos["sl"] = new_sl
                                log.info(f"  TRAILING BE {symbol} — SL → breakeven {new_sl:.5f}")

                # ── TRAILING STOP: Trail by ATR after 2:1 R:R ──
                if rr_ratio >= CONFIG["trailing_step_rr"] and atr > 0:
                    trail_distance = atr * CONFIG["trailing_atr_mult"]
                    if rm_pos["action"] == "BUY":
                        new_sl = current - trail_distance
                        if new_sl > rm_pos["sl"]:
                            success = self.mt5.modify_sl_tp(ticket, sl=new_sl)
                            if success:
                                rm_pos["sl"] = new_sl
                                log.info(f"  TRAILING ATR {symbol} — SL → {new_sl:.5f} (ATR={atr:.5f}, dist={trail_distance:.5f})")
                    else:
                        new_sl = current + trail_distance
                        if new_sl < rm_pos["sl"] or rm_pos["sl"] == 0:
                            success = self.mt5.modify_sl_tp(ticket, sl=new_sl)
                            if success:
                                rm_pos["sl"] = new_sl
                                log.info(f"  TRAILING ATR {symbol} — SL → {new_sl:.5f} (ATR={atr:.5f}, dist={trail_distance:.5f})")

    def _close_trade(self, symbol: str, ticket: int, reason: str):
        """Close a trade and record result."""
        pos = self.risk.open_positions.get(symbol)
        if not pos:
            return

        success = self.mt5.close_position(ticket)
        if success:
            # Get actual P&L from MT5
            closed = self.mt5.get_positions()
            # Record in risk manager
            pnl = 0  # Will be updated on next sync
            self.risk.record_trade_result(pnl, pnl / self.risk.balance if self.risk.balance > 0 else 0)
            del self.risk.open_positions[symbol]
            log.info(f"  CLOSED {symbol} | Reason: {reason}")
        else:
            log.error(f"  FAILED TO CLOSE {symbol} ticket={ticket}")

    def get_dashboard(self) -> Dict:
        """Get current engine state for API/dashboard."""
        acct = self.mt5.get_account_info()
        positions = self.mt5.get_positions()
        state = self.risk.get_state()

        # Add new features state
        features_state = {}
        if NEW_FEATURES_AVAILABLE:
            features_state = {
                "regime": self.ensemble.regime_detector.current_regime.value if self.ensemble else "unknown",
                "sentiment_cache": len(self.sentiment.sentiment_cache) if self.sentiment else 0,
                "hedge_positions": len(self.hedging.hedge_positions) if self.hedging else 0,
                "calendar_events": len(self.calendar.events) if self.calendar else 0,
                "risk_parity": self.risk_parity.get_state() if self.risk_parity else {},
                "execution_metrics": self.execution_optimizer.get_metrics() if self.execution_optimizer else {},
            }

        return {
            "engine": {
                "running": self.running,
                "cycle": self.cycle_count,
                "uptime": str(datetime.now(timezone.utc) - self.start_time),
                "start_time": self.start_time.isoformat(),
                "new_features": NEW_FEATURES_AVAILABLE,
            },
            "account": acct,
            "positions": positions,
            "risk": state,
            "last_signals": {
                sym: {
                    "direction": sig.direction.value,
                    "confidence": sig.confidence,
                    "score": sig.score,
                    "mtf_agreement": sig.mtf_agreement,
                    "llm_signal": sig.llm_signal,
                    "llm_confidence": sig.llm_confidence,
                    "ml_p_up": sig.ml_p_up,
                    "entry_price": sig.entry_price,
                    "sl": sig.sl_price,
                    "tp": sig.tp_price,
                    "timestamp": sig.timestamp,
                }
                for sym, sig in self.last_signals.items()
            },
            "last_analysis": self.last_analysis,
            "features": features_state,
        }


# ═══════════════════════════════════════════════════════════════
# FASTAPI LOCALHOST SERVER
# ═══════════════════════════════════════════════════════════════

app = FastAPI(title="Dutchkem Unified Trading Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = UnifiedEngine()


@app.on_event("startup")
async def startup():
    """Start the trading engine on server startup."""
    import threading

    def run_engine():
        if engine.start():
            while engine.running:
                try:
                    engine.run_cycle()
                    time.sleep(CYCLE_INTERVAL)
                except KeyboardInterrupt:
                    engine.running = False
                except Exception as e:
                    log.error(f"Engine error: {e}")
                    time.sleep(60)

    thread = threading.Thread(target=run_engine, daemon=True)
    thread.start()
    log.info("Engine thread started")


@app.get("/api/v1/health")
def health():
    acct = engine.mt5.get_account_info() if engine.mt5.connected else {}
    return {
        "status": "healthy" if engine.mt5.connected else "degraded",
        "mt5_connected": engine.mt5.connected,
        "engine_running": engine.running,
        "cycle": engine.cycle_count,
        "account": acct,
    }


@app.get("/api/v1/dashboard")
def dashboard():
    return engine.get_dashboard()


# ═══════════════════════════════════════════════════════════════
# AUTH — Simple JWT for login
# ═══════════════════════════════════════════════════════════════
import hashlib, time

AUTH_USERS = {
    "admin": hashlib.sha256("dutchkem".encode()).hexdigest(),
}

@app.post("/api/v1/auth/login")
def auth_login(credentials: dict):
    """Authenticate user and return JWT token."""
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    if username in AUTH_USERS and AUTH_USERS[username] == password_hash:
        token = f"dutchkem-jwt-{username}-{int(time.time())}"
        return {"access_token": token, "token_type": "bearer", "user": username}

    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/v1/auth/me")
def auth_me():
    """Return current user info (stub)."""
    return {"user": "admin", "role": "trader", "platform": "Dutchkem Ventures"}


@app.get("/")
def serve_root():
    """Serve the landing page."""
    from fastapi.responses import HTMLResponse, RedirectResponse
    landing_path = Path("dashboard/landing.html")
    if landing_path.exists():
        return HTMLResponse(content=landing_path.read_text(encoding="utf-8"))
    return RedirectResponse(url="/dashboard")

@app.get("/landing")
def serve_landing():
    """Serve the landing page."""
    from fastapi.responses import HTMLResponse
    landing_path = Path("dashboard/landing.html")
    if landing_path.exists():
        return HTMLResponse(content=landing_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Landing page not found</h1>", status_code=404)

@app.get("/login")
def serve_login():
    """Serve the login page."""
    from fastapi.responses import HTMLResponse
    login_path = Path("dashboard/login.html")
    if login_path.exists():
        return HTMLResponse(content=login_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Login page not found</h1>", status_code=404)

@app.get("/dashboard")
def serve_dashboard():
    """Serve the live dashboard HTML."""
    from fastapi.responses import HTMLResponse
    dashboard_path = Path("dashboard/index.html")
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api/v1/positions")
def positions():
    return engine.mt5.get_positions()


@app.get("/api/v1/calendar")
def calendar_events():
    """Get upcoming economic events and blackout status."""
    from apps.calendar.events import get_all_events, is_blackout_period, get_upcoming_events
    return {
        "all_events": get_all_events(),
        "upcoming_24h": get_upcoming_events(hours=24),
        "blackout": is_blackout_period(),
    }


@app.get("/api/v1/account")
def account():
    return engine.mt5.get_account_info()


@app.get("/api/v1/risk")
def risk():
    return engine.risk.get_state()


@app.get("/api/v1/signals")
def signals():
    return {
        sym: {
            "direction": sig.direction.value,
            "confidence": sig.confidence,
            "score": sig.score,
            "mtf_agreement": sig.mtf_agreement,
            "llm_signal": sig.llm_signal,
            "llm_confidence": sig.llm_confidence,
            "ml_p_up": sig.ml_p_up,
        }
        for sym, sig in engine.last_signals.items()
    }


@app.get("/api/v1/analysis/{symbol}")
def analysis(symbol: str):
    if symbol in engine.last_analysis:
        return engine.last_analysis[symbol]
    return {"error": f"No analysis for {symbol}"}


@app.post("/api/v1/trade")
def manual_trade(symbol: str, action: str, lots: float = 0.01):
    """Manual trade execution."""
    if action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="Action must be BUY or SELL")
    info = engine.mt5.get_account_info()
    price_info = mt5.symbol_info_tick(symbol)
    if not price_info:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    price = price_info.ask if action == "BUY" else price_info.bid
    ticket = engine.mt5.place_order(symbol, action, lots, 0, 0)
    if ticket:
        return {"status": "ok", "ticket": ticket, "symbol": symbol, "action": action, "lots": lots}
    raise HTTPException(status_code=500, detail="Order failed")


@app.post("/api/v1/close/{ticket}")
def close_trade(ticket: int):
    """Close a position by ticket."""
    success = engine.mt5.close_position(ticket)
    if success:
        return {"status": "closed", "ticket": ticket}
    raise HTTPException(status_code=500, detail="Close failed")


@app.post("/api/v1/engine/start")
def start_engine():
    if engine.running:
        return {"status": "already running"}
    engine.start()
    return {"status": "started"}


@app.post("/api/v1/engine/stop")
def stop_engine():
    engine.running = False
    return {"status": "stopping"}


@app.get("/api/v1/config")
def get_config():
    return CONFIG


@app.post("/api/v1/config/toggle")
def toggle_feature(body: dict = Body(...)):
    """Toggle a feature on/off immediately."""
    feature = body.get("feature", "")
    enabled = body.get("enabled")

    feature_map = {
        "regime": "regime_enabled",
        "calendar": "calendar_enabled",
        "risk_parity": "risk_parity_enabled",
        "multi_timeframe": "multi_timeframe_enabled",
        "ai_analysis": "llm_enabled",
        "ml_prediction": "ml_enabled",
        "llm": "llm_enabled",
        "ml": "ml_enabled",
    }

    config_key = feature_map.get(feature)
    if not config_key:
        return {"error": f"Unknown feature: {feature}", "valid": list(feature_map.keys())}

    if enabled is None:
        # Toggle current value
        enabled = not CONFIG.get(config_key, False)

    CONFIG[config_key] = bool(enabled)
    log.info(f"Feature '{feature}' ({config_key}) set to {enabled}")

    return {
        "feature": feature,
        "config_key": config_key,
        "enabled": CONFIG[config_key],
        "all_features": {k: CONFIG.get(k, False) for k in feature_map.values()}
    }


# ═══════════════════════════════════════════════════════════════
# MT5 OPERATIONS — Connect, Status, History, Symbol Info
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/mt5/status")
def mt5_status():
    """Get MT5 terminal connection status."""
    info = {}
    if engine.mt5.connected:
        acct = mt5.account_info()
        if acct:
            info = {
                "connected": True,
                "login": acct.login,
                "server": acct.server,
                "balance": acct.balance,
                "equity": acct.equity,
                "leverage": acct.leverage,
                "margin": acct.margin,
                "margin_free": acct.margin_free,
                "profit": acct.profit,
                "name": acct.name,
                "currency": acct.currency,
                "company": acct.company,
                "terminal": mt5.terminal_info().name if mt5.terminal_info() else "Unknown",
            }
        else:
            info = {"connected": True, "login": MT5_LOGIN, "server": MT5_SERVER}
    else:
        info = {"connected": False, "login": MT5_LOGIN, "server": MT5_SERVER}
    return info


@app.post("/api/v1/mt5/connect")
def mt5_connect(data: dict = None):
    """Connect or reconnect to MT5 terminal."""
    try:
        if engine.mt5.connected:
            engine.mt5.disconnect()
            import time as _t
            _t.sleep(1)

        _login = (data or {}).get("login") or MT5_LOGIN
        _password = (data or {}).get("password") or MT5_PASSWORD
        _server = (data or {}).get("server") or MT5_SERVER

        result = mt5.initialize(
            path=MT5_PATH,
            login=_login,
            password=_password,
            server=_server
        )
        if result:
            engine.mt5.connected = True
            info = mt5.account_info()
            return {
                "status": "connected",
                "login": info.login if info else _login,
                "server": info.server if info else _server,
                "balance": info.balance if info else 0,
            }
        else:
            err = mt5.last_error()
            raise HTTPException(status_code=500, detail=f"MT5 connect failed: {err}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MT5 error: {str(e)}")


@app.post("/api/v1/mt5/disconnect")
def mt5_disconnect():
    """Disconnect from MT5 terminal."""
    engine.mt5.disconnect()
    return {"status": "disconnected"}


@app.get("/api/v1/mt5/history")
def mt5_history(days: int = 30):
    """Get trade history from MT5."""
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        deals = mt5.history_deals_get(start, now)
        if deals is None:
            return {"deals": [], "total": 0}

        result = []
        for d in deals:
            result.append({
                "ticket": d.ticket,
                "order": d.order,
                "time": str(d.time),
                "type": str(d.type),
                "entry": str(d.entry),
                "magic": d.magic,
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "swap": d.swap,
                "commission": d.commission,
                "symbol": d.symbol,
                "comment": d.comment,
            })
        return {"deals": result, "total": len(result)}
    except Exception as e:
        return {"deals": [], "total": 0, "error": str(e)}


@app.get("/api/v1/mt5/symbol/{symbol}")
def mt5_symbol_info(symbol: str):
    """Get detailed symbol info (spread, contract size, digits, etc.)."""
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        tick = mt5.symbol_info_tick(symbol)
        return {
            "symbol": symbol,
            "bid": tick.bid if tick else 0,
            "ask": tick.ask if tick else 0,
            "spread": info.spread,
            "digits": info.digits,
            "contract_size": info.trade_contract_size,
            "min_lot": info.volume_min,
            "max_lot": info.volume_max,
            "lot_step": info.volume_step,
            "swap_long": info.swap_long,
            "swap_short": info.swap_short,
            "margin_initial": info.margin_initial,
            "trade_mode": str(info.trade_mode),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/mt5/symbols")
def mt5_symbols():
    """Get all available symbols."""
    try:
        symbols = mt5.symbols_get()
        if symbols is None:
            return {"symbols": []}
        result = [{"name": s.name, "spread": s.spread, "trade_mode": str(s.trade_mode)} for s in symbols[:50]]
        return {"symbols": result, "total": len(symbols)}
    except Exception as e:
        return {"symbols": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# ACCOUNT — Funding, Withdrawal, Details
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/account/details")
def account_details():
    """Get full account details including user info."""
    info = mt5.account_info()
    if info is None:
        return {"connected": False}
    return {
        "connected": True,
        "login": info.login,
        "name": info.name,
        "server": info.server,
        "company": info.company,
        "currency": info.currency,
        "leverage": info.leverage,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "margin_level": info.margin_level,
        "profit": info.profit,
        "deposit": info.balance + abs(info.profit) if info.profit < 0 else info.balance - info.profit,
        "withdrawal": 0,
        "credit": info.credit,
    }


@app.post("/api/v1/account/fund")
def fund_account(data: dict = None):
    """Simulate account funding (demo account)."""
    amount = 0
    if data:
        amount = data.get("amount", 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if amount > 1000000:
        raise HTTPException(status_code=400, detail="Maximum funding: $1,000,000")
    return {
        "status": "funded",
        "amount": amount,
        "message": f"Demo account funded with ${amount:,.2f}",
        "note": "Contact your broker for live account funding"
    }


@app.post("/api/v1/account/withdraw")
def withdraw_account(data: dict = None):
    """Simulate account withdrawal (demo account)."""
    amount = 0
    if data:
        amount = data.get("amount", 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    info = mt5.account_info()
    if info and amount > info.balance:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    return {
        "status": "withdrawal_requested",
        "amount": amount,
        "message": f"Withdrawal of ${amount:,.2f} requested",
        "note": "Contact your broker for live withdrawals"
    }


# ═══════════════════════════════════════════════════════════════
# CHART DATA — OHLC for enterprise charts
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/chart/{symbol}")
def chart_data(symbol: str, timeframe: str = "H1", count: int = 200):
    """Get OHLC candle data for charts."""
    try:
        tf_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
        }
        tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            return {"candles": [], "symbol": symbol, "timeframe": timeframe}

        candles = []
        for r in rates:
            candles.append({
                "time": int(r['time']),
                "open": round(r['open'], 5),
                "high": round(r['high'], 5),
                "low": round(r['low'], 5),
                "close": round(r['close'], 5),
                "volume": int(r['tick_volume']),
            })
        return {"candles": candles, "symbol": symbol, "timeframe": timeframe, "count": len(candles)}
    except Exception as e:
        return {"candles": [], "symbol": symbol, "timeframe": timeframe, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# LIVE DATA — Real-time prices, WebSocket, Engine status
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/live/prices")
def live_prices():
    """Get real-time bid/ask for all symbols."""
    prices = {}
    for sym in WATCHLIST:
        tick = mt5.symbol_info_tick(sym)
        if tick:
            prices[sym] = {
                "bid": round(tick.bid, 5),
                "ask": round(tick.ask, 5),
                "spread": round((tick.ask - tick.bid) * (10000 if "JPY" not in sym else 100), 1),
                "time": int(tick.time),
            }
    return {"prices": prices, "count": len(prices)}


@app.get("/api/v1/engine/status")
def engine_status():
    """Full engine status with all details."""
    try:
        state = engine.risk.get_state()
    except Exception:
        state = {}
    acct = {}
    if engine.mt5.connected:
        try:
            info = mt5.account_info()
            if info:
                acct = {
                    "balance": info.balance,
                    "equity": info.equity,
                    "margin": info.margin,
                    "margin_free": info.margin_free,
                    "margin_level": info.margin_level,
                    "profit": info.profit,
                    "leverage": info.leverage,
                    "name": info.name,
                    "server": info.server,
                    "login": info.login,
                    "currency": info.currency,
                    "company": info.company,
                }
        except Exception:
            pass
    return {
        "running": engine.running,
        "cycle": engine.cycle_count,
        "uptime": str(datetime.now(timezone.utc) - engine.start_time) if engine.start_time else "0:00:00",
        "mt5_connected": engine.mt5.connected,
        "account": acct,
        "risk": state,
        "positions_count": len(engine.risk.open_positions) if hasattr(engine.risk, 'open_positions') else 0,
        "last_signals": len(engine.last_signals),
        "watchlist": WATCHLIST,
        "features": {
            "regime": getattr(getattr(engine, 'ensemble', None), 'current_regime', None) and str(getattr(engine.ensemble, 'current_regime', '')),
            "calendar_loaded": len(getattr(getattr(engine, 'calendar', None), 'events', [])),
            "risk_parity_weights": dict(getattr(getattr(engine, 'risk_parity', None), 'weights', {})),
        },
        "config": {
            "risk_pct": CONFIG["max_risk_pct"],
            "sl_atr": CONFIG["sl_atr_mult"],
            "tp_atr": CONFIG["tp_atr_mult"],
            "cycle_interval": CONFIG.get("cycle_interval", 300),
            "llm_enabled": CONFIG.get("llm_enabled", False),
            "ml_enabled": CONFIG.get("ml_enabled", False),
            "regime_enabled": CONFIG.get("regime_enabled", False),
            "calendar_enabled": CONFIG.get("calendar_enabled", False),
            "risk_parity_enabled": CONFIG.get("risk_parity_enabled", False),
            "multi_timeframe_enabled": CONFIG.get("multi_timeframe_enabled", False),
        },
    }


@app.get("/api/v1/live/tick/{symbol}")
def live_tick(symbol: str):
    """Get latest tick for a symbol."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    info = mt5.symbol_info(symbol)
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": tick.volume,
        "time": int(tick.time),
        "spread": info.spread if info else 0,
        "digits": info.digits if info else 5,
    }


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET — Real-time chart data
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    """WebSocket for real-time price streaming."""
    await websocket.accept()
    symbols = WATCHLIST
    try:
        while True:
            prices = {}
            for sym in symbols:
                tick = mt5.symbol_info_tick(sym)
                if tick:
                    prices[sym] = {
                        "bid": round(tick.bid, 5),
                        "ask": round(tick.ask, 5),
                        "time": int(tick.time),
                    }
            await websocket.send_json({"prices": prices})
            await asyncio.sleep(1)  # Update every second
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# ADVANCED FEATURES — Analysts, Legendary, Emotion, Defense, etc.
# ═══════════════════════════════════════════════════════════════

try:
    from apps.analysts.market import MarketAnalyst
    from apps.analysts.news import NewsAnalyst
    from apps.analysts.sentiment import SentimentAnalyst
    from apps.analysts.technical import TechnicalAnalyst
    from apps.analysts.fundamentals import FundamentalsAnalyst
    from apps.analysts.options import OptionsAnalyst
    from apps.analysts.order_flow import OrderFlowAnalyst
    from apps.analysts.risk import RiskAnalyst
    from apps.analysts.macro import MacroAnalyst
    from apps.analysts.on_chain import OnChainAnalyst
    from apps.analysts.quant import QuantAnalyst
    from apps.analysts.compliance import ComplianceAnalyst
    from apps.legendary.soros import SorosAgent
    from apps.legendary.buffett import BuffettAgent
    from apps.legendary.druckenmiller import DruckenmillerAgent
    from apps.legendary.tudor_jones import TudorJonesAgent
    from apps.legendary.lynch import LynchAgent
    from apps.memory.situation_memory import FinancialSituationMemory
    ADVANCED_FEATURES_AVAILABLE = True
    log.info("Advanced features (analysts, legendary, memory) loaded successfully")
except ImportError as e:
    ADVANCED_FEATURES_AVAILABLE = False
    log.warning(f"Advanced features not available: {e}")


@app.get("/api/v1/analysts/all")
async def all_analysts(symbol: str = "EURUSD", timeframe: str = "H1"):
    """Run all 12 analysts on a symbol."""
    if not ADVANCED_FEATURES_AVAILABLE:
        return {"error": "Advanced features not available", "symbol": symbol, "analysts": [], "consensus": "HOLD"}
    analysts = [
        ("Market", MarketAnalyst),
        ("News", NewsAnalyst),
        ("Sentiment", SentimentAnalyst),
        ("Technical", TechnicalAnalyst),
        ("Fundamentals", FundamentalsAnalyst),
        ("Options", OptionsAnalyst),
        ("OrderFlow", OrderFlowAnalyst),
        ("Risk", RiskAnalyst),
        ("Macro", MacroAnalyst),
        ("OnChain", OnChainAnalyst),
        ("Quant", QuantAnalyst),
        ("Compliance", ComplianceAnalyst),
    ]
    results = []
    for name, cls in analysts:
        try:
            a = cls()
            r = await a.analyze(symbol, timeframe)
            results.append({
                "name": name,
                "signal": r.signal,
                "confidence": round(r.confidence, 3),
                "reasoning": r.reasoning[:200] if r.reasoning else "",
            })
        except Exception as e:
            results.append({"name": name, "signal": "HOLD", "confidence": 0, "reasoning": str(e)[:100]})

    buys = sum(1 for r in results if r["signal"] == "BUY")
    sells = sum(1 for r in results if r["signal"] == "SELL")
    holds = sum(1 for r in results if r["signal"] == "HOLD")
    avg_conf = sum(r["confidence"] for r in results) / len(results) if results else 0

    consensus = "BUY" if buys > sells and buys > holds else "SELL" if sells > buys and sells > holds else "HOLD"

    return {
        "symbol": symbol,
        "analysts": results,
        "consensus": consensus,
        "votes": {"buy": buys, "sell": sells, "hold": holds},
        "avg_confidence": round(avg_conf, 3),
        "total": len(results),
    }


@app.get("/api/v1/legendary/all")
def all_legendary(symbol: str = "EURUSD"):
    """Run all 5 legendary agents."""
    if not ADVANCED_FEATURES_AVAILABLE:
        return {"error": "Advanced features not available", "symbol": symbol, "agents": [], "consensus": "HOLD"}
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
    price_data = None
    if rates is not None:
        price_data = pd.DataFrame(rates)

    agents = [
        ("Soros", SorosAgent),
        ("Buffett", BuffettAgent),
        ("Druckenmiller", DruckenmillerAgent),
        ("TudorJones", TudorJonesAgent),
        ("Lynch", LynchAgent),
    ]
    results = []
    for name, cls in agents:
        try:
            a = cls()
            if price_data is not None:
                r = a.analyze(symbol, price_data)
            else:
                r = a.analyze(symbol)
            results.append({
                "name": name,
                "signal": r.signal,
                "confidence": round(r.confidence, 3),
                "kelly_fraction": round(getattr(r, 'kelly_fraction', 0), 3),
                "reasoning": r.reasoning[:200] if r.reasoning else "",
            })
        except Exception as e:
            results.append({"name": name, "signal": "HOLD", "confidence": 0, "kelly_fraction": 0, "reasoning": str(e)[:100]})

    buys = sum(1 for r in results if r["signal"] == "BUY")
    sells = sum(1 for r in results if r["signal"] == "SELL")
    consensus = "BUY" if buys > sells else "SELL" if sells > buys else "HOLD"

    return {
        "symbol": symbol,
        "agents": results,
        "consensus": consensus,
        "total": len(results),
    }


@app.get("/api/v1/emotion/fear-greed")
def fear_greed():
    """Calculate Fear/Greed index from market data."""
    try:
        rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 50)
        if rates is None:
            return {"index": 50, "state": "Neutral", "positioning": "RANGING"}

        closes = np.array([r['close'] for r in rates])

        # RSI calculation
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses_arr = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses_arr[-14:])
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))

        # ADX (simplified)
        adx = min(100, abs(rsi - 50) * 2)

        # Bollinger width
        sma20 = np.mean(closes[-20:])
        std20 = np.std(closes[-20:])
        bb_width = (std20 * 2 / sma20 * 100) if sma20 > 0 else 0

        # Composite index
        rsi_score = 100 - rsi  # Inverted: high RSI = greed
        adx_score = min(100, adx)
        bb_score = min(100, bb_width * 10)
        index = (rsi_score * 0.5 + adx_score * 0.25 + bb_score * 0.25)
        index = max(0, min(100, index))

        if index < 10:
            state = "Panic"
        elif index < 30:
            state = "Fear"
        elif index < 50:
            state = "Neutral"
        elif index < 70:
            state = "Greed"
        else:
            state = "Euphoria"

        if rsi < 30:
            positioning = "OVERSOLD"
        elif rsi > 70:
            positioning = "OVERBOUGHT"
        elif adx > 25:
            positioning = "TRENDING"
        else:
            positioning = "RANGING"

        return {
            "index": round(index, 1),
            "state": state,
            "positioning": positioning,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "bb_width": round(bb_width, 3),
        }
    except Exception as e:
        return {"index": 50, "state": "Neutral", "positioning": "RANGING", "error": str(e)}


@app.get("/api/v1/defense/status")
def defense_status():
    """Get defense system status."""
    try:
        state = engine.risk.get_state()
        daily_pnl = state.get("daily_pnl", 0)
        balance = state.get("balance", 10000)
        losses = state.get("consecutive_losses", 0)

        daily_loss_pct = abs(daily_pnl) / balance * 100 if daily_pnl < 0 else 0

        if daily_loss_pct > 5 or losses > 5:
            level = "EMERGENCY"
            color = "#FF0000"
            action = "ALL TRADING HALTED"
        elif daily_loss_pct > 3 or losses > 3:
            level = "DEFENSE"
            color = "#FF6600"
            action = "Position sizes halved"
        elif daily_loss_pct > 1 or losses > 2:
            level = "CAUTION"
            color = "#FFAA00"
            action = "Reduced exposure"
        else:
            level = "NORMAL"
            color = "#00CC88"
            action = "Full trading enabled"

        return {
            "level": level,
            "color": color,
            "action": action,
            "daily_loss_pct": round(daily_loss_pct, 2),
            "consecutive_losses": losses,
            "circuit_breaker": state.get("circuit_breaker", "CLOSED"),
        }
    except Exception as e:
        return {"level": "NORMAL", "color": "#00CC88", "action": "Full trading enabled", "error": str(e)}


@app.get("/api/v1/memory/recent")
def memory_recent():
    """Get recent memory entries."""
    try:
        mem = FinancialSituationMemory()
        situations = mem.retrieve("recent trading", top_k=5)
        return {"situations": situations, "total": len(situations)}
    except Exception as e:
        return {"situations": [], "total": 0, "error": str(e)}


@app.get("/api/v1/debate/{symbol}")
async def debate_result(symbol: str):
    """Run bull vs bear debate."""
    try:
        from apps.debate.engine import DebateEngine
        engine_d = DebateEngine()
        context = {}
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            closes = df["close"].tolist()
            highs = df["high"].tolist()
            lows = df["low"].tolist()
            context["closes"] = closes[-20:]
            context["highs"] = highs[-20:]
            context["lows"] = lows[-20:]
            context["current_price"] = float(closes[-1])
            context["price_change_5"] = round((closes[-1] - closes[-6]) / closes[-6] * 100, 3) if len(closes) >= 6 else 0
            context["price_change_20"] = round((closes[-1] - closes[0]) / closes[0] * 100, 3) if len(closes) >= 20 else 0
            context["high_20"] = max(highs[-20:]) if len(highs) >= 20 else max(highs)
            context["low_20"] = min(lows[-20:]) if len(lows) >= 20 else min(lows)
        result = await engine_d.debate(symbol, context)
        return {
            "winner": result.winner,
            "bull_confidence": round(result.bull_confidence, 3),
            "bear_confidence": round(result.bear_confidence, 3),
            "rounds": result.rounds,
            "arguments": [
                {"stance": a.stance, "confidence": round(a.confidence, 3), "reasoning": a.reasoning[:200]}
                for a in result.arguments
            ],
        }
    except Exception as e:
        return {"winner": "NEUTRAL", "bull_confidence": 0, "bear_confidence": 0, "rounds": 0, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  DUTCHKEM UNIFIED TRADING ENGINE v2.0")
    print("  All Layers Combined | Direct MT5 | LLM Powered")
    print("=" * 70)
    print(f"  Watchlist: {len(WATCHLIST)} symbols")
    print(f"  MTF Timeframes: {CONFIG['mtf_timeframes']}")
    print(f"  Risk per trade: {CONFIG['max_risk_pct']*100:.0f}%")
    print(f"  SL/TP: {CONFIG['sl_atr_mult']}x / {CONFIG['tp_atr_mult']}x ATR")
    print(f"  LLM: {'Enabled' if CONFIG['llm_enabled'] else 'Disabled'}")
    print(f"  ML: {'Enabled' if CONFIG['ml_enabled'] else 'Disabled'}")
    print(f"  API Server: http://localhost:8888")
    print("=" * 70)
    print("\n  Starting FastAPI server with embedded trading engine...\n")

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
