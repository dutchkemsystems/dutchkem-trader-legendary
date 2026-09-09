"""
Round 7: Final Optimization - Exclude Consistent Losers
Round 6 winner: noCB + 3x Winners = +$644.15
Problem: NVDA (-$813), XAGUSD (-$416), US500 (-$179) dragging results.

Strategy: Exclude losers, optimize remaining symbols.
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

# Round 6 losers to exclude
LOSERS = {"NVDA", "XAGUSD", "US500", "UK100"}

SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP",
    "XAUUSD",
    "US30",
    "AAPL","TSLA","GOOGL","AMD",
]


def load_data():
    mt5.initialize(path=MT5_PATH, login=476963617, password="Christ@5436", server="Exness-MT5Trial9")
    all_data = {}
    for sym in SYMBOLS:
        if sym in LOSERS: continue
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
        df["bb_upper"] = df["sma_20"] + 2 * bb_std
        df["bb_lower"] = df["sma_20"] - 2 * bb_std
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
        df["atr"] = pd.Series(tr).rolling(14).mean().values
        df["momentum_5"] = pd.Series(c).pct_change(5).values
        df = df.dropna()
        all_data[sym] = df
    mt5.shutdown()
    return all_data


def generate_signal(row):
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


def backtest(all_data, cfg):
    risk = cfg["max_risk"]
    cb_limit = cfg["circuit_breaker"]
    bad_hours = cfg.get("bad_hours", set())
    bad_days = cfg.get("bad_days", set())
    min_conf = cfg.get("min_confidence", 0.30)
    sym_weights = cfg.get("sym_weights", {})
    use_trailing = cfg.get("trailing_stop", False)
    trail_mult = cfg.get("trail_atr_mult", 2.5)

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

            if pos is not None:
                bars_held = i - pos["bar"]
                hit_stop = False; hit_trail = False
                if pos["a"] == "BUY":
                    if lo <= pos["sl"]: hit_stop = True; px = pos["sl"]
                else:
                    if hi >= pos["sl"]: hit_stop = True; px = pos["sl"]

                if use_trailing and not hit_stop:
                    if pos["a"] == "BUY":
                        new_trail = hi - trail_mult * atr_val
                        if new_trail > pos.get("trail", pos["sl"]): pos["trail"] = new_trail
                        if lo <= pos.get("trail", 0): hit_trail = True; px = pos["trail"]
                    else:
                        new_trail = lo + trail_mult * atr_val
                        if new_trail < pos.get("trail", pos["sl"]): pos["trail"] = new_trail
                        if hi >= pos.get("trail", float("inf")): hit_trail = True; px = pos["trail"]

                if hit_stop or hit_trail:
                    pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                           else (pos["px"] - px) / pos["px"]) * pos["s"]
                    balance += pnl; trades.append(pnl)
                    cl = cl + 1 if pnl <= 0 else 0; pos = None
                continue

            if pos is None:
                skip = (cl >= cb_limit) or (hr in bad_hours) or (dw in bad_days)
                action, conf = generate_signal(row)
                if not skip and action in ("BUY", "SELL") and conf >= min_conf:
                    base_sz = risk * balance
                    w = sym_weights.get(sym, 1.0)
                    sz = max(10, base_sz * w)
                    if 0 < sz <= balance:
                        sl_dist = 1.5 * atr_val
                        sl = px - sl_dist if action == "BUY" else px + sl_dist
                        pos = {"a": action, "px": px, "bar": i, "sl": sl,
                               "s": min(sz, balance * 0.4), "trail": sl}

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
    print("  ROUND 7: FINAL OPTIMIZATION (Exclude Losers)")
    print("=" * 70)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols (excluded: {', '.join(LOSERS)})")

    configs = [
        # Round 6 winner baseline (adjusted for fewer symbols)
        ("noCB 3xW noLOSERS", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # 4x winners
        ("noCB 4xW", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 4.0, "TSLA": 4.0, "ETHUSD": 4.0, "GOOGL": 4.0},
        }),
        # risk40 + 3x winners
        ("risk40 noCB 3xW", {
            "max_risk": 0.40, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # risk50 + 3x winners
        ("risk50 noCB 3xW", {
            "max_risk": 0.50, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # 5x winners (AMD, TSLA, GOOGL)
        ("noCB 5xW (AMD,TSLA,GOOGL)", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 5.0, "TSLA": 5.0, "GOOGL": 5.0},
        }),
        # 3x all winners + XAUUSD
        ("noCB 3xW+XAU", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0, "XAUUSD": 3.0},
        }),
        # Higher min confidence
        ("noCB 3xW minConf40", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.40, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # Trailing stop
        ("noCB 3xW Trail2.5", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
            "trailing_stop": True, "trail_atr_mult": 2.5,
        }),
        # CB3 + 3x winners (moderate)
        ("CB3 3xW", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # Ultra aggressive
        ("risk50 noCB 5xW", {
            "max_risk": 0.50, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 5.0, "TSLA": 5.0, "GOOGL": 5.0},
        }),
        # Conservative: 2x winners
        ("noCB 2xW", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
        }),
        # AAPL as 2x (was +$82 in Round 6)
        ("noCB 3xW AAPL2x", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0, "AAPL": 2.0},
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

    for sym, r in sorted(best_results.items(), key=lambda x: -x[1]["pnl"]):
        if r["trades"] > 0:
            m = "+" if r["pnl"] > 0 else ""
            print(f"    {sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${m}{r['pnl']:.2f}")

    tt = sum(r["trades"] for r in best_results.values())
    tw = sum(r["wins"] for r in best_results.values())
    wr = tw / tt if tt > 0 else 0
    np_ = sum(1 for r in best_results.values() if r["pnl"] > 0)
    print(f"\n  PORTFOLIO: {tt} trades | WR={wr:.1%} | P&L=${best_pnl:+.2f} | {np_}/{len(best_results)} profitable")

    import json, time
    fn = Path("paper_trades") / f"optimization_round7_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({"config": best_name, "total_pnl": best_pnl, "results": best_results}, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
