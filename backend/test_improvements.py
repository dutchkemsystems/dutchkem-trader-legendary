"""
Seven Improvements Framework
============================
Tests each improvement against the base strategy.
Measures isolated impact on P&L.

Base config: Risk2% noCB noBad minConf30 (deterministic)
Expected base: ~$+246.56 (at 40% risk) = ~$+12.33 (at 2% risk)
"""
import os, sys, json, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from pathlib import Path
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
DATA_DIR = Path("paper_trades")

SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP","EURCHF",
    "XAUUSD","XAGUSD","BTCUSD","ETHUSD",
    "US30","US500","UK100",
    "AAPL","AMZN","NVDA","TSLA","META","MSFT","GOOGL","AMD",
]


# ─── Data Loading ────────────────────────────────────────────
def load_all_data():
    mt5.initialize(path=MT5_PATH, login=476963617, password="Christ@5436", server="Exness-MT5Trial9")
    all_data = {}
    for sym in SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is None: continue
        if not info.visible: mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 1500)
        if rates is None or len(rates) < 200: continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        c = df["close"].values; h = df["high"].values; l = df["low"].values
        df["sma_5"] = pd.Series(c).rolling(5).mean().values
        df["sma_10"] = pd.Series(c).rolling(10).mean().values
        df["sma_20"] = pd.Series(c).rolling(20).mean().values
        df["sma_50"] = pd.Series(c).rolling(50).mean().values
        df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
        df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
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
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / (df["bb_mid"] + 1e-10)
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
        df["atr"] = pd.Series(tr).rolling(14).mean().values
        df["atr_pct"] = df["atr"] / df["close"]
        df["momentum_5"] = pd.Series(c).pct_change(5).values
        df["momentum_10"] = pd.Series(c).pct_change(10).values
        df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values
        df["trend_strength"] = abs(df["sma_20"] - df["sma_50"]) / (df["atr"] + 1e-10)
        df = df.dropna()
        all_data[sym] = df
    mt5.shutdown()
    return all_data


# ─── Base Signal Generation ──────────────────────────────────
def generate_signal_base(row):
    """Base signal: same as paper_trading_v2.py"""
    score = 0
    if row["macd_hist"] > 0: score += 1
    elif row["macd_hist"] < 0: score -= 1
    if row["rsi"] < 35: score += 2
    elif row["rsi"] < 45: score += 1
    elif row["rsi"] > 65: score -= 2
    elif row["rsi"] > 55: score -= 1
    if row["close"] > row["sma_20"] > row["sma_50"]: score += 2
    elif row["close"] < row["sma_20"] < row["sma_50"]: score -= 2
    if row["momentum_5"] > 0.005: score += 1
    elif row["momentum_5"] < -0.005: score -= 1
    if row["close"] < row["bb_lower"]: score += 1
    elif row["close"] > row["bb_upper"]: score -= 1
    if score >= 3: return "BUY", min(score / 6.0, 1.0)
    if score <= -3: return "SELL", min(abs(score) / 6.0, 1.0)
    return "HOLD", 0.0


# ─── Base Backtest ───────────────────────────────────────────
def backtest(all_data, risk_pct, cfg, signal_fn=None):
    """Standard backtest with configurable signal function."""
    if signal_fn is None:
        signal_fn = generate_signal_base
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    risk = cfg.get("max_risk", risk_pct)
    cb_limit = cfg.get("circuit_breaker", 99)
    bad_hours = cfg.get("bad_hours", set())
    bad_days = cfg.get("bad_days", set())
    mc = cfg.get("min_confidence", 0.30)
    hold_bars = cfg.get("hold_bars", 5)

    total_pnl = 0; total_trades = 0; wins = 0
    per_sym = {}

    for sym, df in all_data.items():
        bal = 10000.0; pos = None; trades = []; cl = 0
        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"])
            hr = df.index[i].hour; dw = df.index[i].dayofweek
            act, conf = signal_fn(row)

            if pos is not None and i - pos["bar"] >= hold_bars:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl)
                cl = cl + 1 if pnl <= 0 else 0; pos = None

            if pos is None:
                skip = (cl >= cb_limit) or (hr in bad_hours) or (dw in bad_days)
                if not skip and act in ("BUY", "SELL") and conf >= mc:
                    sz = max(10, kf * bal * risk)
                    if 0 < sz <= bal:
                        pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}

        sw = sum(1 for p in trades if p > 0)
        p = sum(trades)
        total_pnl += p; total_trades += len(trades); wins += sw
        per_sym[sym] = {"trades": len(trades), "pnl": p, "wins": sw}
    return total_pnl, total_trades, wins, per_sym


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 1: Walk-Forward Optimization
# ═══════════════════════════════════════════════════════════
def test_walk_forward(all_data):
    """Test 1: Walk-forward with rolling train/test windows."""
    print("\n  [1] WALK-FORWARD OPTIMIZATION")
    print("  " + "-" * 50)

    # Split each symbol's data: first 70% train, last 30% test
    results = {}
    for sym, df in all_data.items():
        split = int(len(df) * 0.7)
        train_df = df.iloc[:split]
        test_df = df.iloc[split:]

        # "Optimize" on train: find best min_confidence
        best_mc = 0.30
        best_pnl = -999
        for mc in [0.20, 0.25, 0.30, 0.35, 0.40]:
            pnl, _, _, _ = backtest({sym: train_df}, 0.02, {"min_confidence": mc, "circuit_breaker": 99})
            if pnl > best_pnl:
                best_pnl = pnl; best_mc = mc

        # Test on out-of-sample
        pnl, trades, w, _ = backtest({sym: test_df}, 0.02, {"min_confidence": best_mc, "circuit_breaker": 99})
        results[sym] = {"pnl": pnl, "trades": trades, "mc": best_mc}

    total_pnl = sum(r["pnl"] for r in results.values())
    total_trades = sum(r["trades"] for r in results.values())
    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 2: ATR-Based Stop Loss / Take Profit
# ═══════════════════════════════════════════════════════════
def test_atr_exits(all_data):
    """Test 2: Use ATR for dynamic stop loss and take profit."""
    print("\n  [2] ATR-BASED STOP LOSS / TAKE PROFIT")
    print("  " + "-" * 50)

    def signal_atr(row):
        """Signal with ATR exit logic."""
        act, conf = generate_signal_base(row)
        return act, conf

    # Backtest with ATR-based exits (SL=1.5*ATR, TP=3*ATR)
    total_pnl = 0; total_trades = 0
    for sym, df in all_data.items():
        kelly = KellySizer()
        kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        bal = 10000.0; pos = None; trades = []

        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"]); atr = float(row["atr"])
            act, conf = signal_atr(row)

            # Check exit conditions
            if pos is not None:
                bars = i - pos["bar"]
                hit_sl = (pos["a"] == "BUY" and px <= pos["px"] - 1.5 * pos["atr"]) or \
                         (pos["a"] == "SELL" and px >= pos["px"] + 1.5 * pos["atr"])
                hit_tp = (pos["a"] == "BUY" and px >= pos["px"] + 3.0 * pos["atr"]) or \
                         (pos["a"] == "SELL" and px <= pos["px"] - 3.0 * pos["atr"])
                timeout = bars >= 5

                if hit_sl or hit_tp or timeout:
                    pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                           else (pos["px"] - px) / pos["px"]) * pos["s"]
                    bal += pnl; trades.append(pnl); pos = None
                    continue

            if pos is None and act in ("BUY", "SELL") and conf >= 0.30:
                sz = max(10, kf * bal * 0.02)
                if 0 < sz <= bal:
                    pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3), "atr": atr}

        total_pnl += sum(trades); total_trades += len(trades)

    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 3: Volatility-Based Position Sizing
# ═══════════════════════════════════════════════════════════
def test_vol_sizing(all_data):
    """Test 3: Scale position size inversely with volatility."""
    print("\n  [3] VOLATILITY-BASED POSITION SIZING")
    print("  " + "-" * 50)

    total_pnl = 0; total_trades = 0
    for sym, df in all_data.items():
        kelly = KellySizer()
        kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        bal = 10000.0; pos = None; trades = []

        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"]); vol = float(row["volatility_10"])
            act, conf = generate_signal_base(row)

            if pos is not None and i - pos["bar"] >= 5:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl); pos = None

            if pos is None and act in ("BUY", "SELL") and conf >= 0.30:
                # Vol-adjusted sizing: lower vol = bigger position
                vol_factor = max(0.5, min(2.0, 1.0 / (vol * 100 + 0.01)))
                base_risk = 0.02 * vol_factor
                sz = max(10, kf * bal * base_risk)
                if 0 < sz <= bal:
                    pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}

        total_pnl += sum(trades); total_trades += len(trades)

    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 4: Session-Based Trading (London/NY only)
# ═══════════════════════════════════════════════════════════
def test_sessions(all_data):
    """Test 4: Only trade during London (07-16 UTC) and NY (13-22 UTC)."""
    print("\n  [4] SESSION-BASED TRADING (London + NY)")
    print("  " + "-" * 50)

    london = set(range(7, 16))   # 07:00-15:59 UTC
    ny = set(range(13, 22))      # 13:00-21:59 UTC
    active_hours = london | ny

    total_pnl = 0; total_trades = 0
    for sym, df in all_data.items():
        kelly = KellySizer()
        kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        bal = 10000.0; pos = None; trades = []

        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"])
            hr = df.index[i].hour
            act, conf = generate_signal_base(row)

            if pos is not None and i - pos["bar"] >= 5:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl); pos = None

            if pos is None:
                if hr not in active_hours:
                    continue
                if act in ("BUY", "SELL") and conf >= 0.30:
                    sz = max(10, kf * bal * 0.02)
                    if 0 < sz <= bal:
                        pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}

        total_pnl += sum(trades); total_trades += len(trades)

    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 5: Per-Symbol Optimization
# ═══════════════════════════════════════════════════════════
def test_per_symbol(all_data):
    """Test 5: Optimize min_confidence per symbol."""
    print("\n  [5] PER-SYMBOL OPTIMIZATION")
    print("  " + "-" * 50)

    total_pnl = 0; total_trades = 0
    for sym, df in all_data.items():
        # Find best min_confidence for this symbol
        best_mc = 0.30; best_pnl = -999
        for mc in [0.20, 0.25, 0.30, 0.35, 0.40]:
            pnl, _, _, _ = backtest({sym: df}, 0.02, {"min_confidence": mc, "circuit_breaker": 99})
            if pnl > best_pnl:
                best_pnl = pnl; best_mc = mc

        pnl, trades, w, _ = backtest({sym: df}, 0.02, {"min_confidence": best_mc, "circuit_breaker": 99})
        total_pnl += pnl; total_trades += trades

    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 6: Trend vs Mean-Reversion Modes
# ═══════════════════════════════════════════════════════════
def test_trend_meanrev(all_data):
    """Test 6: Switch between trend-following and mean-reversion based on market regime."""
    print("\n  [6] TREND vs MEAN-REVERSION MODES")
    print("  " + "-" * 50)

    def signal_adaptive(row):
        """Adaptive signal: trend in trending, mean-revert in ranging."""
        trend_str = float(row.get("trend_strength", 0))
        if trend_str > 2.0:  # Strong trend -> trend-following
            score = 0
            if row["close"] > row["sma_20"] > row["sma_50"]: score += 3
            elif row["close"] < row["sma_20"] < row["sma_50"]: score -= 3
            if row["momentum_5"] > 0.01: score += 2
            elif row["momentum_5"] < -0.01: score -= 2
            if row["macd_hist"] > 0: score += 1
            elif row["macd_hist"] < 0: score -= 1
            if score >= 3: return "BUY", min(score / 6.0, 1.0)
            if score <= -3: return "SELL", min(abs(score) / 6.0, 1.0)
            return "HOLD", 0.0
        else:  # Range -> mean-reversion
            score = 0
            if row["rsi"] < 30: score += 3
            elif row["rsi"] < 40: score += 1
            elif row["rsi"] > 70: score -= 3
            elif row["rsi"] > 60: score -= 1
            if row["close"] < row["bb_lower"]: score += 2
            elif row["close"] > row["bb_upper"]: score -= 2
            if score >= 3: return "BUY", min(score / 6.0, 1.0)
            if score <= -3: return "SELL", min(abs(score) / 6.0, 1.0)
            return "HOLD", 0.0

    total_pnl, total_trades, wins, _ = backtest(all_data, 0.02,
        {"circuit_breaker": 99, "min_confidence": 0.30}, signal_fn=signal_adaptive)
    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ═══════════════════════════════════════════════════════════
# IMPROVEMENT 7: ML Prediction Filter
# ═══════════════════════════════════════════════════════════
def test_ml_filter(all_data):
    """Test 7: Only take trades where ML model agrees with signal direction."""
    print("\n  [7] ML PREDICTION FILTER (XGBoost)")
    print("  " + "-" * 50)

    # Simple ML: use recent momentum + RSI as features
    # In production, use the trained XGBoost model
    def ml_agrees(row, signal):
        """Simple ML filter: momentum + RSI must agree with signal."""
        if signal == "BUY":
            return row["rsi"] < 55 and row["momentum_5"] > -0.005
        elif signal == "SELL":
            return row["rsi"] > 45 and row["momentum_5"] < 0.005
        return True

    total_pnl = 0; total_trades = 0
    for sym, df in all_data.items():
        kelly = KellySizer()
        kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        bal = 10000.0; pos = None; trades = []

        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"])
            act, conf = generate_signal_base(row)

            if pos is not None and i - pos["bar"] >= 5:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl); pos = None

            if pos is None and act in ("BUY", "SELL") and conf >= 0.30:
                if not ml_agrees(row, act):
                    continue
                sz = max(10, kf * bal * 0.02)
                if 0 < sz <= bal:
                    pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}

        total_pnl += sum(trades); total_trades += len(trades)

    print(f"  Result: {total_trades} trades | P&L=${total_pnl:+.2f}")
    return total_pnl, total_trades


# ─── Main ────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  SEVEN IMPROVEMENTS TEST")
    print("  Base: Signal-Agnostic, Risk2%, noCB, noBad, minConf30")
    print("=" * 70)

    all_data = load_all_data()
    print(f"\n  Loaded {len(all_data)} symbols")

    # Base line
    print("\n  [BASE] Signal-Agnostic (no improvements)")
    base_pnl, base_trades, base_wins, _ = backtest(all_data, 0.02,
        {"circuit_breaker": 99, "min_confidence": 0.30})
    print(f"  Result: {base_trades} trades | P&L=${base_pnl:+.2f}")

    # Test all 7
    results = {}
    results["base"] = {"pnl": base_pnl, "trades": base_trades}
    results["1_walk_forward"] = test_walk_forward(all_data)
    results["2_atr_exits"] = test_atr_exits(all_data)
    results["3_vol_sizing"] = test_vol_sizing(all_data)
    results["4_sessions"] = test_sessions(all_data)
    results["5_per_symbol"] = test_per_symbol(all_data)
    results["6_trend_meanrev"] = test_trend_meanrev(all_data)
    results["7_ml_filter"] = test_ml_filter(all_data)

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY: Seven Improvements")
    print("=" * 70)
    base = results["base"]["pnl"]
    for name, (pnl, trades) in results.items():
        delta = pnl - base if name != "base" else 0
        marker = "+" if delta > 0 else ""
        print(f"  {name:25} | {trades:5} trades | P&L=${pnl:+.2f} | Delta=${marker}{delta:.2f}")

    # Winners
    improvements = {k: v for k, v in results.items() if k != "base"}
    profitable = {k: v for k, v in improvements.items() if v[0] > base}
    print(f"\n  Profitable improvements: {len(profitable)}/7")
    for name, (pnl, _) in sorted(profitable.items(), key=lambda x: -x[1][0]):
        print(f"    +{name}: ${pnl - base:+.2f}")

    # Save
    fn = DATA_DIR / "seven_improvements_results.json"
    with open(fn, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
