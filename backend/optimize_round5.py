"""
Round 5: Enhanced Strategy with Trailing Stops + Symbol Exclusion
Builds on Round 4 insights (risk30 CB4 Tue minConf30 = +$68.10).
Key improvements:
- Trailing stop-loss (ATR-based)
- Dynamic position sizing based on volatility
- Symbol exclusion for consistently losing instruments
- Time-of-day session filter (London/NY overlap)
- Trend strength filter (ADX-like)
"""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from pathlib import Path
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

# Excluded symbols (consistently losing in backtests)
EXCLUDED = {"BTCUSD", "MSFT", "META", "AMZN"}

SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP",
    "XAUUSD","XAGUSD","ETHUSD",
    "US30","US500","UK100",
    "AAPL","NVDA","TSLA","GOOGL","AMD",
]


def load_data():
    mt5.initialize(path=MT5_PATH, login=476963617, password="Christ@5436", server="Exness-MT5Trial9")
    all_data = {}
    for sym in SYMBOLS:
        if sym in EXCLUDED: continue
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
        # Indicators
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
        df["momentum_5"] = pd.Series(c).pct_change(5).values
        df["momentum_10"] = pd.Series(c).pct_change(10).values
        df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values
        # ADX-like trend strength
        plus_dm = np.maximum(np.diff(h, prepend=h[0]), 0)
        minus_dm = np.maximum(-np.diff(l, prepend=l[0]), 0)
        plus_dm[plus_dm < minus_dm] = 0
        minus_dm[minus_dm < plus_dm] = 0
        atr_smooth = pd.Series(tr).ewm(span=14).mean().values
        plus_di = 100 * pd.Series(plus_dm).ewm(span=14).mean().values / (atr_smooth + 1e-10)
        minus_di = 100 * pd.Series(minus_dm).ewm(span=14).mean().values / (atr_smooth + 1e-10)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        df["adx"] = pd.Series(dx).ewm(span=14).mean().values
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di
        df = df.dropna()
        all_data[sym] = df
    mt5.shutdown()
    return all_data


def generate_signal(row, use_adx=True, adx_threshold=20):
    """Enhanced signal with trend strength filter."""
    score = 0
    # MACD crossover
    if row["macd_hist"] > 0: score += 1
    elif row["macd_hist"] < 0: score -= 1
    # RSI
    if row["rsi"] < 35: score += 2
    elif row["rsi"] < 45: score += 1
    elif row["rsi"] > 65: score -= 2
    elif row["rsi"] > 55: score -= 1
    # SMA trend
    if row["close"] > row["sma_20"] > row["sma_50"]: score += 2
    elif row["close"] < row["sma_20"] < row["sma_50"]: score -= 2
    # Momentum
    if row["momentum_5"] > 0.005: score += 1
    elif row["momentum_5"] < -0.005: score -= 1
    # BB position
    if row["close"] < row["bb_lower"]: score += 1
    elif row["close"] > row["bb_upper"]: score -= 1
    # ADX trend filter: boost score in strong trends, reduce in weak
    if use_adx:
        if row["adx"] > adx_threshold:
            # Strong trend — amplify signal
            if score > 0: score += 1
            elif score < 0: score -= 1
        else:
            # Weak trend — dampen signal
            if abs(score) <= 2: score = 0  # kill weak signals in ranging market
    # Decision
    if score >= 3: return "BUY", min(score / 7.0, 1.0)
    if score <= -3: return "SELL", min(abs(score) / 7.0, 1.0)
    return "HOLD", 0.0


def backtest(all_data, cfg):
    """Enhanced backtest with trailing stops and session filters."""
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    risk = cfg["max_risk"]
    cb_limit = cfg["circuit_breaker"]
    bad_hours = cfg.get("bad_hours", set())
    bad_days = cfg.get("bad_days", set())
    min_conf = cfg.get("min_confidence", 0.30)
    use_trailing = cfg.get("trailing_stop", False)
    trail_atr_mult = cfg.get("trail_atr_mult", 2.0)
    max_hold = cfg.get("max_hold", 8)
    session_only = cfg.get("session_only", False)
    use_adx = cfg.get("use_adx", True)
    adx_threshold = cfg.get("adx_threshold", 20)
    min_adx = cfg.get("min_adx", 0)

    results = {}
    total_pnl = 0; total_trades = 0; wins = 0

    for sym, df in all_data.items():
        balance = 10000.0; pos = None; trades = []; cl = 0; lb = 50
        for i in range(lb, len(df)):
            row = df.iloc[i]
            px = float(row["close"])
            hi = float(row["high"])
            lo = float(row["low"])
            hr = df.index[i].hour; dw = df.index[i].dayofweek
            atr_val = float(row["atr"])

            # Close existing position
            if pos is not None:
                bars_held = i - pos["bar"]
                hit_stop = False
                hit_trail = False

                # Fixed stop-loss (1.5x ATR)
                if pos["a"] == "BUY":
                    if lo <= pos["sl"]: hit_stop = True; px = pos["sl"]
                else:
                    if hi >= pos["sl"]: hit_stop = True; px = pos["sl"]

                # Trailing stop update
                if use_trailing and not hit_stop:
                    if pos["a"] == "BUY":
                        new_trail = hi - trail_atr_mult * atr_val
                        if new_trail > pos.get("trail", pos["sl"]):
                            pos["trail"] = new_trail
                        if lo <= pos.get("trail", 0): hit_trail = True; px = pos["trail"]
                    else:
                        new_trail = lo + trail_atr_mult * atr_val
                        if new_trail < pos.get("trail", pos["sl"]):
                            pos["trail"] = new_trail
                        if hi >= pos.get("trail", float("inf")): hit_trail = True; px = pos["trail"]

                # Time-based exit
                time_exit = bars_held >= max_hold

                if hit_stop or hit_trail or time_exit:
                    pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                           else (pos["px"] - px) / pos["px"]) * pos["s"]
                    balance += pnl; trades.append(pnl)
                    cl = cl + 1 if pnl <= 0 else 0; pos = None
                continue

            # Open new position
            if pos is None:
                skip = (cl >= cb_limit) or (hr in bad_hours) or (dw in bad_days)
                if session_only and hr not in {7,8,9,10,11,12,13,14,15,16,17}:
                    skip = True
                if min_adx > 0 and row["adx"] < min_adx:
                    skip = True
                action, conf = generate_signal(row, use_adx=use_adx, adx_threshold=adx_threshold)
                if not skip and action in ("BUY", "SELL") and conf >= min_conf:
                    sz = max(10, kf * balance * risk)
                    if 0 < sz <= balance:
                        sl_dist = 1.5 * atr_val
                        sl = px - sl_dist if action == "BUY" else px + sl_dist
                        pos = {"a": action, "px": px, "bar": i, "sl": sl,
                               "s": min(sz, balance * 0.3), "trail": sl}

        # Force close remaining
        if pos is not None:
            px = float(df.iloc[-1]["close"])
            pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                   else (pos["px"] - px) / pos["px"]) * pos["s"]
            balance += pnl; trades.append(pnl)

        sw = sum(1 for p in trades if p > 0)
        pnl = sum(trades)
        results[sym] = {"trades": len(trades), "wins": sw, "pnl": pnl,
                        "win_rate": sw / len(trades) if trades else 0}
        total_pnl += pnl; total_trades += len(trades); wins += sw

    return total_pnl, total_trades, wins, results


def main():
    print("=" * 70)
    print("  ROUND 5: ENHANCED STRATEGY (Trailing Stops + Exclusion + ADX)")
    print("=" * 70)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols (excluded: {', '.join(EXCLUDED) if EXCLUDED else 'none'})")

    configs = [
        # Baseline from Round 4 winner
        ("Base: risk30 CB4 Tue minConf30", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": False, "max_hold": 99,
        }),
        # + Trailing stop
        ("risk30 CB4 Tue minConf30 +Trail", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 99,
        }),
        # Trailing + shorter hold
        ("risk30 CB4 Tue Trail Hold6", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
        }),
        # Trailing + tight trail (1.5x ATR)
        ("risk30 CB4 Tue Trail1.5 Hold6", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 1.5, "max_hold": 6,
        }),
        # Session-only (London/NY overlap)
        ("risk30 CB4 Tue Session Trail Hold6", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
            "session_only": True,
        }),
        # ADX filter (strong trends only)
        ("risk30 CB4 Tue ADX25 Trail Hold6", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
            "use_adx": True, "adx_threshold": 25,
        }),
        # Higher risk + trail
        ("risk35 CB4 Tue Trail Hold6", {
            "max_risk": 0.35, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
        }),
        # No CB + trail
        ("risk30 noCB Tue Trail Hold6", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
        }),
        # No CB + no bad days + trail
        ("risk30 noCB noBad Trail Hold6", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
        }),
        # Min ADX filter
        ("risk30 CB4 Tue Trail minADX15", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
            "min_adx": 15,
        }),
        # Wide trail (2.5x ATR)
        ("risk30 CB4 Tue Trail2.5 Hold8", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.5, "max_hold": 8,
        }),
        # Combo: session + ADX + trail
        ("risk30 CB4 Session ADX20 Trail", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
            "session_only": True, "use_adx": True, "adx_threshold": 20,
        }),
        # Aggressive: risk40 + trail + session
        ("risk40 CB4 Tue Session Trail Hold6", {
            "max_risk": 0.40, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "trailing_stop": True, "trail_atr_mult": 2.0, "max_hold": 6,
            "session_only": True,
        }),
    ]

    best_pnl = -999; best_name = None; best_results = None

    print(f"\n  Testing {len(configs)} configurations:\n")
    for name, cfg in configs:
        pnl, trades, wr, results = backtest(all_data, cfg)
        prof = sum(1 for r in results.values() if r["pnl"] > 0)
        m = "+" if pnl > 0 else ""
        print(f"  {name:45} | {trades:4} trades | {prof:2}/{len(results)} prof | P&L=${m}{pnl:.2f}")
        if pnl > best_pnl:
            best_pnl = pnl; best_name = name; best_results = results

    print(f"\n{'=' * 70}")
    print(f"  BEST: {best_name}")
    print(f"  P&L: ${best_pnl:+.2f}")
    print(f"{'=' * 70}")

    # Show per-symbol
    for sym, r in sorted(best_results.items(), key=lambda x: -x[1]["pnl"]):
        if r["trades"] > 0:
            m = "+" if r["pnl"] > 0 else ""
            print(f"    {sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${m}{r['pnl']:.2f}")

    tt = sum(r["trades"] for r in best_results.values())
    tw = sum(r["wins"] for r in best_results.values())
    wr = tw / tt if tt > 0 else 0
    np_ = sum(1 for r in best_results.values() if r["pnl"] > 0)
    print(f"\n  PORTFOLIO: {tt} trades | WR={wr:.1%} | P&L=${best_pnl:+.2f} | {np_}/{len(best_results)} profitable")
    print(f"  TARGET $50: {'ACHIEVED!' if best_pnl >= 50 else f'NEED ${50-best_pnl:.2f} MORE'}")

    # Save
    import json, time
    fn = Path("paper_trades") / f"optimization_round5_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({"config": best_name, "total_pnl": best_pnl, "results": best_results}, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
