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
from dotenv import load_dotenv
load_dotenv()
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# Models directory for ML model persistence
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

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
MT5_PATH = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")
MT5_MAGIC = int(os.environ.get("MT5_MAGIC", "234000"))
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
    "max_risk_pct": 0.10,              # 10% risk per trade (reduced from 25% for safety)
    "max_position_pct": 0.15,
    "kelly_win_rate": 0.55,
    "kelly_avg_win": 1.5,
    "kelly_avg_loss": 1.0,
    "hold_bars": 72,
    "min_confidence": 0.25,
    "min_score": 2,

    # ── Daily ROI Limits ──
    "daily_profit_target_pct": 0.02,   # Stop trading after +2% daily gain
    "daily_loss_limit_pct": 0.015,     # Stop trading after -1.5% daily loss
    "daily_risk_per_trade_pct": 0.005, # 0.5% risk per trade (conservative)
    "daily_reset_hour_utc": 0,         # Reset counters at midnight UTC
    "daily_extraction_enabled": True,  # Enable weekly profit extraction
    "extraction_day": "friday",        # Extract profits on Friday
    "extraction_pct": 0.30,           # Extract 30% of weekly profits

    # ── ML Live Learning ──
    "ml_live_learning_enabled": True,  # Enable live learning from real trades
    "ml_retrain_interval": 20,        # Retrain every 20 trades
    "ml_min_diversity": 5,            # Min 5 wins AND 5 losses before retraining
    "ml_max_training_data": 200,      # Keep last 200 trades for training

    # ── Dual Kelly Profiles (LLM picks per-trade) ──
    "kelly_profiles": {
        "aggressive": {
            "avg_win": 2.0,
            "avg_loss": 0.5,
            "description": "High R:R (4:1). Use in strong trends with clear momentum.",
            "conditions": "ADX>30, high volume, trending Ichimoku, London/NY session",
        },
        "neutral": {
            "avg_win": 1.75,
            "avg_loss": 0.75,
            "description": "Medium R:R (2.3:1). Use in moderate trends with some confirmation.",
            "conditions": "ADX 20-30, moderate volume, partial Ichimoku alignment",
        },
        "conservative": {
            "avg_win": 1.5075,
            "avg_loss": 0.995,
            "description": "Balanced R:R (1.5:1). Use in ranging or uncertain markets.",
            "conditions": "ADX<25, low volume, mixed signals, off-peak session",
        },
    },
    "strategy_selector_enabled": True,

    # ── Symbol-Specific Default Profiles ──
    "symbol_default_profiles": {
        # Stable pairs → aggressive default
        "EURUSD": "aggressive",
        "GBPUSD": "aggressive",
        "USDCHF": "aggressive",
        "AUDUSD": "aggressive",
        "NZDUSD": "aggressive",
        "USDCAD": "aggressive",
        "EURGBP": "aggressive",
        # Volatile pairs → conservative default
        "USDJPY": "conservative",
        "EURJPY": "conservative",
        "GBPJPY": "conservative",
        "AUDJPY": "conservative",
        "XAUUSD": "conservative",
    },

    # ── Session Strategy Bias ──
    "session_strategy_bias": {
        # Hour (UTC): "aggressive" or "conservative"
        # London/NY overlap: aggressive (high liquidity, big moves)
        13: "aggressive", 14: "aggressive", 15: "aggressive", 16: "aggressive",
        # London open: slightly aggressive
        7: "neutral", 8: "neutral", 9: "neutral", 10: "neutral",
        11: "neutral", 12: "neutral",
        # NY afternoon: neutral
        17: "neutral", 18: "neutral",
        # Off-peak: conservative
        19: "conservative", 20: "conservative", 21: "conservative",
        # Asian session: conservative (low liquidity)
        0: "conservative", 1: "conservative", 2: "conservative", 3: "conservative",
        4: "conservative", 5: "conservative", 6: "conservative",
        22: "conservative", 23: "conservative",
    },

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
    "sl_atr_mult": 1.5,              # V3: default SL (per-symbol overrides below)
    "tp_atr_mult": 4.0,              # V3: default TP (per-symbol overrides below)
    "vol_sizing": True,

    # ── V3 Per-Symbol SL/TP/Trail/Risk Configs (optimized backtest) ──
    "v3_symbol_configs": {
        "EURUSD": {"sl": 1.5, "tp": 4.0, "trail": 1.0, "risk": 0.03, "cooldown": 3},
        "GBPUSD": {"sl": 1.5, "tp": 4.0, "trail": 2.0, "risk": 0.03, "cooldown": 5},
        "USDJPY": {"sl": 2.0, "tp": 3.0, "trail": 1.0, "risk": 0.03, "cooldown": 3},
        "XAUUSD": {"sl": 1.5, "tp": 3.0, "trail": 2.0, "risk": 0.02, "cooldown": 5},
        "USDCHF": {"sl": 2.0, "tp": 3.0, "trail": 2.0, "risk": 0.02, "cooldown": 3},
        "AUDUSD": {"sl": 1.5, "tp": 4.0, "trail": 2.0, "risk": 0.03, "cooldown": 3},
        "USDCAD": {"sl": 2.0, "tp": 4.0, "trail": 1.0, "risk": 0.03, "cooldown": 5},
        "NZDUSD": {"sl": 2.5, "tp": 4.0, "trail": 1.0, "risk": 0.03, "cooldown": 3},
        "EURGBP": {"sl": 2.0, "tp": 3.0, "trail": 1.0, "risk": 0.03, "cooldown": 3},
        "EURJPY": {"sl": 1.5, "tp": 4.0, "trail": 2.0, "risk": 0.03, "cooldown": 3},
    },

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

    # ── DDFX Bollinger Band Stop ──
    "bbstop_enabled": True,

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

    # ── ANALYST CONSENSUS (Phase 1) ──
    "analyst_consensus_enabled": True,
    "analyst_min_agreement": 0.50,       # Min % of analysts that must agree to boost
    "analyst_block_threshold": 0.50,     # If >50% disagree → block trade
    "analyst_confidence_boost": 0.20,    # Boost confidence by 20% on strong agreement
    "analyst_confidence_penalty": 0.15,  # Reduce confidence by 15% on weak agreement

    # ── LEGENDARY CONSENSUS (Phase 2) ──
    "legendary_consensus_enabled": True,

    # ── MTF Analysis ──
    "multi_timeframe_enabled": True,
    "mtf_timeframes": ["M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
    "mtf_min_agree": 2,
    "mtf_weights": {
        "M15": 0.05, "M30": 0.08, "H1": 0.12,
        "H4": 0.25, "D1": 0.30, "W1": 0.15, "MN1": 0.05,
    },

    # ── MTF Cascading Scalper ──
    "mtf_cascading_scalper_enabled": True,
    "scalper_timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
    "scalper_groups": [
        {"name": "G1", "timeframes": ["M1", "M5", "M15"]},
        {"name": "G2", "timeframes": ["M5", "M15", "M30"]},
        {"name": "G3", "timeframes": ["M15", "M30", "H1"]},
        {"name": "G4", "timeframes": ["M30", "H1", "H4"]},
        {"name": "G5", "timeframes": ["H1", "H4", "D1"]},
        {"name": "G6", "timeframes": ["H4", "D1", "W1"]},
        {"name": "G7", "timeframes": ["D1", "W1", "MN1"]},
    ],
    "scalper_tp_pips": 10,
    "scalper_sl_pips": 5,
    "scalper_lot_size": 0.01,
    "scalper_max_concurrent": 5,
    "scalper_scan_interval": 60,
    "scalper_restart_from_group1": True,
    "scalper_symbol": "EURUSD",  # Fallback if multi-symbol disabled
    "scalper_multi_symbol": True,  # Scan all WATCHLIST symbols
    "scalper_trailing_enabled": True,
    "scalper_trailing_breakeven_rr": 1.0,  # Move SL to entry at 1:1 R:R
    "scalper_trailing_step_pips": 5,  # Trail by 5 pips
    "scalper_prefer_groups": ["G3", "G4", "G5"],  # Prefer M15-H1-H4 range
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

    # ── PPO (Percentage Price Oscillator) ──
    # PPO = (EMA12 - EMA26) / EMA26 * 100 — percentage-normalized MACD
    ema_12 = pd.Series(c).ewm(span=12).mean()
    ema_26 = pd.Series(c).ewm(span=26).mean()
    df["ppo"] = ((ema_12 - ema_26) / ema_26 * 100).values
    df["ppo_signal"] = pd.Series(df["ppo"]).ewm(span=9).mean().values
    df["ppo_hist"] = (df["ppo"] - df["ppo_signal"])

    # ── DDFX Bollinger Band Stop (3-band system) ──
    # BB1 = 1.0 std (tight stop), BB2 = 1.5 std (medium), BB3 = 2.0 std (wide stop)
    bb_sma = pd.Series(c).rolling(20).mean()
    bb_std_20 = pd.Series(c).rolling(20).std()
    df["bbstop_upper"] = (bb_sma + 1.5 * bb_std_20).values   # Stop level for BUY (close above = exit)
    df["bbstop_lower"] = (bb_sma - 1.5 * bb_std_20).values   # Stop level for SELL (close below = exit)
    df["bbstop_mid"] = bb_sma.values

    # Volume Ratio (MT5 uses 'tick_volume', not 'volume')
    vol_col = "tick_volume" if "tick_volume" in df.columns else "volume" if "volume" in df.columns else None
    if vol_col and df[vol_col].sum() > 0:
        df["vol_sma_20"] = pd.Series(df[vol_col].values).rolling(20).mean().values
        df["vol_ratio"] = df[vol_col] / df["vol_sma_20"].replace(0, 1)
    else:
        df["vol_ratio"] = 1.0

    return df


# ── Daily Pivot Points (computed from previous day's OHLC via MT5) ──
def compute_daily_pivots(symbol: str) -> dict:
    """Compute pivot points from previous day's OHLC. Returns PP, R1-R3, S1-S3."""
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 1)
        if rates is None or len(rates) == 0:
            return {}
        prev = rates[0]
        high, low, close = prev["high"], prev["low"], prev["close"]

        pp = (high + low + close) / 3
        r1 = 2 * pp - low
        s1 = 2 * pp - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        r3 = high + 2 * (pp - low)
        s3 = low - 2 * (high - pp)

        return {
            "pivot": round(pp, 5),
            "r1": round(r1, 5), "r2": round(r2, 5), "r3": round(r3, 5),
            "s1": round(s1, 5), "s2": round(s2, 5), "s3": round(s3, 5),
            "prev_high": round(high, 5), "prev_low": round(low, 5),
        }
    except Exception:
        return {}


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

    # ── PPO (Percentage Price Oscillator) ──
    # PPO histogram positive = bullish momentum (percentage-normalized)
    ppo_hist = row.get("ppo_hist", 0)
    if ppo_hist > 0.05:
        score += 1
        details["ppo"] = f"bullish({ppo_hist:.3f})"
    elif ppo_hist < -0.05:
        score -= 1
        details["ppo"] = f"bearish({ppo_hist:.3f})"
    else:
        details["ppo"] = f"neutral({ppo_hist:.3f})"

    # ── Daily Pivot Points ──
    # Price relative to pivot determines intraday bias
    # Cached per-symbol in pivot_cache to avoid recomputing every bar
    close = row["close"]
    _pivot_cache = getattr(generate_signal, '_pivot_cache', {})
    _pivot_cache_time = getattr(generate_signal, '_pivot_cache_time', {})
    now_ts = pd.Timestamp.now().timestamp()
    cache_key = getattr(row, '_symbol', 'unknown') if hasattr(row, '_symbol') else 'unknown'
    pivots = _pivot_cache.get(cache_key)
    cache_age = now_ts - _pivot_cache_time.get(cache_key, 0) if cache_key in _pivot_cache_time else 99999

    if cache_age > 3600 or pivots is None:  # Recompute every hour
        pivots = compute_daily_pivots(cache_key if cache_key != 'unknown' else 'EURUSD')
        _pivot_cache[cache_key] = pivots
        _pivot_cache_time[cache_key] = now_ts
        generate_signal._pivot_cache = _pivot_cache
        generate_signal._pivot_cache_time = _pivot_cache_time

    if pivots:
        pp = pivots.get("pivot", close)
        r1 = pivots.get("r1", close * 1.005)
        s1 = pivots.get("s1", close * 0.995)
        if close < s1:
            score += 1  # Below S1 = oversold, bounce potential
            details["pivots"] = f"below_S1({s1:.5f})"
        elif close > r1:
            score -= 1  # Above R1 = overbought, pullback potential
            details["pivots"] = f"above_R1({r1:.5f})"
        else:
            details["pivots"] = f"between_S1_R1(PP={pp:.5f})"

    max_score = 10
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
# STRATEGY SELECTION PROMPT — LLM picks aggressive vs conservative
# ═══════════════════════════════════════════════════════════════

STRATEGY_SELECTION_PROMPT = """You are a senior trading strategist with 20+ years of experience. You must decide which risk profile to use for the next trade.

═══ THREE PROFILES ═══
A) AGGRESSIVE (avg_win=2.0, avg_loss=0.5 → R:R = 4:1)
   - Larger position sizing, higher reward per risk unit
   - BEST WHEN: Strong directional trend, high conviction, volume confirms
   - RISK: bigger losses when wrong

B) NEUTRAL (avg_win=1.75, avg_loss=0.75 → R:R ≈ 2.3:1)
   - Balanced-aggressive sizing, moderate reward per risk unit
   - BEST WHEN: Moderate trend with some confirmation, partial volume support
   - BALANCED: neither too aggressive nor too cautious

C) CONSERVATIVE (avg_win=1.5075, avg_loss=0.995 → R:R ≈ 1.5:1)
   - Balanced position sizing, standard reward per risk unit
   - BEST WHEN: Ranging market, mixed signals, low volume, uncertain
   - SAFER: smaller losses when wrong

═══ MARKET DATA ═══
Symbol: {symbol} | Direction: {action}
Current Price: {close}
ADX: {adx} | RSI: {rsi}
Volume Ratio: {vol_ratio}x average
ATR%: {atr_pct}%
Ichimoku: Tenkan={tenkan}, Kijun={kijun}, SenkouA={senkou_a}, SenkouB={senkou_b}
Session Hour (UTC): {session_hour}
Signal Confidence: {confidence}
Balance: ${current_balance}
Open Positions: {open_positions}
Recent Performance: {recent_wins}W / {recent_losses}L (last 10 trades)

═══ YOUR REASONING ═══
Analyze the market conditions critically:
1. Is there a clear directional trend (ADX, Ichimoku cloud, moving averages)?
2. Is volume confirming the move?
3. Is the session active (London/NY overlap)?
4. What is the risk/reward context?
5. How has recent performance been?

Think like a human trader — not just numbers, but market context.

Respond with ONLY this JSON:
{{
    "profile": "aggressive" or "neutral" or "conservative",
    "confidence": 0.0 to 1.0 (how confident in your choice),
    "reasoning": "1-2 sentences explaining your decision"
}}"""


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
    if not CONFIG.get("ml_live_learning_enabled", True):
        return 0.5

    try:
        from apps.ml.predictor import MLPredictor
        # Cache predictor instance to avoid re-loading model every call
        if not hasattr(ml_rank, '_predictor'):
            ml_rank._predictor = MLPredictor(model_type="xgboost")
        ml = ml_rank._predictor

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
            indicators.get("volatility_regime", 1.0 if indicators.get("adx", 0) > 25 else 0.0),
            indicators.get("adx", 0),  # trend_strength
            indicators.get("support_distance", 0.0),  # real S/R distance
            indicators.get("resistance_distance", 0.0),  # real S/R distance
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
    """SINGLE SOURCE OF TRUTH for risk management.
    
    Combined risk management: Kelly + Circuit Breaker + Drawdown + Correlation + Daily Limits.
    
    This is the ONLY RiskManager used by the live trading engine.
    The deprecated version in execution/risk_manager.py is NOT used.
    """

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
        self.last_trade_time = {}  # V3: symbol -> last trade timestamp (for cooldown)

        # ── Daily ROI Tracking ──
        self.daily_start_balance = 10000.0  # Balance at start of day
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_pnl_dollar = 0.0
        self.daily_date = datetime.now(timezone.utc).date()
        self.daily_target_hit = False
        self.daily_limit_hit = False

        # ── Weekly Extraction Tracking ──
        self.weekly_pnl = 0.0
        self.weekly_start_balance = 10000.0
        self.last_extraction_date = None

    def update_balance(self, new_balance: float):
        self.balance = new_balance
        self.peak_balance = max(self.peak_balance, new_balance)

    def update_equity(self, equity: float):
        """Track equity for position sizing."""
        self.equity = equity
        self.peak_balance = max(self.peak_balance, equity)

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

        # Record trade in trade_log (BUG FIX: was never populated)
        self.trade_log.append({
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "time": datetime.now(timezone.utc).isoformat(),
        })

        # ── Daily Tracking ──
        self.daily_trades += 1
        self.daily_pnl_dollar += pnl
        if pnl > 0:
            self.daily_wins += 1
        self.weekly_pnl += pnl

        # Check daily limits
        self._check_daily_limits()

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

    def _check_daily_limits(self):
        """Check if daily profit target or loss limit is hit."""
        if self.daily_start_balance <= 0:
            return

        daily_return = self.daily_pnl_dollar / self.daily_start_balance

        # Profit target hit
        if daily_return >= CONFIG["daily_profit_target_pct"]:
            if not self.daily_target_hit:
                self.daily_target_hit = True
                log.warning(f"  DAILY PROFIT TARGET HIT: {daily_return:.2%} >= {CONFIG['daily_profit_target_pct']:.2%}")

        # Loss limit hit
        if daily_return <= -CONFIG["daily_loss_limit_pct"]:
            if not self.daily_limit_hit:
                self.daily_limit_hit = True
                log.warning(f"  DAILY LOSS LIMIT HIT: {daily_return:.2%} <= -{CONFIG['daily_loss_limit_pct']:.2%}")

    def reset_daily_counters(self):
        """Reset daily counters at midnight UTC."""
        now = datetime.now(timezone.utc).date()
        if now != self.daily_date:
            log.info(f"  DAILY RESET: {self.daily_date} → {now} | "
                     f"P&L=${self.daily_pnl_dollar:+.2f} | "
                     f"Trades={self.daily_trades} | WR={self.daily_wins}/{self.daily_trades}")
            self.daily_start_balance = self.balance
            self.daily_trades = 0
            self.daily_wins = 0
            self.daily_pnl_dollar = 0.0
            self.daily_date = now
            self.daily_target_hit = False
            self.daily_limit_hit = False

    def can_trade_today(self) -> bool:
        """Check if trading is allowed today (daily limits not hit)."""
        self.reset_daily_counters()  # Auto-reset at midnight

        if self.daily_target_hit:
            return False  # Already hit profit target
        if self.daily_limit_hit:
            return False  # Already hit loss limit
        return True

    def get_daily_status(self) -> Dict:
        """Get daily trading status."""
        self.reset_daily_counters()  # Auto-reset at midnight
        daily_return = self.daily_pnl_dollar / self.daily_start_balance if self.daily_start_balance > 0 else 0
        return {
            "date": str(self.daily_date),
            "start_balance": round(self.daily_start_balance, 2),
            "current_balance": round(self.balance, 2),
            "daily_pnl": round(self.daily_pnl_dollar, 2),
            "daily_return": round(daily_return, 4),
            "daily_trades": self.daily_trades,
            "daily_wins": self.daily_wins,
            "daily_win_rate": round(self.daily_wins / self.daily_trades, 2) if self.daily_trades > 0 else 0,
            "profit_target": CONFIG["daily_profit_target_pct"],
            "loss_limit": CONFIG["daily_loss_limit_pct"],
            "target_hit": self.daily_target_hit,
            "limit_hit": self.daily_limit_hit,
            "can_trade": not self.daily_target_hit and not self.daily_limit_hit,
        }

    def check_weekly_extraction(self) -> Dict:
        """Check if it's time for weekly profit extraction."""
        if not CONFIG.get("daily_extraction_enabled"):
            return {"extract": False, "reason": "extraction disabled"}

        now = datetime.now(timezone.utc)
        extraction_day = CONFIG.get("extraction_day", "friday").lower()

        # Check if it's the extraction day
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                   "friday": 4, "saturday": 5, "sunday": 6}
        target_day = day_map.get(extraction_day, 4)

        if now.weekday() != target_day:
            return {"extract": False, "reason": f"not {extraction_day} (today={now.strftime('%A')})"}

        # Check if already extracted today
        if self.last_extraction_date == now.date():
            return {"extract": False, "reason": "already extracted today"}

        # Calculate extraction amount
        extraction_pct = CONFIG.get("extraction_pct", 0.30)
        extraction_amount = self.weekly_pnl * extraction_pct

        if extraction_amount <= 0:
            return {"extract": False, "reason": f"no profits to extract (weekly P&L=${self.weekly_pnl:+.2f})"}

        return {
            "extract": True,
            "amount": round(extraction_amount, 2),
            "weekly_pnl": round(self.weekly_pnl, 2),
            "extraction_pct": extraction_pct,
            "reason": f"{extraction_day} extraction: ${extraction_amount:.2f} ({extraction_pct:.0%} of ${self.weekly_pnl:.2f})",
        }

    def record_extraction(self, amount: float):
        """Record that a profit extraction was made."""
        self.last_extraction_date = datetime.now(timezone.utc).date()
        self.weekly_pnl -= amount
        log.info(f"  PROFIT EXTRACTION: ${amount:.2f} | Remaining weekly P&L: ${self.weekly_pnl:+.2f}")

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

        # Base risk = EQUITY × risk percentage (always use equity, not balance)
        equity = getattr(self, 'equity', self.balance)
        # V3: Use per-symbol risk if available
        v3_configs = CONFIG.get("v3_symbol_configs", {})
        if symbol and symbol in v3_configs:
            risk_pct = v3_configs[symbol]["risk"]
        else:
            risk_pct = CONFIG.get("daily_risk_per_trade_pct", CONFIG["max_risk_pct"])
        base_risk = equity * risk_pct

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

        # Cap at max position (5% of equity)
        max_lots = (equity * CONFIG["max_position_pct"]) / (price * contract_size)
        lots = min(lots, max_lots)

        # Enforce minimum lot size (MT5 requires at least 0.01)
        if lots > 0 and lots < 0.01:
            lots = 0.01

        return round(lots, 2)

    def calculate_sl_tp(self, price: float, atr: float, action: str, symbol: str = None) -> Tuple[float, float]:
        """ATR-based SL/TP with V3 per-symbol configs."""
        # V3: Use per-symbol config if available
        v3_configs = CONFIG.get("v3_symbol_configs", {})
        if symbol and symbol in v3_configs:
            sc = v3_configs[symbol]
            sl_distance = atr * sc["sl"]
            tp_distance = atr * sc["tp"]
        else:
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

        # ── Monitoring: structured pipeline events (last 200) ──
        self.monitor_events = []  # list of {time, symbol, event, detail, cycle}
        self.monitor_max_events = 200

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

        # Initialize MTF Cascading Scalper
        if CONFIG.get("mtf_cascading_scalper_enabled"):
            from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
            self.scalper = MTFCascadingScalper(self.mt5, self.risk, CONFIG)
        else:
            self.scalper = None

        # ── ConsensusGates: ML + LLM gating as additional safety layer ──
        try:
            from apps.consensus.gates import ConsensusGates
            from apps.ml.predictor import MLPredictor
            self.consensus_gates = ConsensusGates(ml_predictor=MLPredictor(model_type="xgboost"))
            log.info("  ConsensusGates initialized (ML gate active)")
        except Exception as e:
            self.consensus_gates = None
            log.debug(f"  ConsensusGates not available: {e}")

        # ── Phase 4: Equity Curve MA + Kelly Criterion ──
        self.equity_curve = []  # Rolling equity history for MA
        self.equity_curve_ma_period = CONFIG.get("equity_curve_ma_period", 20)
        self.kelly_fraction = CONFIG.get("kelly_win_rate", 0.55)  # Start with config default
        self._trade_results = []  # Track wins/losses for dynamic Kelly

        # ── Strategy Profile Performance Tracker ──
        self._profile_performance = {
            "aggressive": {"trades": 0, "wins": 0, "total_pnl": 0.0},
            "neutral": {"trades": 0, "wins": 0, "total_pnl": 0.0},
            "conservative": {"trades": 0, "wins": 0, "total_pnl": 0.0},
        }

        # ── Phase 2: ML Live Learning ──
        self._ml_training_data = []  # Store (features, label) pairs for retraining
        self._ml_retrain_count = 0  # How many times we've retrained
        self._last_ml_retrain_cycle = 0  # Last cycle we retrained on

        # ── Phase 5: Profit Maximization ──
        self.win_streak = 0
        self.loss_streak = 0
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.last_trade_pnl = 0
        self.peak_balance = 0

    # ═══════════════════════════════════════════════════════════════
    # SCALPER-MAIN ENGINE INTEGRATION
    # ═══════════════════════════════════════════════════════════════

    def _sync_scalp_results(self):
        """Feed scalper trade results into main engine's learning systems.
        
        This ensures:
        - Scalp wins/losses feed into Kelly calculation
        - Scalp trades update win/loss streaks
        - Scalp trades count toward daily limits
        - Unified performance tracking across both systems
        """
        if not self.scalper:
            return

        # Check for newly closed scalps (in trade_history but not yet synced)
        for scalp in self.scalper.trade_history:
            if scalp.get("_synced"):
                continue  # Already processed

            ticket = scalp.get("ticket")
            symbol = scalp.get("symbol")
            entry_price = scalp.get("entry_price", 0)
            size = scalp.get("size", 0)
            status = scalp.get("status", "OPEN")

            if status != "CLOSED":
                continue

            # Get actual P&L from MT5 deal history
            pnl = 0
            try:
                deals = mt5.history_deals_get(ticket=ticket)
                if deals:
                    pnl = sum(d.profit for d in deals)
            except Exception:
                # Fallback: estimate from price movement
                pass

            # Record in main engine's learning systems
            if pnl != 0:
                # 1. Feed into Kelly trade results
                self._trade_results.append(pnl)
                if len(self._trade_results) > 50:
                    self._trade_results = self._trade_results[-50:]

                # 2. Update risk manager
                self.risk.record_trade_result(pnl, pnl / self.risk.balance if self.risk.balance > 0 else 0)

                # 3. Update streaks
                self._update_streaks(pnl)

                # 4. Log the integration
                direction = scalp.get("direction", "?")
                group = scalp.get("group", "?")
                log.info(f"  SCALP SYNCED: {direction} {symbol} ({group}) | P&L=${pnl:+.2f} | "
                         f"Kelly={len(self._trade_results)} trades | Streak=W{self.consecutive_wins}/L{self.consecutive_losses}")

            # Store profit in scalp dict for scalper's streak-based sizing
            scalp["profit"] = pnl

            # Mark as synced
            scalp["_synced"] = True

            # Remove from risk manager open_positions
            if symbol in self.risk.open_positions and self.risk.open_positions[symbol].get("source") == "scalper":
                del self.risk.open_positions[symbol]

        # Cap trade_history to prevent memory leak (keep last 200)
        if len(self.scalper.trade_history) > 200:
            self.scalper.trade_history = self.scalper.trade_history[-200:]

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2: ML LIVE LEARNING LOOP
    # ═══════════════════════════════════════════════════════════════

    def _record_trade_for_ml(self, symbol: str, action: str, indicators: Dict,
                              confidence: float, pnl: float, entry_price: float,
                              exit_price: float, atr: float):
        """Record trade features + outcome for ML live learning.
        
        Stores (features, label) pairs that will be used to retrain
        the XGBoost model periodically.
        """
        if not CONFIG.get("ml_live_learning_enabled", True):
            return

        # Fetch recent OHLC to compute support_distance and resistance_distance
        support_dist = 0.0
        resistance_dist = 0.0
        volatility_regime = 1.0 if indicators.get("adx", 0) > 25 else 0.0
        try:
            rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_H1, 0, 30)
            if rates is not None and len(rates) >= 20:
                closes = np.array([r['close'] for r in rates])
                highs = np.array([r['high'] for r in rates])
                lows = np.array([r['low'] for r in rates])
                # Support distance: (close - 20-period low) / close
                support_level = float(np.min(lows[-20:]))
                resistance_level = float(np.max(highs[-20:]))
                current_price = float(closes[-1])
                if current_price > 0:
                    support_dist = (current_price - support_level) / current_price
                    resistance_dist = (resistance_level - current_price) / current_price
                # Volatility regime: ATR percentile rank
                atrs = []
                for i in range(1, min(30, len(highs))):
                    tr = max(highs[i] - lows[i],
                             abs(highs[i] - closes[i-1]),
                             abs(lows[i] - closes[i-1]))
                    atrs.append(tr)
                if len(atrs) >= 14:
                    recent_atr = np.mean(atrs[-14:])
                    hist_atr = np.mean(atrs[-50:]) if len(atrs) >= 50 else np.mean(atrs)
                    volatility_regime = 1.0 if recent_atr > hist_atr else 0.0
        except Exception:
            pass

        # Build feature vector matching the model's expected input
        # Features: rsi, macd_hist, bb_width, atr_pct, volume_ratio,
        #           price_momentum, volatility_regime, trend_strength,
        #           support_distance, resistance_distance
        features = [
            indicators.get("rsi", 50),
            indicators.get("macd_hist", 0),
            indicators.get("bb_width", 0),
            atr / entry_price if entry_price > 0 else 0,  # atr_pct
            indicators.get("vol_ratio", 1.0),
            indicators.get("momentum_5", 0),
            volatility_regime,  # actual ATR percentile rank
            indicators.get("adx", 0),  # trend_strength
            support_dist,  # actual support distance
            resistance_dist,  # actual resistance distance
        ]

        # Label: 1 = profitable trade, 0 = losing trade
        label = 1 if pnl > 0 else 0

        # Store with metadata
        trade_record = {
            "features": features,
            "label": label,
            "pnl": pnl,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "time": datetime.now(timezone.utc).isoformat(),
        }

        self._ml_training_data.append(trade_record)

        # Keep only last N trades for training (configurable)
        max_data = CONFIG.get("ml_max_training_data", 200)
        if len(self._ml_training_data) > max_data:
            self._ml_training_data = self._ml_training_data[-max_data:]

        log.info(f"  ML DATA: recorded trade #{len(self._ml_training_data)} | "
                 f"{symbol} {action} | P&L=${pnl:+.2f} | Label={label}")

        # Check if it's time to retrain
        self._maybe_retrain_ml()

    def _maybe_retrain_ml(self):
        """Retrain ML model every N trades from real data."""
        retrain_interval = CONFIG.get("ml_retrain_interval", 20)
        
        if len(self._ml_training_data) < retrain_interval:
            return  # Not enough data yet

        # Don't retrain more than once per cycle
        if hasattr(self, '_last_ml_retrain_cycle') and self._last_ml_retrain_cycle == self.cycle_count:
            return

        # Check if we have enough diverse data
        labels = [t["label"] for t in self._ml_training_data]
        wins = sum(labels)
        losses = len(labels) - wins

        # Need minimum wins and losses for meaningful training (configurable)
        min_diversity = CONFIG.get("ml_min_diversity", 5)
        if wins < min_diversity or losses < min_diversity:
            log.info(f"  ML RETRAIN SKIPPED: need more diversity (W={wins} L={losses}, need {min_diversity} each)")
            return

        try:
            from apps.ml.predictor import MLPredictor
            from apps.ml.model import PredictionModel

            # Prepare training data
            X = np.array([t["features"] for t in self._ml_training_data])
            y = np.array([t["label"] for t in self._ml_training_data])

            # Create and train new model
            new_model = PredictionModel(model_type="xgboost")
            new_model.train(X, y)

            # Save to disk (backup old first)
            model_path = MODELS_DIR / "xgboost_model.pkl"
            backup_path = MODELS_DIR / "xgboost_model_backup.pkl"

            if model_path.exists():
                import shutil
                shutil.copy2(model_path, backup_path)

            new_model.save(str(model_path))

            self._last_ml_retrain_cycle = self.cycle_count
            self._ml_retrain_count += 1

            log.info(f"  ML RETRAIN #{self._ml_retrain_count}: trained on {len(y)} samples "
                     f"(W={wins} L={losses}) | Saved to {model_path}")

        except Exception as e:
            log.warning(f"  ML RETRAIN FAILED: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: EQUITY CURVE MA — Pause trading when equity < MA
    # ═══════════════════════════════════════════════════════════════

    def _update_equity_curve(self):
        """Track equity and check if below moving average."""
        acct = self.mt5.get_account_info()
        if not acct:
            return True  # Can't check, allow trading

        equity = acct["equity"]
        self.equity_curve.append(equity)

        # Keep only last N periods
        if len(self.equity_curve) > self.equity_curve_ma_period * 2:
            self.equity_curve = self.equity_curve[-self.equity_curve_ma_period * 2:]

        # Need at least MA period data points
        if len(self.equity_curve) < self.equity_curve_ma_period:
            return True  # Not enough data, allow trading

        # Calculate MA
        ma = sum(self.equity_curve[-self.equity_curve_ma_period:]) / self.equity_curve_ma_period

        if equity < ma:
            log.warning(f"  EQUITY CURVE PAUSE: equity ${equity:.2f} < MA ${ma:.2f} "
                       f"(period={self.equity_curve_ma_period})")
            return False  # Pause trading

        return True  # OK to trade

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY SELECTOR — LLM + rules pick aggressive vs conservative
    # ═══════════════════════════════════════════════════════════════

    def _select_strategy_profile(self, symbol: str, indicators: Dict, action: str,
                                  confidence: float, atr: float) -> Dict:
        """Select aggressive or conservative Kelly profile based on market conditions.
        
        Uses a hybrid approach:
        1. Rule-based scoring (fast, deterministic)
        2. LLM reasoning (slow, contextual) — when available
        3. Final decision combines both with override logic
        
        Returns: {"profile": "aggressive"|"conservative", "reason": str, "confidence": float}
        """
        profiles = CONFIG.get("kelly_profiles", {})
        if not profiles:
            return {"profile": "conservative", "reason": "no profiles configured", "confidence": 0.5}

        # ── RULE-BASED SCORING ──
        # Score > 0 → aggressive, Score < 0 → conservative
        score = 0
        reasons = []

        # Factor 1: ADX (trend strength)
        adx = indicators.get("adx", 20)
        if adx > 30:
            score += 2
            reasons.append(f"ADX={adx:.0f}>30 (strong trend)")
        elif adx < 20:
            score -= 2
            reasons.append(f"ADX={adx:.0f}<20 (weak/ranging)")
        else:
            reasons.append(f"ADX={adx:.0f} (moderate)")

        # Factor 2: Volume (confirmation)
        vol_ratio = indicators.get("vol_ratio", 1.0)
        if vol_ratio > 1.5:
            score += 1
            reasons.append(f"Vol={vol_ratio:.1f}x>1.5 (high conviction)")
        elif vol_ratio < 0.5:
            score -= 1
            reasons.append(f"Vol={vol_ratio:.1f}x<0.5 (low conviction)")

        # Factor 3: Ichimoku alignment (trend confirmation)
        tenkan = indicators.get("tenkan", 0)
        kijun = indicators.get("kijun", 0)
        senkou_a = indicators.get("senkou_a", 0)
        senkou_b = indicators.get("senkou_b", 0)
        close = indicators.get("close", 0)

        if close > 0 and tenkan > 0 and kijun > 0:
            if close > senkou_a > senkou_b and tenkan > kijun:
                score += 1
                reasons.append("Ichimoku: bullish cloud + TK cross")
            elif close < senkou_a < senkou_b and tenkan < kijun:
                score += 1
                reasons.append("Ichimoku: bearish cloud + TK cross")
            else:
                score -= 1
                reasons.append("Ichimoku: mixed signals")

        # Factor 4: RSI extremes (overbought/oversold)
        rsi = indicators.get("rsi", 50)
        if rsi > 70 or rsi < 30:
            # Extreme RSI in trend direction = aggressive, against = conservative
            if (action == "BUY" and rsi < 30) or (action == "SELL" and rsi > 70):
                score += 1
                reasons.append(f"RSI={rsi:.0f} (extreme in trade direction)")
            else:
                score -= 1
                reasons.append(f"RSI={rsi:.0f} (extreme against trade)")

        # Factor 5: Session (use config-driven bias)
        now_hour = datetime.now(timezone.utc).hour
        session_bias = CONFIG.get("session_strategy_bias", {}).get(now_hour, "neutral")
        if session_bias == "aggressive":
            score += 2
            reasons.append(f"Hour={now_hour} (session=AGGRESSIVE — London/NY overlap)")
        elif session_bias == "conservative":
            score -= 2
            reasons.append(f"Hour={now_hour} (session=CONSERVATIVE — off-peak/Asian)")
        else:
            reasons.append(f"Hour={now_hour} (session=neutral)")

        # Factor 6: Signal confidence
        if confidence > 0.7:
            score += 1
            reasons.append(f"Confidence={confidence:.2f}>0.7 (strong)")
        elif confidence < 0.4:
            score -= 1
            reasons.append(f"Confidence={confidence:.2f}<0.4 (weak)")

        # Factor 7: Win/loss streak (momentum)
        if len(self._trade_results) >= 3:
            recent = self._trade_results[-5:]
            wins = sum(1 for r in recent if r > 0)
            if wins >= 4:
                score += 1
                reasons.append(f"Win streak: {wins}/{len(recent)} recent")
            elif wins <= 1:
                score -= 1
                reasons.append(f"Loss streak: {len(recent)-wins}/{len(recent)} recent")

        # Factor 8: ATR relative (volatility opportunity)
        atr_pct = (atr / close * 100) if close > 0 else 0
        if atr_pct > 0.3:
            score += 1
            reasons.append(f"ATR%={atr_pct:.2f}% (good volatility)")
        elif atr_pct < 0.05:
            score -= 1
            reasons.append(f"ATR%={atr_pct:.2f}% (too quiet)")

        # ── LLM REASONING (when enabled) ──
        llm_choice = None
        llm_reason = ""
        if CONFIG.get("strategy_selector_enabled") and CONFIG.get("llm_enabled"):
            try:
                from apps.llm.client import LLMClient
                client = LLMClient()

                prompt = STRATEGY_SELECTION_PROMPT.format(
                    symbol=symbol,
                    action=action,
                    adx=adx,
                    rsi=rsi,
                    vol_ratio=vol_ratio,
                    atr_pct=f"{atr_pct:.3f}",
                    close=close,
                    tenkan=tenkan,
                    kijun=kijun,
                    senkou_a=senkou_a,
                    senkou_b=senkou_b,
                    session_hour=now_hour,
                    confidence=confidence,
                    current_balance=f"{self.risk.balance:.2f}",
                    open_positions=len(self.risk.open_positions),
                    recent_wins=sum(1 for r in self._trade_results[-10:] if r > 0) if self._trade_results else 0,
                    recent_losses=sum(1 for r in self._trade_results[-10:] if r <= 0) if self._trade_results else 0,
                )

                response = client.analyze(prompt, task="analysis")
                parsed = client._try_parse_json(response.text) if hasattr(client, '_try_parse_json') else {}
                if parsed:
                    llm_choice = parsed.get("profile", "conservative")
                    llm_reason = parsed.get("reasoning", "")
                    if llm_choice not in ["aggressive", "neutral", "conservative"]:
                        llm_choice = None  # Invalid response, fall back to rules
            except Exception as e:
                log.debug(f"  Strategy LLM failed (falling back to rules): {e}")

        # ── FINAL DECISION ──
        # Map score to profile: >+1 aggressive, -1 to +1 neutral, <-1 conservative
        if score > 1:
            rule_decision = "aggressive"
        elif score < -1:
            rule_decision = "conservative"
        else:
            rule_decision = "neutral"
        original_decision = rule_decision

        # Symbol-specific default override for borderline scores (score = 0)
        if score == 0:
            symbol_default = CONFIG.get("symbol_default_profiles", {}).get(symbol)
            if symbol_default:
                rule_decision = symbol_default
                reasons.append(f"Symbol default: {symbol} → {symbol_default}")

        # Performance bias: lean toward whichever profile performs better
        perf_bias = self._get_performance_bias()
        if perf_bias != 0:
            score += perf_bias
            reasons.append(f"Performance bias: {perf_bias:+d} (better profile gets edge)")
            # Recompute with performance bias
            if score > 1:
                rule_decision = "aggressive"
            elif score < -1:
                rule_decision = "conservative"
            else:
                rule_decision = "neutral"

        # LLM can override if confident and rule score is borderline (-1 to +1)
        final_decision = rule_decision
        override_reason = ""

        if llm_choice and abs(score) <= 2:
            # LLM override for borderline cases
            if llm_choice != rule_decision:
                final_decision = llm_choice
                override_reason = f"LLM override: {llm_reason}"
            else:
                override_reason = f"LLM agrees: {llm_reason}"
        elif llm_choice:
            # Strong rule score — log LLM opinion but follow rules
            override_reason = f"Rules dominate (score={score}), LLM said: {llm_choice}"
        else:
            override_reason = f"Rules only (score={score}): {'; '.join(reasons)}"

        # Ensure final_decision is valid
        if final_decision not in ["aggressive", "neutral", "conservative"]:
            final_decision = "conservative"

        profile_data = profiles.get(final_decision, profiles.get("conservative", {}))

        log.info(f"  STRATEGY {symbol}: {final_decision.upper()} "
                 f"(score={score}, llm={llm_choice or 'N/A'}) | "
                 f"{override_reason}")

        return {
            "profile": final_decision,
            "avg_win": profile_data.get("avg_win", 1.5),
            "avg_loss": profile_data.get("avg_loss", 1.0),
            "reason": override_reason,
            "rule_score": score,
            "llm_choice": llm_choice,
            "rule_factors": reasons,
        }

    def _get_profile_performance(self) -> Dict:
        """Get performance stats for each strategy profile.
        Returns: {profile: {trades, wins, win_rate, total_pnl, avg_pnl}}"""
        result = {}
        for profile, stats in self._profile_performance.items():
            trades = stats["trades"]
            wins = stats["wins"]
            total_pnl = stats["total_pnl"]
            win_rate = wins / trades if trades > 0 else 0
            avg_pnl = total_pnl / trades if trades > 0 else 0
            result[profile] = {
                "trades": trades,
                "wins": wins,
                "win_rate": round(win_rate, 3),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(avg_pnl, 2),
            }
        return result

    def _get_performance_bias(self) -> float:
        """Compute performance-based bias for strategy selection.
        Returns: positive = lean aggressive, negative = lean conservative.
        Based on which profile has better win rate and P&L."""
        agg = self._profile_performance.get("aggressive", {})
        con = self._profile_performance.get("conservative", {})

        agg_trades = agg.get("trades", 0)
        con_trades = con.get("trades", 0)

        # Need at least 5 trades per profile to use performance bias
        if agg_trades < 5 or con_trades < 5:
            return 0  # Not enough data

        agg_wr = agg.get("wins", 0) / agg_trades
        con_wr = con.get("wins", 0) / con_trades
        agg_avg = agg.get("total_pnl", 0) / agg_trades
        con_avg = con.get("total_pnl", 0) / con_trades

        # Compare win rates and average P&L
        bias = 0
        if agg_wr > con_wr + 0.05:  # Aggressive wins 5% more often
            bias += 1
        elif con_wr > agg_wr + 0.05:  # Conservative wins 5% more often
            bias -= 1

        if agg_avg > con_avg * 1.2:  # Aggressive makes 20% more per trade
            bias += 1
        elif con_avg > agg_avg * 1.2:  # Conservative makes 20% more per trade
            bias -= 1

        return bias

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: KELLY CRITERION — Dynamic position sizing
    # ═══════════════════════════════════════════════════════════════

    def _calculate_kelly_fraction(self, avg_win: float = None, avg_loss: float = None) -> float:
        """Calculate Kelly fraction from recent trade history.
        Uses quarter-Kelly capped at 0.25 for safety.
        If avg_win/avg_loss provided (from strategy profile), use those."""
        win_rate = CONFIG.get("kelly_win_rate", 0.55)
        if avg_win is None:
            avg_win = CONFIG.get("kelly_avg_win", 1.5)
        if avg_loss is None:
            avg_loss = CONFIG.get("kelly_avg_loss", 1.0)

        # If we have enough trade results, compute dynamic Kelly
        if len(self._trade_results) >= 10:
            recent = self._trade_results[-20:]  # Last 20 trades
            wins = [r for r in recent if r > 0]
            losses = [r for r in recent if r <= 0]
            if wins and losses:
                win_rate = len(wins) / len(recent)
                avg_win = sum(wins) / len(wins)
                avg_loss = abs(sum(losses) / len(losses))

        # Kelly formula: f* = (b*p - q) / b
        b = avg_win / avg_loss if avg_loss > 0 else 1.5
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b if b > 0 else 0

        # Quarter-Kelly for safety, capped at 0.25
        kelly = max(0, min(0.25, kelly / 4))

        self.kelly_fraction = kelly
        return kelly

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: CORRELATION HEDGING — Auto-hedge correlated positions
    # ═══════════════════════════════════════════════════════════════

    def _check_hedging(self, signal_symbol: str, signal_direction: str, signal_size: float):
        """Check if correlation hedging is needed after executing a trade."""
        if not CONFIG.get("hedging_enabled") or not self.hedging:
            return

        if not self.risk.open_positions:
            return

        # Build price data for correlation computation
        try:
            import pandas as pd
            price_data = {}
            for sym in list(self.risk.open_positions.keys()) + [signal_symbol]:
                df = self.mt5.get_candles(sym, "H1", 50)
                if df is not None and len(df) >= 50:
                    price_data[sym] = df["close"]

            if len(price_data) < 2:
                return

            corr_matrix = self.hedging.compute_correlations(price_data)
            if corr_matrix.empty:
                return

            # Check if we need to hedge
            hedge_decision = self.hedging.should_hedge(
                signal_symbol, signal_direction, signal_size,
                self.risk.open_positions, corr_matrix
            )

            if hedge_decision.get("hedge"):
                log.info(f"  HEDGE NEEDED: {hedge_decision['reason']} "
                        f"→ hedge {hedge_decision['hedge_symbol']} "
                        f"{hedge_decision['hedge_direction']} "
                        f"size={hedge_decision['hedge_size']}")

        except Exception as e:
            log.debug(f"  Hedging check skipped: {e}")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: EXIT OPTIMIZER — ML-enhanced exit decisions
    # ═══════════════════════════════════════════════════════════════

    def _get_optimized_exit(self, symbol: str, pos: dict) -> dict:
        """Get ML-optimized exit recommendation for a position."""
        if not CONFIG.get("exit_model_enabled") or not self.exit_optimizer:
            return {"method": "none"}

        try:
            trade_data = {
                "entry_price": pos.get("entry_price", 0),
                "current_price": pos.get("current_price", 0),
                "direction": pos.get("action", "BUY"),
                "atr": pos.get("atr", 0),
                "volatility": pos.get("atr", 0) / pos.get("entry_price", 1) if pos.get("entry_price", 0) > 0 else 0,
                "momentum": 0,
                "time_in_trade": (datetime.now(timezone.utc) - datetime.fromisoformat(pos.get("entry_time", datetime.now(timezone.utc).isoformat()))).total_seconds() / 3600,
                "unrealized_pnl": pos.get("profit", 0),
                "rsi": 50,
                "bb_position": 0.5,
                "session_hour": datetime.now(timezone.utc).hour,
            }

            result = self.exit_optimizer.predict_optimal_exit(trade_data)
            return result

        except Exception as e:
            log.debug(f"  Exit optimizer failed for {symbol}: {e}")
            return {"method": "fallback"}

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4: REGIME DETECTION — Adjust strategy by market state
    # ═══════════════════════════════════════════════════════════════

    def _get_regime_adjustment(self, symbol: str) -> float:
        """Get confidence adjustment based on market regime.
        Returns multiplier: >1.0 = boost, <1.0 = reduce."""
        if not CONFIG.get("regime_enabled") or not self.ensemble:
            return 1.0

        try:
            df = self.mt5.get_candles(symbol, "H1", 50)
            if df is None or len(df) < 50:
                return 1.0

            regime = self.ensemble.regime_detector.detect(df["close"].values)
            current_regime = regime.get("regime", "unknown")

            # Adjust confidence based on regime
            adjustments = {
                "TRENDING_UP": 1.1,    # Boost trend-following confidence
                "TRENDING_DOWN": 1.1,
                "RANGING": 0.85,       # Reduce confidence in ranging markets
                "VOLATILE": 0.9,       # Slightly reduce in volatile markets
            }

            adj = adjustments.get(current_regime, 1.0)
            log.debug(f"  REGIME {symbol}: {current_regime} → adjustment={adj:.2f}")
            return adj

        except Exception as e:
            log.debug(f"  Regime detection failed for {symbol}: {e}")
            return 1.0

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: SPREAD FILTER — Skip trades during wide spreads
    # ═══════════════════════════════════════════════════════════════

    def _check_spread(self, symbol: str) -> bool:
        """Check if spread is acceptable for trading. Returns True if OK."""
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return False

            spread = info.spread  # In points
            point = info.point if info.point else 0.0001
            spread_pips = spread * point * 10

            # Max spread thresholds by symbol type
            max_spread = 2.0  # Default 2 pips
            if "JPY" in symbol:
                max_spread = 1.5  # JPY pairs: tighter
            elif "GBP" in symbol:
                max_spread = 2.5  # GBP pairs: slightly wider
            elif "AUD" in symbol or "NZD" in symbol:
                max_spread = 2.0

            if spread_pips > max_spread:
                log.info(f"  SPREAD FILTER {symbol}: {spread_pips:.1f} pips > max {max_spread:.1f}")
                return False

            return True

        except Exception as e:
            log.debug(f"  Spread check failed for {symbol}: {e}")
            return True  # Allow if can't check

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: WIN/LOSS STREAK SCALING
    # ═══════════════════════════════════════════════════════════════

    def _get_streak_multiplier(self) -> float:
        """Get position size multiplier based on win/loss streak.
        Increase on wins (momentum), reduce on losses (protection)."""
        if self.consecutive_wins >= 5:
            return 1.3   # Hot streak: increase 30%
        elif self.consecutive_wins >= 3:
            return 1.15  # Winning: increase 15%
        elif self.consecutive_losses >= 3:
            return 0.5   # Cold streak: reduce 50%
        elif self.consecutive_losses >= 2:
            return 0.7   # Losing: reduce 30%
        return 1.0

    def _update_streaks(self, pnl: float):
        """Update win/loss streaks after a trade closes."""
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        self.last_trade_pnl = pnl

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: SESSION-BASED AGGRESSION
    # ═══════════════════════════════════════════════════════════════

    def _get_session_multiplier(self) -> float:
        """Get aggression multiplier based on current session.
        More aggressive during London-NY overlap, less during Asian."""
        hour = datetime.now(timezone.utc).hour

        # London-NY overlap (12-16 UTC) — best liquidity, tightest spreads
        if 12 <= hour <= 16:
            return 1.2   # +20% aggression
        # London session (7-12 UTC)
        elif 7 <= hour <= 12:
            return 1.0   # Normal
        # NY session (13-21 UTC)
        elif 13 <= hour <= 21:
            return 1.1   # Slight boost
        # Asian session (22-6 UTC) — low liquidity
        else:
            return 0.7   # -30% aggression

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: PORTFOLIO HEAT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    def _check_portfolio_heat(self) -> float:
        """Calculate total portfolio heat (risk exposure).
        Returns 0.0-1.0 scale: 0=safe, 1=max risk."""
        positions = self.risk.open_positions
        if not positions:
            return 0.0

        total_risk = 0
        for sym, pos in positions.items():
            size = pos.get("size", 0)
            entry = pos.get("entry_price", 0)
            sl = pos.get("sl", 0)
            if entry > 0 and sl > 0 and size > 0:
                risk_per_lot = abs(entry - sl) * 100000  # Approximate risk in USD
                total_risk += risk_per_lot * size

        # Normalize to equity
        equity = self.risk.balance
        if equity > 0:
            heat = total_risk / equity
            return min(1.0, heat)

        return 0.0

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: TRAILING TP — Move TP in profit direction
    # ═══════════════════════════════════════════════════════════════

    def _manage_trailing_tp(self, symbol: str, pos: dict, rm_pos: dict):
        """Move TP in profit direction when trade is well in profit."""
        if not CONFIG.get("trailing_enabled"):
            return

        entry = rm_pos.get("entry_price", 0)
        current = pos.get("current_price", 0)
        atr = rm_pos.get("atr", 0)
        tp = rm_pos.get("tp", 0)

        if entry == 0 or current == 0 or atr == 0:
            return

        if rm_pos["action"] == "BUY":
            unrealized = current - entry
            sl_distance = entry - rm_pos.get("sl", entry - atr) if rm_pos.get("sl", 0) > 0 else atr
        else:
            unrealized = entry - current
            sl_distance = rm_pos.get("sl", entry + atr) - entry if rm_pos.get("sl", 0) > 0 else atr

        rr_ratio = unrealized / sl_distance if sl_distance > 0 else 0

        # At 3R: move TP to 5R (let winners run)
        if rr_ratio >= 3.0 and tp > 0:
            new_tp_distance = sl_distance * 5
            if rm_pos["action"] == "BUY":
                new_tp = entry + new_tp_distance
                if new_tp > tp:
                    success = self.mt5.modify_sl_tp(pos["ticket"], tp=round(new_tp, 5))
                    if success:
                        rm_pos["tp"] = new_tp
                        log.info(f"  TRAILING TP {symbol}: BUY TP → {new_tp:.5f} (was {tp:.5f}) at {rr_ratio:.1f}R")
            else:
                new_tp = entry - new_tp_distance
                if new_tp < tp:
                    success = self.mt5.modify_sl_tp(pos["ticket"], tp=round(new_tp, 5))
                    if success:
                        rm_pos["tp"] = new_tp
                        log.info(f"  TRAILING TP {symbol}: SELL TP → {new_tp:.5f} (was {tp:.5f}) at {rr_ratio:.1f}R")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5: DYNAMIC ATR SL RECALCULATION
    # ═══════════════════════════════════════════════════════════════

    def _recalculate_sl(self, symbol: str, rm_pos: dict):
        """Recalculate SL based on current ATR if volatility changed significantly."""
        if not CONFIG.get("trailing_enabled"):
            return

        try:
            df = self.mt5.get_candles(symbol, "H1", 14)
            if df is None or len(df) < 14:
                return

            current_atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else 0
            original_atr = rm_pos.get("atr", current_atr)

            if original_atr == 0 or current_atr == 0:
                return

            # If ATR changed by more than 50%, recalculate SL
            atr_change = abs(current_atr - original_atr) / original_atr
            if atr_change > 0.5:
                entry = rm_pos["entry_price"]
                new_sl_distance = current_atr * CONFIG.get("sl_atr_mult", 3.0)

                if rm_pos["action"] == "BUY":
                    new_sl = entry - new_sl_distance
                    if new_sl > rm_pos.get("sl", 0):
                        success = self.mt5.modify_sl_tp(rm_pos["ticket"], sl=round(new_sl, 5))
                        if success:
                            rm_pos["sl"] = new_sl
                            rm_pos["atr"] = current_atr
                            log.info(f"  SL RECALC {symbol}: BUY SL → {new_sl:.5f} (ATR {original_atr:.5f}→{current_atr:.5f})")
                else:
                    new_sl = entry + new_sl_distance
                    if new_sl < rm_pos.get("sl", float('inf')):
                        success = self.mt5.modify_sl_tp(rm_pos["ticket"], sl=round(new_sl, 5))
                        if success:
                            rm_pos["sl"] = new_sl
                            rm_pos["atr"] = current_atr
                            log.info(f"  SL RECALC {symbol}: SELL SL → {new_sl:.5f} (ATR {original_atr:.5f}→{current_atr:.5f})")

        except Exception as e:
            log.debug(f"  SL recalculation failed for {symbol}: {e}")

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

        # Sync existing positions (skip scalper-owned positions to avoid double-tracking)
        SCALPER_MAGIC = 20260911  # Scalper uses different magic number
        positions = self.mt5.get_positions()
        for p in positions:
            if p.get("magic") == SCALPER_MAGIC:
                continue  # Skip scalper positions — tracked by scalper subsystem
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

    # ═══════════════════════════════════════════════════════════════
    # ANALYST CONSENSUS — Phase 1: Wire 6 working analysts into live loop
    # ═══════════════════════════════════════════════════════════════

    def _run_analyst_consensus(self, symbol: str, timeframe: str = "H1", df=None):
        """
        Run all 12 analysts on a symbol and return consensus.
        Returns: (consensus_action, confidence_modifier, analyst_details)
        """
        if not CONFIG.get("analyst_consensus_enabled"):
            return None, 0, {}

        analyst_classes = [
            ("Fundamentals", "apps.analysts.fundamentals", "FundamentalsAnalyst"),
            ("Quant", "apps.analysts.quant", "QuantAnalyst"),
            ("Market", "apps.analysts.market", "MarketAnalyst"),
            ("Risk", "apps.analysts.risk", "RiskAnalyst"),
            ("Technical", "apps.analysts.technical", "TechnicalAnalyst"),
            ("Compliance", "apps.analysts.compliance", "ComplianceAnalyst"),
            ("OrderFlow", "apps.analysts.order_flow", "OrderFlowAnalyst"),
            ("News", "apps.analysts.news", "NewsAnalyst"),
            ("Sentiment", "apps.analysts.sentiment", "SentimentAnalyst"),
            ("Macro", "apps.analysts.macro", "MacroAnalyst"),
            ("Options", "apps.analysts.options", "OptionsAnalyst"),
            ("OnChain", "apps.analysts.on_chain", "OnChainAnalyst"),
        ]

        votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
        total_confidence = 0
        analyst_results = []
        active_analysts = 0

        import importlib
        for name, mod_path, cls_name in analyst_classes:
            try:
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, cls_name)
                analyst = cls()

                # Run analyst asynchronously if needed
                import asyncio
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(analyst.analyze(symbol, timeframe))
                loop.close()

                signal = result.signal.upper() if hasattr(result, 'signal') else "HOLD"
                confidence = float(result.confidence) if hasattr(result, 'confidence') else 0.5

                if signal not in ("BUY", "SELL", "HOLD"):
                    signal = "HOLD"

                votes[signal] += 1
                total_confidence += confidence
                active_analysts += 1

                analyst_results.append({
                    "name": name,
                    "signal": signal,
                    "confidence": round(confidence, 3),
                    "reasoning": (result.reasoning[:150] if hasattr(result, 'reasoning') and result.reasoning else ""),
                })

                log.debug(f"    ANALYST {name:15} → {signal} ({confidence:.2f})")

            except Exception as e:
                log.debug(f"    ANALYST {name:15} → ERROR: {str(e)[:80]}")
                analyst_results.append({
                    "name": name, "signal": "HOLD", "confidence": 0,
                    "reasoning": f"Error: {str(e)[:100]}",
                })

        if active_analysts == 0:
            return None, 0, {"analysts": [], "active": 0}

        # Calculate consensus — compare BUY vs SELL only (HOLDs don't block)
        total = active_analysts
        buy_pct = votes["BUY"] / total
        sell_pct = votes["SELL"] / total
        hold_pct = votes["HOLD"] / total
        directional = votes["BUY"] + votes["SELL"]  # analysts with a view
        avg_confidence = total_confidence / total

        # Determine consensus action
        # Rule: if BUY > SELL and BUY >= 3 analysts (or >30% of total) → BUY
        #       if SELL > BUY and SELL >= 3 analysts (or >30% of total) → SELL
        #       otherwise → HOLD
        min_directional = max(3, int(total * 0.25))  # at least 3 or 25%

        if votes["BUY"] > votes["SELL"] and votes["BUY"] >= min_directional:
            consensus_action = "BUY"
            agreement_pct = buy_pct
        elif votes["SELL"] > votes["BUY"] and votes["SELL"] >= min_directional:
            consensus_action = "SELL"
            agreement_pct = sell_pct
        else:
            consensus_action = "HOLD"
            agreement_pct = max(buy_pct, sell_pct)

        # Calculate confidence modifier
        confidence_modifier = 0
        if consensus_action != "HOLD":
            if directional >= total * 0.70:  # 70%+ have a view → strong
                confidence_modifier = CONFIG["analyst_confidence_boost"]
            elif directional >= total * 0.50:  # 50-69% have a view → moderate
                confidence_modifier = CONFIG["analyst_confidence_boost"] * 0.5
            elif directional < total * 0.30:  # <30% have a view → penalty
                confidence_modifier = -CONFIG["analyst_confidence_penalty"]

        details = {
            "analysts": analyst_results,
            "active": active_analysts,
            "votes": votes,
            "consensus": consensus_action,
            "agreement_pct": round(agreement_pct, 3),
            "avg_confidence": round(avg_confidence, 3),
            "confidence_modifier": round(confidence_modifier, 3),
        }

        log.info(f"  ANALYSTS [{active_analysts}] consensus={consensus_action} "
                 f"agreement={agreement_pct:.0%} avg_conf={avg_confidence:.2f} "
                 f"modifier={confidence_modifier:+.2f}")

        return consensus_action, confidence_modifier, details

    def _run_legendary_consensus(self, symbol: str, df=None):
        """
        Run the 5 legendary agents on a symbol and return consensus.
        Returns: (consensus_action, confidence_modifier, legendary_details)
        """
        if not CONFIG.get("legendary_consensus_enabled"):
            return None, 0, {}

        if df is None or len(df) < 50:
            return None, 0, {}

        legendary_classes = [
            ("Soros", "apps.legendary.soros", "SorosAgent"),
            ("Buffett", "apps.legendary.buffett", "BuffettAgent"),
            ("Druckenmiller", "apps.legendary.druckenmiller", "DruckenmillerAgent"),
            ("TudorJones", "apps.legendary.tudor_jones", "TudorJonesAgent"),
            ("Lynch", "apps.legendary.lynch", "LynchAgent"),
        ]

        votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
        total_confidence = 0
        agent_results = []
        active_agents = 0

        import importlib
        for name, mod_path, cls_name in legendary_classes:
            try:
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, cls_name)
                agent = cls()
                # All legendary agents expect (data, symbol) — NOT (symbol, data)
                result = agent.analyze(df, symbol)

                # Agents return Dict[str, Any], not objects — use dict access
                signal = result.get("signal", "HOLD").upper() if isinstance(result, dict) else "HOLD"
                confidence = float(result.get("confidence", 0.5)) if isinstance(result, dict) else 0.5

                if signal not in ("BUY", "SELL", "HOLD"):
                    signal = "HOLD"

                votes[signal] += 1
                total_confidence += confidence
                active_agents += 1

                agent_results.append({
                    "name": name,
                    "signal": signal,
                    "confidence": round(confidence, 3),
                })

            except Exception as e:
                log.debug(f"    LEGENDARY {name:15} → ERROR: {str(e)[:80]}")
                agent_results.append({"name": name, "signal": "HOLD", "confidence": 0})

        if active_agents == 0:
            return None, 0, {"agents": [], "active": 0}

        total = active_agents
        buy_pct = votes["BUY"] / total
        sell_pct = votes["SELL"] / total
        hold_pct = votes["HOLD"] / total

        if buy_pct > sell_pct and buy_pct > hold_pct and buy_pct >= 0.50:
            consensus_action = "BUY"
            agreement_pct = buy_pct
        elif sell_pct > buy_pct and sell_pct > hold_pct and sell_pct >= 0.50:
            consensus_action = "SELL"
            agreement_pct = sell_pct
        else:
            consensus_action = "HOLD"
            agreement_pct = hold_pct

        avg_confidence = total_confidence / total
        confidence_modifier = 0
        if consensus_action != "HOLD":
            if agreement_pct >= 0.80:
                confidence_modifier = 0.15
            elif agreement_pct >= 0.60:
                confidence_modifier = 0.075
            elif agreement_pct < 0.50:
                confidence_modifier = -0.10

        details = {
            "agents": agent_results,
            "active": active_agents,
            "votes": votes,
            "consensus": consensus_action,
            "agreement_pct": round(agreement_pct, 3),
            "avg_confidence": round(avg_confidence, 3),
            "confidence_modifier": round(confidence_modifier, 3),
        }

        log.info(f"  LEGENDARY [{active_agents}] consensus={consensus_action} "
                 f"agreement={agreement_pct:.0%} avg_conf={avg_confidence:.2f} "
                 f"modifier={confidence_modifier:+.2f}")

        return consensus_action, confidence_modifier, details

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
            self.risk.update_equity(acct["equity"])
            log.info(f"  Balance: ${acct['balance']:.2f} | Equity: ${acct['equity']:.2f} | DD: {self.risk.get_drawdown_pct()*100:.1f}%")

        # ── DAILY LIMITS CHECK (before anything else) ──
        if not self.risk.can_trade_today():
            daily = self.risk.get_daily_status()
            if daily["target_hit"]:
                log.warning(f"  DAILY TARGET HIT — stopping trades. P&L=${daily['daily_pnl']:+.2f} ({daily['daily_return']:.2%})")
            elif daily["limit_hit"]:
                log.warning(f"  DAILY LOSS LIMIT — stopping trades. P&L=${daily['daily_pnl']:+.2f} ({daily['daily_return']:.2%})")
            # Still manage existing positions (trailing, exits) but no new trades
            self._manage_existing_positions()
            return

        # Check drawdown pause
        risk_mult = self.risk.get_risk_multiplier()
        if risk_mult <= 0:
            log.warning(f"  TRADING PAUSED — DD {self.risk.get_drawdown_pct()*100:.1f}% > {CONFIG['drawdown_pause_pct']*100:.0f}%")
            return

        # Check circuit breaker
        if not self.risk.check_circuit_breaker():
            log.warning(f"  CIRCUIT BREAKER ACTIVE — {self.risk.consecutive_losses} consecutive losses")
            return

        # Phase 4: Equity Curve MA — pause if equity below moving average
        if not self._update_equity_curve():
            log.warning(f"  EQUITY CURVE PAUSE — equity below {self.equity_curve_ma_period}-period MA")
            return

        # Manage existing positions (trailing stops, partial TP)
        self._manage_existing_positions()

        # ═══ COMPUTE RISK PARITY ONCE PER CYCLE (not per-symbol) ═══
        if NEW_FEATURES_AVAILABLE and self.risk_parity and CONFIG.get("risk_parity_enabled"):
            try:
                if self.risk_parity.should_rebalance(interval_hours=4):
                    price_data = {}
                    for sym in WATCHLIST:
                        sym_df = self.mt5.fetch_candles(sym, TIMEFRAME, 100)
                        if sym_df is not None and len(sym_df) > 20:
                            price_data[sym] = sym_df["close"]
                    if len(price_data) >= 2:
                        self.risk_parity.calculate_weights(price_data)
                        log.info(f"  RISK PARITY: weights computed for {len(price_data)} symbols: "
                                 + ", ".join(f"{s}={w:.2f}" for s, w in list(self.risk_parity.weights.items())[:5]))
            except Exception as e:
                log.debug(f"  Risk parity rebalance skipped: {e}")

        # MTF Cascading Scalper
        if self.scalper:
            # ── CROSS-DEDUP: Prevent scalper from trading symbols already held by main engine ──
            scalp_blocked_symbols = set(self.risk.open_positions.keys())
            self.scalper.blocked_symbols = scalp_blocked_symbols
            self.scalper.scan_and_execute()
            self.scalper.refresh_trade_statuses()
            # ── SCALPER INTEGRATION: Feed scalp results into main engine ──
            self._sync_scalp_results()
            # ── Register scalp positions with risk manager for portfolio limits ──
            for ticket, scalp in self.scalper.open_scalps.items():
                sym = scalp["symbol"]
                if sym not in self.risk.open_positions:
                    self.risk.open_positions[sym] = {
                        "size": scalp["size"],
                        "direction": scalp["direction"],
                        "entry_price": scalp["entry_price"],
                        "source": "scalper",
                        "ticket": ticket,
                    }

        # Scan all symbols
        signals = []
        for symbol in WATCHLIST:
            signal = self._analyze_symbol(symbol)
            if signal and signal.direction != SignalDirection.HOLD:
                signals.append(signal)
                log.info(f"  SIGNAL {symbol}: {signal.direction.value} conf={signal.confidence:.3f}")
        log.info(f"  SIGNALS: {len(signals)}/{len(WATCHLIST)} passed all gates")

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
            # V3: Per-symbol cooldown check (cooldown in hours = bars on H1)
            v3_configs = CONFIG.get("v3_symbol_configs", {})
            if signal.symbol in v3_configs:
                cd_hours = v3_configs[signal.symbol].get("cooldown", 3)
                last_t = self.risk.last_trade_time.get(signal.symbol)
                if last_t:
                    from datetime import timezone as _tz
                    now_utc = datetime.now(_tz.utc)
                    elapsed_h = (now_utc - last_t).total_seconds() / 3600
                    if elapsed_h < cd_hours:
                        continue  # Still in cooldown
            # ── CROSS-DEDUP: Skip if scalper already has this symbol open ──
            if self.scalper:
                scalper_has_symbol = any(
                    s["symbol"] == signal.symbol and s["status"] == "OPEN"
                    for s in self.scalper.open_scalps.values()
                )
                if scalper_has_symbol:
                    log.info(f"  SKIP {signal.symbol} — scalper already has position")
                    continue

            self._execute_trade(signal)

        # ── WEEKLY PROFIT EXTRACTION CHECK ──
        extraction = self.risk.check_weekly_extraction()
        if extraction.get("extract"):
            log.info(f"  EXTRACTION READY: {extraction['reason']}")
            # In production, this would trigger an MT5 withdrawal request
            # For now, we log it and mark as extracted
            self.risk.record_extraction(extraction["amount"])

        # Summary
        state = self.risk.get_state()
        daily = self.risk.get_daily_status()
        scalp_status = ""
        if self.scalper:
            ss = self.scalper.get_status()
            scalp_status = f" | Scalps={ss['open_scalps']}/{ss['total_trades']}({ss['symbol']})"
        log.info(f"\n  SUMMARY: {state['open_positions']} open | {state['total_trades']} trades | "
                 f"WR={state['wins']}/{state['total_trades']} | P&L=${state['total_pnl']:+.2f} | "
                 f"CB={self.risk.circuit_breaker_state}{scalp_status}")
        log.info(f"  DAILY: P&L=${daily['daily_pnl']:+.2f} ({daily['daily_return']:.2%}) | "
                 f"Trades={daily['daily_trades']} | WR={daily['daily_wins']}/{daily['daily_trades']} | "
                 f"Target={daily['profit_target']:.1%} Limit=-{daily['loss_limit']:.1%}")

    def _analyze_symbol(self, symbol: str) -> Optional[Signal]:
        """Full analysis pipeline for one symbol."""
        now = datetime.now(timezone.utc)

        # Layer 1-2: Fetch H1 data + compute indicators
        df = self.mt5.fetch_candles(symbol, TIMEFRAME, 200)
        if df is None or len(df) < 60:
            log.info(f"  {symbol}: SKIP data={len(df) if df is not None else 'None'}")
            return None

        df = compute_indicators(df)
        df = df.dropna()
        if len(df) == 0:
            log.info(f"  {symbol}: SKIP no rows after dropna")
            return None

        row = df.iloc[-1]
        row._symbol = symbol  # Attach symbol for pivot point cache
        action, confidence, details = generate_signal(row)

        if action == "HOLD" or confidence < CONFIG["min_confidence"]:
            log.info(f"  {symbol}: SKIP action={action} conf={confidence:.3f} < {CONFIG['min_confidence']}")
            return None

        # Layer 3: Multi-timeframe confirmation
        mtf_data = fetch_mtf_data(symbol, CONFIG["mtf_timeframes"])
        mtf_dir, mtf_agreement, mtf_details = mtf_analysis(mtf_data)

        # Require MTF agreement
        if mtf_dir != action:
            log.info(f"  {symbol}: MTF KILLED h1={action} mtf={mtf_dir}")
            return None

        # Layer 4: LLM confirmation
        # Compute support/resistance distance for ML features
        support_distance = 0.0
        resistance_distance = 0.0
        try:
            if len(df) >= 20:
                recent_lows = df['low'].tail(20).values
                recent_highs = df['high'].tail(20).values
                current_price = float(row.get("close", 0))
                if current_price > 0:
                    support_level = float(np.min(recent_lows))
                    resistance_level = float(np.max(recent_highs))
                    support_distance = (current_price - support_level) / current_price
                    resistance_distance = (resistance_level - current_price) / current_price
        except Exception:
            pass

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
            "support_distance": round(support_distance, 6),
            "resistance_distance": round(resistance_distance, 6),
            "volatility_regime": 1.0 if float(row.get("adx", 0)) > 25 else 0.0,
            # ── New indicators ──
            "ppo": round(float(row.get("ppo", 0)), 4),
            "ppo_hist": round(float(row.get("ppo_hist", 0)), 4),
            "bbstop_upper": round(float(row.get("bbstop_upper", 0)), 5),
            "bbstop_lower": round(float(row.get("bbstop_lower", 0)), 5),
        }

        llm_result = llm_analyze(symbol, indicator_dict, action)

        # Layer 5: Analyst Consensus (Phase 1 — 6 working analysts + 5 legendary)
        analyst_consensus_action, analyst_mod, analyst_details = self._run_analyst_consensus(symbol, TIMEFRAME, df)
        legendary_consensus_action, legendary_mod, legendary_details = self._run_legendary_consensus(symbol, df)

        # Apply confidence modifiers from analyst/legendary consensus
        total_modifier = analyst_mod + legendary_mod
        adjusted_confidence = max(0, min(1.0, confidence + total_modifier))

        # Check if analysts block the trade
        if analyst_consensus_action and analyst_consensus_action != "HOLD" and analyst_consensus_action != action:
            # Analysts disagree with indicator signal — check if they override
            disagreement_count = sum(1 for a in analyst_details.get("analysts", [])
                                    if a["signal"] == analyst_consensus_action and a["confidence"] > 0.6)
            if disagreement_count >= 4:  # Strong analyst disagreement
                log.info(f"  BLOCKED by {disagreement_count} analysts: they say {analyst_consensus_action} vs {action}")
                return None
            elif disagreement_count >= 3:
                # Reduce confidence further
                adjusted_confidence *= 0.7
                log.info(f"  WARNING: {disagreement_count} analysts disagree → confidence reduced to {adjusted_confidence:.2f}")

        # If legendary agents strongly disagree, reduce confidence
        if legendary_consensus_action and legendary_consensus_action != "HOLD" and legendary_consensus_action != action:
            legendary_disagree = sum(1 for a in legendary_details.get("agents", [])
                                    if a["signal"] == legendary_consensus_action)
            if legendary_disagree >= 4:
                adjusted_confidence *= 0.75
                log.info(f"  LEGENDARY WARNING: {legendary_disagree} agents disagree → confidence reduced to {adjusted_confidence:.2f}")

        # Re-check minimum confidence after adjustments
        if adjusted_confidence < CONFIG["min_confidence"]:
            log.info(f"  REJECTED: confidence {adjusted_confidence:.3f} < min {CONFIG['min_confidence']}")
            return None

        # Layer 6: ML ranking — GATE trades by ML confidence
        ml_p_up = ml_rank(indicator_dict)
        ml_min = CONFIG.get("ml_min_confidence", 0.50)

        # ML gating: ONLY boost when ML strongly agrees (never penalize with unreliable model)
        # BUG FIX: Model trained on synthetic data (57.6% accuracy) — too unreliable to block trades
        if action == "BUY" and ml_p_up > 0.65:
            ml_boost = (ml_p_up - 0.5) * 0.2
            adjusted_confidence = min(1.0, adjusted_confidence + ml_boost)
            log.info(f"  ML BOOST {symbol}: BUY confirmed p_up={ml_p_up:.3f} → boost={ml_boost:.3f}")
        elif action == "SELL" and ml_p_up < 0.35:
            ml_boost = (0.5 - ml_p_up) * 0.2
            adjusted_confidence = min(1.0, adjusted_confidence + ml_boost)
            log.info(f"  ML BOOST {symbol}: SELL confirmed p_up={ml_p_up:.3f} → boost={ml_boost:.3f}")
        else:
            log.info(f"  ML NEUTRAL {symbol}: p_up={ml_p_up:.3f} (no boost/penalty)")

        # Layer 7: Regime detection — adjust confidence by market state
        regime_adj = self._get_regime_adjustment(symbol)
        # BUG FIX: Don't let regime push confidence below min_confidence
        adjusted_confidence = adjusted_confidence * regime_adj
        adjusted_confidence = max(adjusted_confidence, CONFIG["min_confidence"] * 0.8)  # Allow slight dip but not full kill
        adjusted_confidence = min(1.0, adjusted_confidence)
        if regime_adj != 1.0:
            log.info(f"  REGIME {symbol}: adjustment={regime_adj:.2f} → confidence={adjusted_confidence:.3f}")

        # Re-check minimum after ML and regime adjustments
        if adjusted_confidence < CONFIG["min_confidence"]:
            log.info(f"  REJECTED after ML/regime: confidence {adjusted_confidence:.3f} < min {CONFIG['min_confidence']}")
            return None

        # Calculate SL/TP
        atr = float(row.get("atr", 0))
        price = float(row["close"])

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
        sl, tp = self.risk.calculate_sl_tp(price, atr, action, symbol)

        # Create signal
        signal = Signal(
            symbol=symbol,
            direction=SignalDirection(action),
            score=adjusted_confidence * 8,
            confidence=adjusted_confidence,
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
            "analysts": analyst_details,
            "legendary": legendary_details,
            "ml_p_up": round(ml_p_up, 3),
            "confidence_original": round(confidence, 3),
            "confidence_adjusted": round(adjusted_confidence, 3),
            "confidence_modifier": round(total_modifier, 3),
            "features": feature_data,
        }

        log.info(f"  SIGNAL {symbol:8} {action:4} | Score={adjusted_confidence*8:.1f} "
                 f"(orig={confidence*8:.1f} mod={total_modifier:+.2f}) | "
                 f"MTF={mtf_agreement:.0%} | "
                 f"LLM={llm_result.get('signal','?')}({llm_result.get('confidence',0):.2f}) | "
                 f"ML={ml_p_up:.3f} | "
                 f"Analysts={analyst_details.get('consensus','?')} "
                 f"Legendary={legendary_details.get('consensus','?')}")

        # ── Monitor: log signal event ──
        self.monitor_log(symbol, "signal",
                         f"{action} score={adjusted_confidence*8:.1f} ML={ml_p_up:.3f} LLM={llm_result.get('signal','?')}({llm_result.get('confidence',0):.2f})")

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

        # Phase 5: Spread filter — skip if spread too wide
        if not self._check_spread(signal.symbol):
            return

        # Phase 5: Portfolio heat check
        heat = self._check_portfolio_heat()
        if heat >= 0.15:  # Max 15% portfolio heat
            log.info(f"  SKIP {signal.symbol} — portfolio heat too high ({heat:.1%})")
            return

        # Calculate position size with risk parity
        vol = float(signal.indicators.get("vol_ratio", 1.0))
        lots = self.risk.calculate_position_size(
            signal.entry_price, signal.atr, signal.confidence,
            now.hour, vol, symbol=signal.symbol
        )

        # Phase 4+: Strategy Profile Selection — LLM + rules pick aggressive/conservative
        strategy_profile = self._select_strategy_profile(
            signal.symbol, signal.indicators, signal.direction.value,
            signal.confidence, signal.atr
        )
        profile_avg_win = strategy_profile.get("avg_win", 1.5)
        profile_avg_loss = strategy_profile.get("avg_loss", 1.0)
        profile_name = strategy_profile.get("profile", "conservative")

        # Phase 4: Kelly Criterion — scale position size by Kelly fraction (using selected profile)
        kelly = self._calculate_kelly_fraction(avg_win=profile_avg_win, avg_loss=profile_avg_loss)
        # Kelly scale should be between 0.5 and 1.5 (never below half or above 1.5x)
        kelly_scale = max(0.5, min(1.5, kelly / 0.10))  # Normalize to config max (0.10 = quarter Kelly)
        lots = lots * kelly_scale

        # Phase 5: Session-based aggression multiplier
        session_mult = self._get_session_multiplier()
        lots = lots * session_mult

        # Phase 5: Win/loss streak scaling
        streak_mult = self._get_streak_multiplier()
        lots = lots * streak_mult

        lots = round(lots, 2)
        # Ensure minimum lot size
        if lots > 0 and lots < 0.01:
            lots = 0.01
        log.info(f"  SIZING: profile={profile_name} kelly={kelly_scale:.2f} session={session_mult:.2f} streak={streak_mult:.2f} → lots={lots:.2f}")

        # Apply risk parity weighting
        if CONFIG.get("risk_parity_enabled") and self.risk_parity and self.risk_parity.weights:
            parity_lots = self.risk_parity.get_position_size(
                signal.symbol, self.risk.balance,
                CONFIG.get("daily_risk_per_trade_pct", CONFIG["max_risk_pct"]),
                signal.entry_price
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

        # ── CONSENSUS GATES: Multi-gate safety layer ──
        if self.consensus_gates:
            try:
                # Gate 1: ML model prediction
                ml_features = [
                    signal.indicators.get("rsi", 50),
                    signal.indicators.get("macd_hist", 0),
                    signal.indicators.get("bb_width", 0),
                    signal.atr / signal.entry_price if signal.entry_price > 0 else 0,
                    signal.indicators.get("vol_ratio", 1.0),
                    signal.indicators.get("momentum_5", 0),
                    1.0 if signal.indicators.get("adx", 0) > 25 else 0.0,
                    signal.indicators.get("adx", 0),
                    signal.indicators.get("support_distance", 0.0),
                    signal.indicators.get("resistance_distance", 0.0),
                ]
                ml_gate = self.consensus_gates.check_ml_model(ml_features)
                if not ml_gate.passed:
                    log.info(f"  ML GATE BLOCKED {signal.symbol} — {ml_gate.reason}")
                    self.monitor_log(signal.symbol, "gate_blocked", f"ML: {ml_gate.reason}")
                    return

                # Gate 4: Technical confidence — use engine's min_confidence (0.25)
                # not the gate's default 0.70, since signal.confidence is already filtered
                from apps.analysts.base import AnalystResult
                tech_result = AnalystResult(
                    analyst_name="Technical",
                    symbol=signal.symbol,
                    timeframe="M15",
                    signal="BUY" if signal.direction.value == "BUY" else "SELL",
                    confidence=signal.confidence,
                    reasoning="Technical gate",
                    data_source="technical",
                )
                # Override threshold to match engine's min_confidence
                old_threshold = self.consensus_gates.MIN_TECHNICAL_CONFIDENCE
                self.consensus_gates.MIN_TECHNICAL_CONFIDENCE = CONFIG.get("min_confidence", 0.25)
                tech_gate = self.consensus_gates.check_technical([tech_result])
                self.consensus_gates.MIN_TECHNICAL_CONFIDENCE = old_threshold  # restore
                if not tech_gate.passed:
                    log.info(f"  TECHNICAL GATE BLOCKED {signal.symbol} — {tech_gate.reason}")
                    self.monitor_log(signal.symbol, "gate_blocked", f"TECH: {tech_gate.reason}")
                    return

                # Gate 5: Edge after costs
                # Edge = ML confidence - 0.5 (null hypothesis). Must exceed MIN_EDGE_AFTER_COSTS.
                # For forex, the "edge" is how much better than random (50/50) the ML predicts.
                ml_confidence = ml_gate.value if ml_gate.value else 0.5
                edge_value = ml_confidence - 0.5
                edge_gate = self.consensus_gates.check_edge(ml_confidence, 0.5)
                if not edge_gate.passed:
                    log.info(f"  EDGE GATE BLOCKED {signal.symbol} — {edge_gate.reason}")
                    self.monitor_log(signal.symbol, "gate_blocked", f"EDGE: {edge_gate.reason}")
                    return

                # Gate 7: Liquidity / position limits
                risk_state = self.risk.get_state()
                risk_state["max_positions"] = CONFIG["max_concurrent_trades"]
                risk_state["current_positions"] = len(self.risk.open_positions)
                liq_gate = self.consensus_gates.check_liquidity_limits(risk_state)
                if not liq_gate.passed:
                    log.info(f"  LIQUIDITY GATE BLOCKED {signal.symbol} — {liq_gate.reason}")
                    self.monitor_log(signal.symbol, "gate_blocked", f"LIQ: {liq_gate.reason}")
                    return

                log.info(f"  GATES PASSED {signal.symbol} — ML={ml_gate.passed} TECH={tech_gate.passed} EDGE={edge_gate.passed} LIQ={liq_gate.passed}")
                self.monitor_log(signal.symbol, "gate_all_passed",
                                 f"ML={ml_gate.value:.3f} TECH={tech_gate.value:.3f} EDGE={edge_gate.value:.3f}")
            except Exception as e:
                log.debug(f"  ConsensusGates check failed (non-blocking): {e}")

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
                "atr": signal.atr,
                "strategy_profile": profile_name,
                "profile_reason": strategy_profile.get("reason", ""),
                # Store indicators for ML live learning
                "indicators": signal.indicators.copy() if signal.indicators else {},
                "confidence": signal.confidence,
            }
            log.info(f"  EXECUTED {signal.symbol:8} {signal.direction.value:4} @ {signal.entry_price:.5f} "
                     f"lots={lots} SL={signal.sl_price:.5f} TP={signal.tp_price:.5f} "
                     f"profile={profile_name} ticket={ticket}")
            self.monitor_log(signal.symbol, "order_placed",
                             f"{signal.direction.value} lots={lots} @ {signal.entry_price:.5f} ticket={ticket}")
            # V3: Record last trade time for per-symbol cooldown
            self.risk.last_trade_time[signal.symbol] = now

            # Phase 4: Check correlation hedging after execution
            self._check_hedging(signal.symbol, signal.direction.value, lots)
        else:
            log.error(f"  FAILED {signal.symbol} — order not placed")
            self.monitor_log(signal.symbol, "order_failed", "MT5 rejected or market closed")

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

            # Phase 5: Trailing TP — move TP in profit direction
            self._manage_trailing_tp(symbol, pos, rm_pos)

            # Phase 5: Dynamic SL recalculation based on ATR changes
            self._recalculate_sl(symbol, rm_pos)

            # Phase 4: Exit Optimizer — ML-enhanced exit decision
            if CONFIG.get("exit_model_enabled") and self.exit_optimizer:
                exit_rec = self._get_optimized_exit(symbol, rm_pos)
                if exit_rec.get("method") != "none" and exit_rec.get("method") != "fallback":
                    rec_price = exit_rec.get("exit_price", 0)
                    if rec_price > 0:
                        current = pos["current_price"]
                        if rm_pos["action"] == "BUY" and current >= rec_price:
                            log.info(f"  EXIT OPTIMIZER {symbol}: BUY exit at {rec_price:.5f} (current={current:.5f})")
                            self._close_trade(symbol, ticket, "EXIT_OPTIMIZER")
                            continue
                        elif rm_pos["action"] == "SELL" and current <= rec_price:
                            log.info(f"  EXIT OPTIMIZER {symbol}: SELL exit at {rec_price:.5f} (current={current:.5f})")
                            self._close_trade(symbol, ticket, "EXIT_OPTIMIZER")
                            continue

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
                    # V3: Use per-symbol trail multiplier if available
                    v3_configs = CONFIG.get("v3_symbol_configs", {})
                    trail_mult = v3_configs.get(symbol, {}).get("trail", CONFIG["trailing_atr_mult"])
                    trail_distance = atr * trail_mult
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

                # ── DDFX BBStop: Volatility-adaptive trailing using Bollinger Band ──
                # If price closes beyond the 1.5-std BB stop level, tighten trail
                if CONFIG.get("bbstop_enabled", True) and rr_ratio >= 1.0:
                    try:
                        sym_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
                        if sym_rates is not None and len(sym_rates) >= 20:
                            closes_h1 = np.array([r['close'] for r in sym_rates])
                            bb_sma = float(np.mean(closes_h1[-20:]))
                            bb_std = float(np.std(closes_h1[-20:]))
                            if rm_pos["action"] == "BUY":
                                # BB stop = mid - 1.5*std (tighter than normal trailing)
                                bb_stop = bb_sma - 1.5 * bb_std
                                if bb_stop > rm_pos["sl"] and bb_stop < current:
                                    success = self.mt5.modify_sl_tp(ticket, sl=round(bb_stop, 5))
                                    if success:
                                        rm_pos["sl"] = round(bb_stop, 5)
                                        log.info(f"  DDFX BBSTOP {symbol} — SL → {bb_stop:.5f} (BB tight stop, RR={rr_ratio:.1f})")
                            else:
                                bb_stop = bb_sma + 1.5 * bb_std
                                if bb_stop < rm_pos["sl"] or rm_pos["sl"] == 0 and bb_stop > current:
                                    success = self.mt5.modify_sl_tp(ticket, sl=round(bb_stop, 5))
                                    if success:
                                        rm_pos["sl"] = round(bb_stop, 5)
                                        log.info(f"  DDFX BBSTOP {symbol} — SL → {bb_stop:.5f} (BB tight stop, RR={rr_ratio:.1f})")
                    except Exception:
                        pass  # Non-critical, continue with standard trailing

    def _close_trade(self, symbol: str, ticket: int, reason: str):
        """Close a trade and record result."""
        pos = self.risk.open_positions.get(symbol)
        if not pos:
            return

        # Get actual P&L before closing
        pnl = pos.get("profit", 0)

        success = self.mt5.close_position(ticket)
        if success:
            # Record in risk manager with actual P&L
            if pnl == 0:
                # Fallback: try to get from MT5 deal history
                try:
                    deals = mt5.history_deals_get(ticket=ticket)
                    if deals:
                        pnl = sum(d.profit for d in deals)
                except Exception:
                    pass

            self.risk.record_trade_result(pnl, pnl / self.risk.balance if self.risk.balance > 0 else 0)

            # Phase 4: Track trade result for dynamic Kelly
            self._trade_results.append(pnl)
            if len(self._trade_results) > 50:
                self._trade_results = self._trade_results[-50:]

            # Strategy Profile Performance Tracking
            profile = pos.get("strategy_profile", "conservative")
            if profile in self._profile_performance:
                self._profile_performance[profile]["trades"] += 1
                self._profile_performance[profile]["total_pnl"] += pnl
                if pnl > 0:
                    self._profile_performance[profile]["wins"] += 1
                # Log profile performance
                pp = self._profile_performance[profile]
                wr = pp["wins"] / pp["trades"] * 100 if pp["trades"] > 0 else 0
                log.info(f"  PROFILE {profile}: {pp['trades']} trades, {pp['wins']} wins ({wr:.0f}%), "
                         f"P&L=${pp['total_pnl']:+.2f}")

            # Phase 5: Update win/loss streaks
            self._update_streaks(pnl)

            # Phase 2: ML Live Learning — record trade features for retraining
            indicators = pos.get("indicators", {})
            if indicators:
                self._record_trade_for_ml(
                    symbol=symbol,
                    action=pos.get("action", "?"),
                    indicators=indicators,
                    confidence=pos.get("confidence", 0.5),
                    pnl=pnl,
                    entry_price=pos.get("entry_price", 0),
                    exit_price=pos.get("current_price", pos.get("entry_price", 0)),
                    atr=pos.get("atr", 0),
                )

            del self.risk.open_positions[symbol]
            streak_info = f"W={self.consecutive_wins} L={self.consecutive_losses}"
            log.info(f"  CLOSED {symbol} | Reason: {reason} | P&L=${pnl:+.2f} | Streak: {streak_info}")
        else:
            log.error(f"  FAILED TO CLOSE {symbol} ticket={ticket}")

    def monitor_log(self, symbol: str, event: str, detail: str = ""):
        """Log a structured monitoring event."""
        import threading
        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "symbol": symbol,
            "event": event,
            "detail": detail,
            "cycle": self.cycle_count,
        }
        self.monitor_events.append(entry)
        if len(self.monitor_events) > self.monitor_max_events:
            self.monitor_events = self.monitor_events[-self.monitor_max_events:]

    def get_monitor(self) -> Dict:
        """Get monitoring pipeline state for the dashboard."""
        # Group events by symbol
        by_symbol = {}
        for ev in self.monitor_events:
            sym = ev["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(ev)

        # Last 5 events per symbol (most recent first)
        recent = {}
        for sym, events in by_symbol.items():
            recent[sym] = list(reversed(events[-5:]))

        # Pipeline summary: last signal, gate result, order result per symbol
        pipeline = {}
        for sym, events in by_symbol.items():
            last_signal = next((e for e in reversed(events) if e["event"] == "signal"), None)
            last_gate = next((e for e in reversed(events) if e["event"].startswith("gate_")), None)
            last_order = next((e for e in reversed(events) if e["event"] in ("order_placed", "order_failed", "order_closed")), None)
            pipeline[sym] = {
                "signal": last_signal,
                "gate": last_gate,
                "order": last_order,
            }

        # Overall stats
        signals = [e for e in self.monitor_events if e["event"] == "signal"]
        gates_passed = [e for e in self.monitor_events if e["event"] == "gate_all_passed"]
        orders_placed = [e for e in self.monitor_events if e["event"] == "order_placed"]
        orders_failed = [e for e in self.monitor_events if e["event"] == "order_failed"]

        return {
            "cycle": self.cycle_count,
            "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "total_events": len(self.monitor_events),
            "stats": {
                "signals_generated": len(signals),
                "gates_passed": len(gates_passed),
                "orders_placed": len(orders_placed),
                "orders_failed": len(orders_failed),
            },
            "pipeline": pipeline,
            "recent_events": list(reversed(self.monitor_events[-30:])),
        }

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
            # Phase 1A: Daily ROI Limits
            "daily_status": self.risk.get_daily_status(),
            # Phase 2: ML Live Learning
            "ml_learning": {
                "enabled": CONFIG.get("ml_live_learning_enabled", True),
                "training_samples": len(self._ml_training_data),
                "retrain_count": self._ml_retrain_count,
                "retrain_interval": CONFIG.get("ml_retrain_interval", 20),
                "next_retrain": max(0, CONFIG.get("ml_retrain_interval", 20) - len(self._ml_training_data)),
            },
            # Strategy Profiles
            "strategy_profiles": self._profile_performance,
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
                    import traceback
                    log.error(f"Engine error: {e}")
                    log.error(traceback.format_exc())
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


@app.get("/api/v1/daily-status")
def daily_status():
    """Get daily ROI limits, ML learning status, and extraction schedule."""
    daily = engine.risk.get_daily_status()
    extraction = engine.risk.check_weekly_extraction()
    ml_status = {
        "enabled": CONFIG.get("ml_live_learning_enabled", True),
        "training_samples": len(engine._ml_training_data),
        "retrain_count": engine._ml_retrain_count,
        "retrain_interval": CONFIG.get("ml_retrain_interval", 20),
        "next_retrain": max(0, CONFIG.get("ml_retrain_interval", 20) - len(engine._ml_training_data)),
    }
    return {
        "daily": daily,
        "extraction": extraction,
        "ml_learning": ml_status,
        "strategy_profiles": engine._profile_performance,
    }


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
        return {"token": token, "access_token": token, "token_type": "bearer", "user": username}

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
    mt5_positions = engine.mt5.get_positions()
    # Add scalper positions if available
    scalp_positions = []
    if getattr(engine, 'scalper', None):
        ss = engine.scalper.get_status()
        scalp_positions = ss.get("open_positions", [])
    return {
        "mt5": mt5_positions,
        "scalper": scalp_positions,
        "total": len(mt5_positions) + len(scalp_positions),
    }


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


@app.get("/api/v1/performance")
def performance():
    """Historical performance: trades, win rate, P&L, drawdown."""
    try:
        import MetaTrader5 as mt5
        # Get account info
        acct = mt5.account_info()
        # Get deals (closed trades) from last 30 days
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=30)
        deals = mt5.history_deals_get(start, end)
        if deals is None:
            deals = []
        
        # Calculate stats
        wins = 0
        losses = 0
        total_pnl = 0
        total_commission = 0
        total_swap = 0
        trade_history = []
        
        for deal in deals:
            if deal.type == mt5.DEAL_TYPE_BUY or deal.type == mt5.DEAL_TYPE_SELL:
                pnl = deal.profit + deal.swap + deal.commission
                total_pnl += pnl
                total_commission += deal.commission
                total_swap += deal.swap
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                trade_history.append({
                    "ticket": deal.ticket,
                    "time": deal.time.strftime("%Y-%m-%d %H:%M") if hasattr(deal.time, 'strftime') else str(deal.time),
                    "symbol": deal.symbol,
                    "type": "BUY" if deal.type == mt5.DEAL_TYPE_BUY else "SELL",
                    "volume": deal.volume,
                    "price": deal.price,
                    "pnl": round(pnl, 2),
                    "commission": round(deal.commission, 2),
                    "swap": round(deal.swap, 2),
                })
        
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "balance": round(acct.balance, 2) if acct else 0,
            "equity": round(acct.equity, 2) if acct else 0,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_commission": round(total_commission, 2),
            "total_swap": round(total_swap, 2),
            "avg_pnl": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            "trades": trade_history[-20:],  # Last 20 trades
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/v1/monitor")
def monitor():
    """Pipeline monitoring: signals, gates, orders — real-time view."""
    return engine.get_monitor()


@app.get("/api/v1/monitor/clear")
def monitor_clear():
    """Clear monitoring events."""
    engine.monitor_events = []
    return {"status": "cleared", "events": 0}


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
            "v3_symbol_configs": CONFIG.get("v3_symbol_configs", {}),
            "cycle_interval": CONFIG.get("cycle_interval", 300),
            "llm_enabled": CONFIG.get("llm_enabled", False),
            "ml_enabled": CONFIG.get("ml_enabled", False),
            "regime_enabled": CONFIG.get("regime_enabled", False),
            "calendar_enabled": CONFIG.get("calendar_enabled", False),
            "risk_parity_enabled": CONFIG.get("risk_parity_enabled", False),
            "multi_timeframe_enabled": CONFIG.get("multi_timeframe_enabled", False),
            "mtf_cascading_scalper_enabled": CONFIG.get("mtf_cascading_scalper_enabled", False),
            "hedging_enabled": CONFIG.get("hedging_enabled", False),
            "exit_model_enabled": CONFIG.get("exit_model_enabled", False),
            "equity_curve_ma_period": CONFIG.get("equity_curve_ma_period", 20),
        },
        "scalper": engine.scalper.get_status() if getattr(engine, 'scalper', None) else None,
        "phase4": {
            "equity_curve_len": len(getattr(engine, 'equity_curve', [])),
            "equity_curve_ma": round(sum(getattr(engine, 'equity_curve', [0])[-20:]) / max(1, len(getattr(engine, 'equity_curve', [0])[-20:])), 2) if getattr(engine, 'equity_curve', []) else 0,
            "kelly_fraction": round(getattr(engine, 'kelly_fraction', 0), 4),
            "trade_results_count": len(getattr(engine, '_trade_results', [])),
            "regime": getattr(getattr(engine, 'ensemble', None), 'current_regime', None) and str(getattr(engine.ensemble, 'current_regime', '')),
        },
        "phase5": {
            "win_streak": getattr(engine, 'consecutive_wins', 0),
            "loss_streak": getattr(engine, 'consecutive_losses', 0),
            "streak_multiplier": round(getattr(engine, '_get_streak_multiplier', lambda: 1.0)(), 2),
            "session_multiplier": round(getattr(engine, '_get_session_multiplier', lambda: 1.0)(), 2),
            "portfolio_heat": round(getattr(engine, '_check_portfolio_heat', lambda: 0.0)(), 3),
        },
    }


@app.get("/api/v1/scalper/status")
def scalper_status():
    """MTF Cascading Scalper status endpoint."""
    if not getattr(engine, 'scalper', None):
        return {"enabled": False, "open_scalps": 0, "total_trades": 0,
                "last_scan": None, "last_error": None, "symbol": None,
                "tp_pips": 0, "sl_pips": 0, "max_concurrent": 0, "groups": []}
    return engine.scalper.get_status()


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
            if price_data is not None and len(price_data) >= 20:
                # All legendary agents expect (data, symbol) — NOT (symbol, data)
                r = a.analyze(price_data, symbol)
                # Agents return dicts, not objects
                if isinstance(r, dict):
                    results.append({
                        "name": name,
                        "signal": r.get("signal", "HOLD"),
                        "confidence": round(float(r.get("confidence", 0)), 3),
                        "kelly_fraction": round(float(r.get("kelly_fraction", 0)), 3),
                        "reasoning": str(r.get("reasoning", ""))[:200],
                    })
                else:
                    results.append({"name": name, "signal": "HOLD", "confidence": 0, "kelly_fraction": 0, "reasoning": "invalid return type"})
            else:
                results.append({"name": name, "signal": "HOLD", "confidence": 0, "kelly_fraction": 0, "reasoning": "insufficient data"})
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
# DASHBOARD-API COMPAT — Endpoints the Next.js frontend expects
# ═══════════════════════════════════════════════════════════════

# --- Analysts list & individual analysis ---
ANALYST_NAMES = [
    "Market", "News", "Sentiment", "Technical", "Fundamentals",
    "Options", "OrderFlow", "Risk", "Macro", "OnChain", "Quant", "Compliance",
]

@app.get("/api/v1/analysts/")
def list_analysts():
    return {"analysts": ANALYST_NAMES, "total": len(ANALYST_NAMES)}


@app.get("/api/v1/analysts/{name}")
def get_analyst(name: str):
    for n in ANALYST_NAMES:
        if n.lower() == name.lower():
            return {"name": n, "capabilities": [f"Analyze {sym}" for sym in WATCHLIST[:5]]}
    raise HTTPException(status_code=404, detail=f"Analyst {name} not found")


@app.get("/api/v1/analysts/{name}/analyze")
def run_analyst(name: str, symbol: str = "EURUSD", timeframe: str = "H1"):
    """Run a single analyst on a symbol and return structured result."""
    if not ADVANCED_FEATURES_AVAILABLE:
        return _stub_analyst_result(name, symbol)
    analyst_map = {
        "Market": ("apps.analysts.market", "MarketAnalyst"),
        "News": ("apps.analysts.news", "NewsAnalyst"),
        "Sentiment": ("apps.analysts.sentiment", "SentimentAnalyst"),
        "Technical": ("apps.analysts.technical", "TechnicalAnalyst"),
        "Fundamentals": ("apps.analysts.fundamentals", "FundamentalsAnalyst"),
        "Options": ("apps.analysts.options", "OptionsAnalyst"),
        "OrderFlow": ("apps.analysts.order_flow", "OrderFlowAnalyst"),
        "Risk": ("apps.analysts.risk", "RiskAnalyst"),
        "Macro": ("apps.analysts.macro", "MacroAnalyst"),
        "OnChain": ("apps.analysts.on_chain", "OnChainAnalyst"),
        "Quant": ("apps.analysts.quant", "QuantAnalyst"),
        "Compliance": ("apps.analysts.compliance", "ComplianceAnalyst"),
    }
    key = name.capitalize()
    if key not in analyst_map:
        raise HTTPException(status_code=404, detail=f"Analyst {name} not found")
    try:
        mod_path, cls_name = analyst_map[key]
        import importlib
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        a = cls()
        import asyncio
        loop = asyncio.new_event_loop()
        r = loop.run_until_complete(a.analyze(symbol, timeframe))
        loop.close()
        return {
            "analyst_name": key,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": r.signal,
            "confidence": round(r.confidence, 3),
            "reasoning": r.reasoning[:500] if r.reasoning else "",
        }
    except Exception as e:
        return _stub_analyst_result(name, symbol, str(e))


def _stub_analyst_result(name: str, symbol: str, error: str = ""):
    return {
        "analyst_name": name,
        "symbol": symbol,
        "signal": "HOLD",
        "confidence": 0.0,
        "reasoning": error or "Analyst not available",
    }


# --- Consensus endpoints ---
@app.get("/api/v1/consensus/{symbol}")
def get_consensus(symbol: str, timeframe: str = "H1"):
    """Basic consensus for a symbol — aggregated from engine signals."""
    if symbol in engine.last_signals:
        sig = engine.last_signals[symbol]
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "action": sig.direction.value,
            "confidence": round(sig.confidence, 3),
            "score": sig.score,
            "votes": {"buy": 1 if sig.direction.value == "BUY" else 0,
                       "sell": 1 if sig.direction.value == "SELL" else 0,
                       "hold": 1 if sig.direction.value == "HOLD" else 0},
            "mtf_agreement": getattr(sig, 'mtf_agreement', False),
        }
    # Fallback: generate on-the-fly
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            action, conf, details = generate_signal(df.iloc[-1])
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "action": action,
                "confidence": round(conf, 3),
                "score": details.get("score", 0),
                "votes": {"buy": 1 if action == "BUY" else 0,
                           "sell": 1 if action == "SELL" else 0,
                           "hold": 1 if action == "HOLD" else 0},
                "mtf_agreement": False,
            }
    except Exception:
        pass
    return {"symbol": symbol, "timeframe": timeframe, "action": "HOLD",
            "confidence": 0, "score": 0,
            "votes": {"buy": 0, "sell": 0, "hold": 1}, "mtf_agreement": False}


@app.get("/api/v1/consensus/{symbol}/full")
def get_full_consensus(symbol: str, timeframe: str = "H1"):
    """Full consensus with debate, memory, gate status."""
    basic = get_consensus(symbol, timeframe)
    debate_data = None
    memory_data = []
    gate_status = {"ml_gate": True, "sentiment_gate": True, "regime_gate": True, "calendar_gate": True}
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates is not None:
            df = pd.DataFrame(rates)
            closes = df["close"].tolist()
            gate_status["volume_gate"] = float(df["tick_volume"].iloc[-1]) > 0 if "tick_volume" in df.columns else True
    except Exception:
        pass
    return {
        **basic,
        "debate": debate_data,
        "memory_situations": memory_data,
        "gate_status": gate_status,
    }


@app.get("/api/v1/consensus/{symbol}/debate")
def get_debate(symbol: str):
    """Bull vs Bear debate for a symbol."""
    # Reuse existing debate endpoint
    return {"winner": "NEUTRAL", "bull_confidence": 0.5, "bear_confidence": 0.5, "rounds": 0}


@app.get("/api/v1/consensus/{symbol}/memory")
def get_memory(symbol: str, timeframe: str = "H1"):
    """Memory recall for a symbol."""
    try:
        from apps.memory.situation_memory import FinancialSituationMemory
        mem = FinancialSituationMemory()
        situations = mem.retrieve(f"{symbol} trading situation", top_k=3)
        return {"symbol": symbol, "similar_situations": situations}
    except Exception:
        return {"symbol": symbol, "similar_situations": []}


# --- Scanner endpoint ---
@app.get("/api/v1/scanner/{symbol}")
def scan_symbol(symbol: str):
    """Multi-timeframe scan for a symbol."""
    timeframes = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}
    tf_results = {}
    for tf_name, tf_const in timeframes.items():
        try:
            rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 100)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                action, conf, details = generate_signal(df.iloc[-1])
                tf_results[tf_name] = {
                    "signal": action, "confidence": round(conf, 3),
                    "score": details.get("score", 0),
                }
            else:
                tf_results[tf_name] = {"signal": "HOLD", "confidence": 0, "score": 0}
        except Exception:
            tf_results[tf_name] = {"signal": "HOLD", "confidence": 0, "score": 0}
    return {"symbol": symbol, "timeframes": tf_results}


# --- Legendary strategy endpoints ---
@app.get("/api/v1/legendary/seykota/{symbol}")
def legendary_seykota(symbol: str):
    try:
        from apps.legendary.seykota import SeykotaTrendModule
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
        df = pd.DataFrame(rates) if rates is not None else None
        if df is None or len(df) < 50:
            return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "Insufficient data"}}
        a = SeykotaTrendModule()
        # SeykotaTrendModule uses analyze_trend(data) — no symbol param
        r = a.analyze_trend(df)
        # Returns dict
        if isinstance(r, dict):
            return {"symbol": symbol, "result": {"signal": r.get("signal", "HOLD"), "confidence": round(float(r.get("confidence", 0)), 3),
                    "reasoning": str(r.get("reasoning", ""))[:300]}}
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "Invalid return"}}
    except Exception as e:
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": str(e)[:200]}}


@app.get("/api/v1/legendary/turtle-soup/{symbol}")
def legendary_turtle_soup(symbol: str):
    try:
        from apps.legendary.turtle_soup import TurtleSoupModule
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
        df = pd.DataFrame(rates) if rates is not None else None
        if df is None or len(df) < 21:
            return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "Insufficient data"}}
        s = TurtleSoupModule()
        # TurtleSoupModule uses detect_false_breakout(data) — no symbol param
        r = s.detect_false_breakout(df)
        if r is None:
            return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "No false breakout detected"}}
        if isinstance(r, dict):
            return {"symbol": symbol, "result": {"signal": r.get("signal", "HOLD"), "confidence": round(float(r.get("confidence", 0)), 3),
                    "reasoning": str(r.get("reasoning", ""))[:300]}}
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "Invalid return"}}
    except Exception as e:
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": str(e)[:200]}}


@app.get("/api/v1/legendary/pyramiding/{symbol}")
def legendary_pyramiding(symbol: str):
    try:
        from apps.legendary.pyramiding import PyramidingLogic
        from apps.legendary.seykota import SeykotaTrendModule
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
        df = pd.DataFrame(rates) if rates is not None else None
        if df is None or len(df) < 50:
            return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "Insufficient data"}}
        # PyramidingLogic needs a position dict + market data
        # For API: return current pyramiding assessment
        s = PyramidingLogic()
        # Check if we have an open position for this symbol
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            pos = positions[0]
            position_dict = {
                "profit_pips": (pos.price_current - pos.price_open) / (0.0001 if "JPY" not in symbol else 0.01),
                "lot_size": pos.volume,
                "action": "BUY" if pos.type == 0 else "SELL",
                "entry_count": 1,
            }
            r = s.should_add_position(position_dict, df)
            if r and isinstance(r, dict):
                return {"symbol": symbol, "result": {"signal": r.get("signal", "HOLD"), "confidence": round(float(r.get("confidence", 0)), 3),
                        "reasoning": str(r.get("reasoning", ""))[:300]}}
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": "No open position to pyramid"}}
    except Exception as e:
        return {"symbol": symbol, "result": {"signal": "HOLD", "confidence": 0, "reasoning": str(e)[:200]}}


# --- Market endpoints ---
@app.get("/api/v1/market/{symbol}/price")
def market_price(symbol: str):
    """Get current price for a symbol (frontend format)."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    return {
        "symbol": symbol,
        "data": {"price": tick.bid, "bid": tick.bid, "ask": tick.ask,
                 "spread": round((tick.ask - tick.bid) * (10000 if "JPY" not in symbol else 100), 1),
                 "time": int(tick.time)},
    }


@app.get("/api/v1/market/{symbol}/analysis")
def market_analysis(symbol: str, timeframe: str = "H1"):
    """Get analysis for a symbol."""
    tf_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "15M": mt5.TIMEFRAME_M15, "15m": mt5.TIMEFRAME_M15,
              "1H": mt5.TIMEFRAME_H1, "H1": mt5.TIMEFRAME_H1, "4H": mt5.TIMEFRAME_H4, "H4": mt5.TIMEFRAME_H4,
              "1D": mt5.TIMEFRAME_D1, "D1": mt5.TIMEFRAME_D1}
    tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, 100)
    if rates is None or len(rates) == 0:
        return {"symbol": symbol, "timeframe": timeframe, "indicators": {}, "action": "HOLD", "confidence": 0}
    df = pd.DataFrame(rates)
    indicators = compute_indicators(df)
    action, conf, details = generate_signal(df.iloc[-1])
    return {
        "symbol": symbol, "timeframe": timeframe,
        "indicators": {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                       for k, v in details.items() if k != "reasons"},
        "action": action, "confidence": round(conf, 3),
        "reasons": details.get("reasons", []),
    }


# --- Trades endpoint ---
@app.get("/api/v1/trades/")
def list_trades():
    """List recent trades from MT5 history."""
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        deals = mt5.history_deals_get(start, now)
        if deals is None:
            return {"trades": [], "count": 0}
        trades = []
        for d in deals:
            trades.append({
                "id": str(d.ticket),
                "symbol": d.symbol,
                "action": "BUY" if d.type == 0 else "SELL" if d.type == 1 else str(d.type),
                "lots": d.volume,
                "entry_price": d.price,
                "status": "executed" if d.entry == 0 else "closed",
                "profit": d.profit,
                "time": str(d.time),
            })
        return {"trades": trades[:50], "count": len(trades)}
    except Exception as e:
        return {"trades": [], "count": 0, "error": str(e)}


@app.post("/api/v1/trades/")
def create_trade_endpoint(trade: dict):
    """Create a manual trade."""
    symbol = trade.get("symbol", "EURUSD")
    action = trade.get("action", "BUY")
    lots = float(trade.get("lots", 0.01))
    return manual_trade(symbol, action, lots)


# --- Paper trading endpoints ---
@app.get("/api/v1/paper-trades")
def paper_trades_list():
    return {"trades": [], "count": 0}


@app.get("/api/v1/paper-trades/stats")
def paper_trades_stats():
    return {"total_trades": 0, "buys": 0, "sells": 0, "holds": 0, "symbols": {}, "last_trade": None}


# --- Positions endpoint (with trailing slash) ---
@app.get("/api/v1/positions/")
def positions_list():
    """List open positions."""
    return {"positions": engine.mt5.get_positions()}


# --- Live trading control endpoints (frontend live-trading-card) ---
@app.get("/api/v1/live/setup")
def live_setup():
    """Check MT5 setup status."""
    import os as _os
    mt5_path = _os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
    installed = _os.path.exists(mt5_path)
    has_creds = bool(MT5_LOGIN and MT5_PASSWORD and MT5_SERVER)
    return {
        "installed": installed,
        "running": engine.mt5.connected,
        "connected": engine.mt5.connected,
        "path": mt5_path,
        "has_credentials": has_creds,
        "needs_setup": not installed or not has_creds,
        "setup_message": "Ready" if installed and has_creds else "Configure MT5 path and credentials in .env",
    }


@app.post("/api/v1/live/connect")
def live_connect(data: dict = None):
    """Connect to MT5 from the dashboard."""
    return mt5_connect(data)


@app.get("/api/v1/live/status")
def live_status():
    """Live trading status for the dashboard card."""
    acct = {}
    positions = []
    if engine.mt5.connected:
        try:
            info = mt5.account_info()
            if info:
                acct = {"login": info.login, "server": info.server, "name": info.name,
                        "balance": info.balance, "equity": info.equity, "margin": info.margin,
                        "margin_free": info.margin_free, "leverage": info.leverage,
                        "currency": info.currency, "profit": info.profit}
            pos = mt5.positions_get()
            if pos:
                positions = [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == 0 else "SELL",
                              "volume": p.volume, "price_open": p.price_open, "price_current": p.price_current,
                              "profit": p.profit, "sl": p.sl, "tp": p.tp} for p in pos]
        except Exception:
            pass
    return {
        "active": engine.running,
        "control": "RUNNING" if engine.running else "STOPPED",
        "state": {
            "balance": acct.get("balance", 0),
            "consecutive_losses": getattr(engine.risk, 'consecutive_losses', 0) if hasattr(engine.risk, 'consecutive_losses') else 0,
            "week_number": 1,
            "total_trades": engine.cycle_count,
            "wins": 0, "losses": 0, "total_pnl": acct.get("profit", 0),
            "active_improvements": {},
            "positions": {p["symbol"]: p for p in positions},
        },
        "mt5": {"installed": True, "running": engine.mt5.connected, "connected": engine.mt5.connected},
        "account": {**acct, "account_type": "Demo", "positions_count": len(positions),
                    "positions": positions, "recent_deals": []},
        "engine_pid": None,
    }


@app.get("/api/v1/live/mt5/status")
def live_mt5_status():
    """MT5 status — alias for mt5_status."""
    return mt5_status()


@app.get("/api/v1/live/account")
def live_account():
    """Account details for the dashboard."""
    return account_details()


@app.post("/api/v1/live/start")
def live_start():
    """Start the trading engine."""
    return start_engine()


@app.post("/api/v1/live/stop")
def live_stop():
    """Stop the trading engine."""
    return stop_engine()


@app.get("/api/v1/live/improvements")
def live_improvements():
    """List available improvements."""
    return {"improvements": [
        {"name": "Correlation Filter", "key": "correlation_filter", "enabled": True},
        {"name": "Dynamic Risk", "key": "dynamic_risk", "enabled": True},
        {"name": "Spread Filter", "key": "spread_filter", "enabled": True},
        {"name": "Risk Parity", "key": "risk_parity", "enabled": CONFIG.get("risk_parity_enabled", False)},
        {"name": "ML Prediction", "key": "ml_prediction", "enabled": CONFIG.get("ml_enabled", False)},
        {"name": "LLM Analysis", "key": "llm_analysis", "enabled": CONFIG.get("llm_enabled", False)},
        {"name": "Regime Detection", "key": "regime_detection", "enabled": CONFIG.get("regime_enabled", False)},
    ]}


@app.get("/api/v1/live/positions")
def live_positions():
    """Open positions for the dashboard."""
    positions = []
    if engine.mt5.connected:
        try:
            pos = mt5.positions_get()
            if pos:
                positions = [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == 0 else "SELL",
                              "volume": p.volume, "price_open": p.price_open, "price_current": p.price_current,
                              "profit": p.profit, "sl": p.sl, "tp": p.tp, "time": str(p.time)} for p in pos]
        except Exception:
            pass
    return {"positions": positions, "count": len(positions)}


@app.get("/api/v1/live/trades")
def live_trades():
    """Recent trades for the dashboard."""
    return list_trades()


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
    print(f"  Risk per trade: V3 per-symbol (2-3%)")
    print(f"  SL/TP: V3 per-symbol optimized configs")
    for sym, sc in CONFIG.get("v3_symbol_configs", {}).items():
        print(f"    {sym}: SL={sc['sl']}x TP={sc['tp']}x Trail={sc['trail']}x Risk={sc['risk']*100:.0f}%")
    print(f"  LLM: {'Enabled' if CONFIG['llm_enabled'] else 'Disabled'}")
    print(f"  ML: {'Enabled' if CONFIG['ml_enabled'] else 'Disabled'}")
    print(f"  API Server: http://localhost:8888")
    print("=" * 70)
    print("\n  Starting FastAPI server with embedded trading engine...\n")

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
