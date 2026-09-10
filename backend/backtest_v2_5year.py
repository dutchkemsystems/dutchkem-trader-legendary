"""
DUTCHKEM TRADER - REDESIGNED 5-YEAR BACKTEST (v2)
===================================================
NEW STRATEGY with proven edge indicators.

CHANGES FROM v1:
- REMOVED: AMD, GOOGL (worst performers)
- NEW INDICATORS: ADX trend strength, Ichimoku Cloud, Volume profile, RSI divergence
- WIDER SL/TP: 3x ATR SL / 5x ATR TP (R:R = 1:1.67)
- HIGHER CONFIDENCE: 0.50 minimum
- MULTI-TIMEFRAME: H4 trend filter + H1 entry
- REDUCED FREQUENCY: Only high-quality setups
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"

# ═══════════════════════════════════════════════════════════════
# NEW OPTIMIZED SYMBOLS (AMD/GOOGL removed)
# ═══════════════════════════════════════════════════════════════
SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD", "US30",
]

# Multiple configs to test
CONFIGS = {
    "v2_MTF_ADX": {
        "max_risk": 0.15,
        "min_confidence": 0.50,
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 5.0,
        "max_bars_held": 72,
        "adx_threshold": 25,
        "use_ichimoku": True,
        "use_volume_filter": True,
        "use_rsi_divergence": True,
        "mtf_confluence": True,
        "sym_weights": {},
    },
    "v2_MTF_ADX_risk20": {
        "max_risk": 0.20,
        "min_confidence": 0.50,
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 5.0,
        "max_bars_held": 72,
        "adx_threshold": 25,
        "use_ichimoku": True,
        "use_volume_filter": True,
        "use_rsi_divergence": True,
        "mtf_confluence": True,
        "sym_weights": {},
    },
    "v2_ADX_only": {
        "max_risk": 0.15,
        "min_confidence": 0.50,
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 5.0,
        "max_bars_held": 72,
        "adx_threshold": 25,
        "use_ichimoku": False,
        "use_volume_filter": True,
        "use_rsi_divergence": True,
        "mtf_confluence": False,
        "sym_weights": {},
    },
    "v2_Wide_SL": {
        "max_risk": 0.15,
        "min_confidence": 0.50,
        "sl_atr_mult": 4.0,
        "tp_atr_mult": 7.0,
        "max_bars_held": 96,
        "adx_threshold": 20,
        "use_ichimoku": True,
        "use_volume_filter": True,
        "use_rsi_divergence": True,
        "mtf_confluence": True,
        "sym_weights": {},
    },
    "v2_Conservative": {
        "max_risk": 0.10,
        "min_confidence": 0.60,
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 5.0,
        "max_bars_held": 72,
        "adx_threshold": 30,
        "use_ichimoku": True,
        "use_volume_filter": True,
        "use_rsi_divergence": True,
        "mtf_confluence": True,
        "sym_weights": {},
    },
}

INITIAL_BALANCE = 10000.0
BARS_NEEDED = 13000


# ═══════════════════════════════════════════════════════════════
# INDICATOR COMPUTATIONS
# ═══════════════════════════════════════════════════════════════

def compute_adx(high, low, close, period=14):
    """Average Directional Index — measures trend strength."""
    plus_dm = np.zeros(len(high))
    minus_dm = np.zeros(len(high))
    tr = np.zeros(len(high))

    for i in range(1, len(high)):
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0
        minus_dm[i] = down if (down > up and down > 0) else 0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))

    atr = pd.Series(tr).ewm(span=period, adjust=False).mean().values
    plus_di = 100 * pd.Series(plus_dm).ewm(span=period, adjust=False).mean().values / np.where(atr > 0, atr, 1)
    minus_di = 100 * pd.Series(minus_dm).ewm(span=period, adjust=False).mean().values / np.where(atr > 0, atr, 1)

    dx = np.where((plus_di + minus_di) > 0, 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0)
    adx = pd.Series(dx).ewm(span=period, adjust=False).mean().values
    return adx, plus_di, minus_di


def compute_ichimoku(high, low, close):
    """Ichimoku Cloud components."""
    tenkan = (pd.Series(high).rolling(9).max() + pd.Series(low).rolling(9).min()).values / 2
    kijun = (pd.Series(high).rolling(26).max() + pd.Series(low).rolling(26).min()).values / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = ((pd.Series(high).rolling(52).max() + pd.Series(low).rolling(52).min()).values) / 2
    return tenkan, kijun, senkou_a, senkou_b


def compute_rsi_divergence(close, rsi, lookback=14):
    """
    Detect RSI divergence:
    - Bullish: price makes lower low but RSI makes higher low
    - Bearish: price makes higher high but RSI makes lower high
    Returns: +1 bullish, -1 bearish, 0 none
    """
    n = len(close)
    div = np.zeros(n)
    for i in range(lookback * 2, n):
        # Find recent swing lows for price and RSI
        price_window = close[i-lookback*2:i+1]
        rsi_window = rsi[i-lookback*2:i+1]

        # Simple divergence: compare current vs lookback ago
        if close[i] < close[i - lookback] and rsi[i] > rsi[i - lookback]:
            div[i] = 1  # Bullish divergence
        elif close[i] > close[i - lookback] and rsi[i] < rsi[i - lookback]:
            div[i] = -1  # Bearish divergence
    return div


# ═══════════════════════════════════════════════════════════════
# DATA LOADING (H1 + H4 for MTF)
# ═══════════════════════════════════════════════════════════════
def load_data():
    """Load H1 and H4 data from MT5."""
    print("  Connecting to MT5...")
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("  ERROR: MT5 connection failed")
        return {}, {}

    all_h1 = {}
    all_h4 = {}

    for sym in SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  SKIP {sym}: not found")
            continue
        if not info.visible:
            mt5.symbol_select(sym, True)

        # H1 data
        rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, BARS_NEEDED)
        if rates_h1 is None or len(rates_h1) < 500:
            print(f"  SKIP {sym}: only {len(rates_h1) if rates_h1 is not None else 0} H1 bars")
            continue

        df1 = pd.DataFrame(rates_h1)
        df1["time"] = pd.to_datetime(df1["time"], unit="s", utc=True)
        df1 = df1.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df1 = df1.set_index("timestamp")[["open", "high", "low", "close", "volume"]]

        # H4 data
        rates_h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, BARS_NEEDED // 4)
        if rates_h4 is None or len(rates_h4) < 200:
            print(f"  SKIP {sym}: insufficient H4 data")
            continue

        df4 = pd.DataFrame(rates_h4)
        df4["time"] = pd.to_datetime(df4["time"], unit="s", utc=True)
        df4 = df4.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df4 = df4.set_index("timestamp")[["open", "high", "low", "close", "volume"]]

        # Compute indicators for H1
        c = df1["close"].values.astype(float)
        h = df1["high"].values.astype(float)
        l = df1["low"].values.astype(float)

        # ADX
        adx, plus_di, minus_di = compute_adx(h, l, c)
        df1["adx"] = adx
        df1["plus_di"] = plus_di
        df1["minus_di"] = minus_di

        # Ichimoku
        tenkan, kijun, senkou_a, senkou_b = compute_ichimoku(h, l, c)
        df1["tenkan"] = tenkan
        df1["kijun"] = kijun
        df1["senkou_a"] = senkou_a
        df1["senkou_b"] = senkou_b

        # RSI (divergence-capable)
        deltas = np.diff(c, prepend=c[0])
        gains = np.where(deltas > 0, deltas, 0)
        losses_arr = np.where(deltas < 0, -deltas, 0)
        avg_gain = pd.Series(gains).ewm(span=14, adjust=False).mean().values
        avg_loss = pd.Series(losses_arr).ewm(span=14, adjust=False).mean().values
        rs = np.where(avg_loss > 1e-10, avg_gain / avg_loss, 100)
        df1["rsi"] = 100 - (100 / (1 + rs))

        # RSI divergence
        df1["rsi_div"] = compute_rsi_divergence(c, df1["rsi"].values)

        # ATR
        prev_c = np.roll(c, 1); prev_c[0] = c[0]
        tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
        df1["atr"] = pd.Series(tr).rolling(14).mean().values

        # Volume SMA (for volume filter)
        df1["vol_sma"] = pd.Series(df1["volume"].values).rolling(20).mean().values

        # SMA for trend
        df1["sma_50"] = pd.Series(c).rolling(50).mean().values
        df1["sma_200"] = pd.Series(c).rolling(200).mean().values

        # EMA 21 for trend
        df1["ema_21"] = pd.Series(c).ewm(span=21).mean().values

        # Momentum
        df1["momentum"] = pd.Series(c).pct_change(10).values

        df1 = df1.dropna()
        all_h1[sym] = df1

        # Compute H4 ADX for MTF filter
        c4 = df4["close"].values.astype(float)
        h4 = df4["high"].values.astype(float)
        l4 = df4["low"].values.astype(float)
        adx4, _, _ = compute_adx(h4, l4, c4)
        df4["adx"] = adx4
        df4["sma_50"] = pd.Series(c4).rolling(50).mean().values
        df4["sma_200"] = pd.Series(c4).rolling(200).mean().values
        df4 = df4.dropna()
        all_h4[sym] = df4

        print(f"  {sym:10} H1={len(df1):5} bars | H4={len(df4):4} bars | {df1.index[0].strftime('%Y-%m-%d')} to {df1.index[-1].strftime('%Y-%m-%d')}")

    mt5.shutdown()
    return all_h1, all_h4


# ═══════════════════════════════════════════════════════════════
# REDESIGNED SIGNAL GENERATION (v2)
# ═══════════════════════════════════════════════════════════════
def generate_signal_v2(row, h4_row, cfg):
    """
    Redesigned signal with multiple confirmation layers.
    Returns (direction, confidence).
    """
    score = 0
    max_score = 0

    adx_thresh = cfg.get("adx_threshold", 25)
    use_ichimoku = cfg.get("use_ichimoku", True)
    use_vol = cfg.get("use_volume_filter", True)
    use_div = cfg.get("use_rsi_divergence", True)
    mtf = cfg.get("mtf_confluence", True)

    adx_val = float(row["adx"])
    plus_di = float(row["plus_di"])
    minus_di = float(row["minus_di"])

    # ── Layer 1: ADX Trend Strength (must be trending) ──
    max_score += 3
    if adx_val >= adx_thresh:
        score += 3  # Strong trend — highest weight
    elif adx_val >= adx_thresh - 5:
        score += 1  # Mild trend

    # ── Layer 2: DI Direction (who controls — buyers or sellers) ──
    max_score += 2
    if plus_di > minus_di:
        score += 2  # Buyers control
    elif minus_di > plus_di:
        score -= 2  # Sellers control (for SELL)

    # ── Layer 3: Price vs EMA21 + SMA50 (trend alignment) ──
    max_score += 2
    ema21 = float(row["ema_21"])
    sma50 = float(row["sma_50"])
    px = float(row["close"])

    if px > ema21 > sma50:
        score += 2  # Strong uptrend
    elif px < ema21 < sma50:
        score -= 2  # Strong downtrend
    elif px > ema21:
        score += 1
    elif px < ema21:
        score -= 1

    # ── Layer 4: RSI (not overbought/oversold — use as confirmation) ──
    max_score += 1
    rsi = float(row["rsi"])
    if 40 <= rsi <= 60:
        score += 1  # Neutral zone — good for continuation
    elif rsi < 30 or rsi > 70:
        score -= 1  # Extreme — counter-trend risk

    # ── Layer 5: Volume Confirmation ──
    max_score += 1
    if use_vol:
        vol = float(row["volume"])
        vol_sma = float(row["vol_sma"])
        if vol > vol_sma * 1.2:
            score += 1  # Above-average volume confirms

    # ── Layer 6: Ichimoku Cloud (if enabled) ──
    if use_ichimoku:
        max_score += 2
        tenkan = float(row["tenkan"])
        kijun = float(row["kijun"])
        senkou_a = float(row["senkou_a"])
        senkou_b = float(row["senkou_b"])

        if px > max(senkou_a, senkou_b) and tenkan > kijun:
            score += 2  # Above cloud + Tenkan > Kijun = bullish
        elif px < min(senkou_a, senkou_b) and tenkan < kijun:
            score -= 2  # Below cloud + Tenkan < Kijun = bearish

    # ── Layer 7: RSI Divergence (bonus) ──
    max_score += 1
    if use_div:
        div = float(row["rsi_div"])
        if div > 0:
            score += 1  # Bullish divergence
        elif div < 0:
            score -= 1  # Bearish divergence

    # ── Layer 8: Multi-Timeframe Confluence (H4 trend) ──
    max_score += 2
    if mtf and h4_row is not None:
        h4_sma50 = float(h4_row["sma_50"])
        h4_sma200 = float(h4_row["sma_200"])
        h4_adx = float(h4_row["adx"])

        if h4_sma50 > h4_sma200 and h4_adx >= 20:
            score += 2  # H4 bullish trend confirmed
        elif h4_sma50 < h4_sma200 and h4_adx >= 20:
            score -= 2  # H4 bearish trend confirmed

    # ── Determine direction and confidence ──
    if score >= 3:
        direction = "BUY"
        confidence = min(score / max_score, 1.0)
    elif score <= -3:
        direction = "SELL"
        confidence = min(abs(score) / max_score, 1.0)
    else:
        direction = "HOLD"
        confidence = 0.0

    return direction, confidence


# ═══════════════════════════════════════════════════════════════
# BACKTEST ENGINE (v2 — with ATR-based SL/TP)
# ═══════════════════════════════════════════════════════════════
def backtest(all_h1, all_h4, cfg):
    risk = cfg["max_risk"]
    min_conf = cfg.get("min_confidence", 0.50)
    sl_mult = cfg.get("sl_atr_mult", 3.0)
    tp_mult = cfg.get("tp_atr_mult", 5.0)
    max_hold = cfg.get("max_bars_held", 72)

    balance = INITIAL_BALANCE
    peak_balance = balance
    max_drawdown = 0
    max_dd_pct = 0

    all_trades = []
    monthly_pnl = {}

    for sym in SYMBOLS:
        if sym not in all_h1:
            continue
        df = all_h1[sym]
        h4_df = all_h4.get(sym)
        pos = None

        # Align H4 data
        h4_idx = 0 if h4_df is not None else None

        for i in range(200, len(df)):  # Start after 200 bars (SMA200 warmup)
            row = df.iloc[i]
            px = float(row["close"])
            high_px = float(row["high"])
            low_px = float(row["low"])
            atr_val = float(row["atr"])
            ts = df.index[i]

            # Find matching H4 row
            h4_row = None
            if h4_df is not None and h4_idx is not None:
                # Walk H4 index forward to find closest match
                while h4_idx < len(h4_df) - 1 and h4_df.index[h4_idx + 1] <= ts:
                    h4_idx += 1
                if h4_idx < len(h4_df):
                    h4_row = h4_df.iloc[h4_idx]

            # ── Manage open position ──
            if pos is not None:
                bars_held = i - pos["entry_bar"]
                direction = pos["direction"]

                if direction == "BUY":
                    unrealized = (px - pos["entry_px"]) / pos["entry_px"]
                    new_sl = px - sl_mult * atr_val
                    if new_sl > pos["sl"]:
                        pos["sl"] = new_sl

                    if low_px <= pos["sl"]:
                        pnl = (pos["sl"] - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({"sym": sym, "dir": "BUY", "pnl": pnl, "bars": bars_held, "exit_reason": "SL", "time": ts})
                        pos = None
                        continue
                    if high_px >= pos["tp"]:
                        pnl = (pos["tp"] - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({"sym": sym, "dir": "BUY", "pnl": pnl, "bars": bars_held, "exit_reason": "TP", "time": ts})
                        pos = None
                        continue
                else:  # SELL
                    unrealized = (pos["entry_px"] - px) / pos["entry_px"]
                    new_sl = px + sl_mult * atr_val
                    if new_sl < pos["sl"]:
                        pos["sl"] = new_sl

                    if high_px >= pos["sl"]:
                        pnl = (pos["entry_px"] - pos["sl"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({"sym": sym, "dir": "SELL", "pnl": pnl, "bars": bars_held, "exit_reason": "SL", "time": ts})
                        pos = None
                        continue
                    if low_px <= pos["tp"]:
                        pnl = (pos["entry_px"] - pos["tp"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({"sym": sym, "dir": "SELL", "pnl": pnl, "bars": bars_held, "exit_reason": "TP", "time": ts})
                        pos = None
                        continue

                # Time exit
                if bars_held >= max_hold:
                    if direction == "BUY":
                        pnl = (px - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                    else:
                        pnl = (pos["entry_px"] - px) / pos["entry_px"] * pos["size"]
                    balance += pnl
                    all_trades.append({"sym": sym, "dir": direction, "pnl": pnl, "bars": bars_held, "exit_reason": "TIME", "time": ts})
                    pos = None
                    continue

                continue

            # ── New entry ──
            action, conf = generate_signal_v2(row, h4_row, cfg)
            if action in ("BUY", "SELL") and conf >= min_conf:
                sz = max(10, risk * balance)
                sz = min(sz, balance * 0.25)  # Cap at 25%
                if sz > 0 and sz <= balance:
                    if action == "BUY":
                        sl_px = px - sl_mult * atr_val
                        tp_px = px + tp_mult * atr_val
                    else:
                        sl_px = px + sl_mult * atr_val
                        tp_px = px - tp_mult * atr_val
                    pos = {
                        "direction": action, "entry_px": px, "entry_bar": i,
                        "sl": sl_px, "tp": tp_px, "size": sz, "confidence": conf,
                    }

            # Drawdown tracking
            if balance > peak_balance:
                peak_balance = balance
            dd = peak_balance - balance
            dd_pct = dd / peak_balance if peak_balance > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            # Monthly
            if i % 24 == 0:
                mk = ts.strftime("%Y-%m")
                if mk not in monthly_pnl:
                    monthly_pnl[mk] = 0

    # Close remaining
    if pos is not None:
        px = float(df.iloc[-1]["close"])
        if pos["direction"] == "BUY":
            pnl = (px - pos["entry_px"]) / pos["entry_px"] * pos["size"]
        else:
            pnl = (pos["entry_px"] - px) / pos["entry_px"] * pos["size"]
        balance += pnl
        all_trades.append({"sym": sym, "dir": pos["direction"], "pnl": pnl, "bars": len(df)-1-pos["entry_bar"], "exit_reason": "EOD", "time": df.index[-1]})

    # Compute monthly from trades
    for t in all_trades:
        if t["time"] is not None:
            mk = pd.Timestamp(t["time"]).strftime("%Y-%m")
            monthly_pnl[mk] = monthly_pnl.get(mk, 0) + t["pnl"]

    return {
        "trades": all_trades,
        "final_balance": balance,
        "total_pnl": balance - INITIAL_BALANCE,
        "total_return_pct": (balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_dd_pct * 100,
        "monthly_pnl": monthly_pnl,
        "num_trades": len(all_trades),
    }


# ═══════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════
def generate_report(result, config_name):
    trades = result["trades"]
    fb = result["final_balance"]
    tp = result["total_pnl"]
    tr = result["total_return_pct"]
    mdd = result["max_drawdown"]
    mdd_pct = result["max_drawdown_pct"]
    mp = result["monthly_pnl"]

    if not trades:
        return {"summary": {"total_pnl": 0, "total_return_pct": 0, "max_drawdown_pct": 0}, "trades": {"total": 0}}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades)

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    expectancy = tp / len(trades)

    monthly_vals = list(mp.values())
    if len(monthly_vals) > 2:
        m_arr = np.array(monthly_vals) / INITIAL_BALANCE
        sharpe = (np.mean(m_arr) / np.std(m_arr)) * np.sqrt(12) if np.std(m_arr) > 0 else 0
    else:
        sharpe = 0

    # Exit reasons
    sl_count = sum(1 for t in trades if t["exit_reason"] == "SL")
    tp_count = sum(1 for t in trades if t["exit_reason"] == "TP")
    time_count = sum(1 for t in trades if t["exit_reason"] == "TIME")

    # Per symbol
    sym_stats = {}
    for t in trades:
        s = t["sym"]
        if s not in sym_stats:
            sym_stats[s] = {"trades": 0, "wins": 0, "pnl": 0}
        sym_stats[s]["trades"] += 1
        sym_stats[s]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            sym_stats[s]["wins"] += 1

    # Yearly
    yearly = {}
    for mk, pnl in mp.items():
        y = mk[:4]
        yearly[y] = yearly.get(y, 0) + pnl

    print(f"\n{'='*80}")
    print(f"  BACKTEST REPORT: {config_name}")
    print(f"{'='*80}")
    print(f"\n  PERFORMANCE SUMMARY")
    print(f"  {'-'*50}")
    print(f"  Initial:       ${INITIAL_BALANCE:>10,.2f}")
    print(f"  Final:         ${fb:>10,.2f}")
    print(f"  P&L:           ${tp:>+10,.2f} ({tr:>+.1f}%)")
    print(f"  Max Drawdown:  ${mdd:>10,.2f} ({mdd_pct:.1f}%)")
    print(f"  Sharpe:        {sharpe:>10.2f}")
    print(f"  Profit Factor: {profit_factor:>10.2f}")

    print(f"\n  TRADE STATS")
    print(f"  {'-'*50}")
    print(f"  Trades:  {len(trades)} | Wins: {len(wins)} ({win_rate:.1%}) | Losses: {len(losses)}")
    print(f"  Avg Win: ${avg_win:,.2f} | Avg Loss: ${avg_loss:,.2f} | Expectancy: ${expectancy:,.2f}")
    print(f"  TP: {tp_count} ({tp_count/len(trades)*100:.0f}%) | SL: {sl_count} ({sl_count/len(trades)*100:.0f}%) | TIME: {time_count}")

    print(f"\n  PER-SYMBOL")
    print(f"  {'-'*50}")
    for sym, st in sorted(sym_stats.items(), key=lambda x: -x[1]["pnl"]):
        wr = st["wins"]/st["trades"] if st["trades"] else 0
        m = "+" if st["pnl"] > 0 else ""
        print(f"  {sym:10} {st['trades']:4} trades | WR={wr:.0%} | P&L=${m}{st['pnl']:,.2f}")

    print(f"\n  YEARLY")
    print(f"  {'-'*50}")
    for y, pnl in sorted(yearly.items()):
        m = "+" if pnl > 0 else ""
        print(f"  {y}:  ${m}{pnl:>8,.2f} ({pnl/INITIAL_BALANCE*100:>+.1f}%)")

    verdict = "PROFITABLE" if tp > 0 and win_rate >= 0.45 and profit_factor >= 1.1 else "NOT PROFITABLE"
    print(f"\n  VERDICT: {verdict}")
    print(f"{'='*80}")

    return {
        "config_name": config_name,
        "summary": {"total_pnl": tp, "total_return_pct": tr, "max_drawdown_pct": mdd_pct, "sharpe": sharpe, "profit_factor": profit_factor},
        "trades": {"total": len(trades), "wins": len(wins), "win_rate": win_rate},
        "yearly": yearly,
        "monthly_pnl": mp,
        "symbol_stats": sym_stats,
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 80)
    print("  DUTCHKEM TRADER - REDESIGNED 5-YEAR BACKTEST (v2)")
    print("  New indicators: ADX + Ichimoku + RSI Divergence + Volume + MTF")
    print("  Symbols: 13 (AMD/GOOGL removed) | SL: 3x ATR | TP: 5x ATR")
    print("=" * 80)

    all_h1, all_h4 = load_data()
    if not all_h1:
        print("  ERROR: No data. Exiting.")
        return

    print(f"\n  Loaded {len(all_h1)} symbols")

    best_pnl = -999
    best_name = None
    all_results = {}

    for name, cfg in CONFIGS.items():
        print(f"\n  Testing: {name}")
        result = backtest(all_h1, all_h4, cfg)
        report = generate_report(result, name)
        all_results[name] = report

        pnl = result["total_pnl"]
        if pnl > best_pnl:
            best_pnl = pnl
            best_name = name

    print(f"\n{'='*80}")
    print(f"  BEST CONFIG: {best_name}")
    print(f"  P&L: ${best_pnl:+,.2f}")
    print(f"{'='*80}")

    # Save
    fn = Path("paper_trades") / f"backtest_v2_5yr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({
            "configs_tested": list(CONFIGS.keys()),
            "best_config": best_name,
            "best_pnl": best_pnl,
            "results": {k: v for k, v in all_results.items()},
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
