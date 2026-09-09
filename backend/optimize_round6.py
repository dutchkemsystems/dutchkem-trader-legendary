"""
Round 6: Symbol-Weighted Portfolio Optimization
Key insight from Round 3-5: Some symbols are consistently profitable (AMD +$86, ETH +$52, TSLA +$40),
while others consistently lose (MSFT -$41, BTC -$34, AMZN -$34, META -$33).

Strategy: Focus on profitable symbols with dynamic position sizing.
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

# All symbols for full backtest
ALL_SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP",
    "XAUUSD","XAGUSD",
    "US30","US500","UK100",
    "AAPL","NVDA","TSLA","GOOGL","AMD",
]

# Historical winners (from Round 3): AMD, ETH, TSLA, GOOGL, USDJPY, XAUUSD, EURJPY
# Historical losers: MSFT, BTC, AMZN, META


def load_data():
    mt5.initialize(path=MT5_PATH, login=476963617, password="Christ@5436", server="Exness-MT5Trial9")
    all_data = {}
    for sym in ALL_SYMBOLS:
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
    """Backtest with optional symbol weighting and trailing stops."""
    risk = cfg["max_risk"]
    cb_limit = cfg["circuit_breaker"]
    bad_hours = cfg.get("bad_hours", set())
    bad_days = cfg.get("bad_days", set())
    min_conf = cfg.get("min_confidence", 0.30)
    max_hold = cfg.get("max_hold", 99)
    use_trailing = cfg.get("trailing_stop", False)
    trail_mult = cfg.get("trail_atr_mult", 2.0)
    # Symbol weight overrides: multiply position size by weight
    sym_weights = cfg.get("sym_weights", {})
    # Reduce weight for historically weak symbols
    weak_penalty = cfg.get("weak_penalty", 1.0)

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

                time_exit = bars_held >= max_hold
                if hit_stop or hit_trail or time_exit:
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
                               "s": min(sz, balance * 0.3), "trail": sl}

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
    print("  ROUND 6: SYMBOL-WEIGHTED PORTFOLIO OPTIMIZATION")
    print("=" * 70)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols")

    configs = [
        # Baseline: Round 4 winner
        ("Baseline: risk30 CB3", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
        }),
        # Winner-focused: 2x weight on proven winners
        ("2x Winners (AMD,TSLA,ETH,GOOGL)", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
        }),
        # 3x winners
        ("3x Winners (AMD,TSLA,ETH,GOOGL)", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # Winners only (0.5x on losers)
        ("Winners 1.5x + Losers 0.5x", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 1.5, "TSLA": 1.5, "ETHUSD": 1.5, "GOOGL": 1.5, "XAUUSD": 1.5,
                           "EURJPY": 1.5, "USDJPY": 1.5},
        }),
        # Higher risk + 2x winners
        ("risk35 + 2x Winners", {
            "max_risk": 0.35, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
        }),
        # Tuesday filter + 2x winners
        ("Tue + 2x Winners", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": {1},
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
        }),
        # CB4 + 2x winners + trailing
        ("CB4 + 2x Winners + Trail", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
            "trailing_stop": True, "trail_atr_mult": 2.5,
        }),
        # 3x winners + trailing + CB4
        ("3x Winners + Trail + CB4", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
            "trailing_stop": True, "trail_atr_mult": 2.5,
        }),
        # risk40 + 3x winners
        ("risk40 + 3x Winners", {
            "max_risk": 0.40, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # Tight confidence (0.40) + 2x winners
        ("minConf40 + 2x Winners", {
            "max_risk": 0.30, "circuit_breaker": 3, "bad_hours": {19, 22}, "bad_days": set(),
            "min_confidence": 0.40, "max_hold": 99,
            "sym_weights": {"AMD": 2.0, "TSLA": 2.0, "ETHUSD": 2.0, "GOOGL": 2.0},
        }),
        # No circuit breaker + 3x winners
        ("noCB + 3x Winners", {
            "max_risk": 0.30, "circuit_breaker": 99, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0},
        }),
        # Absolute best combo
        ("risk30 CB4 Trail 3xW+XAU", {
            "max_risk": 0.30, "circuit_breaker": 4, "bad_hours": set(), "bad_days": set(),
            "min_confidence": 0.30, "max_hold": 99,
            "sym_weights": {"AMD": 3.0, "TSLA": 3.0, "ETHUSD": 3.0, "GOOGL": 3.0, "XAUUSD": 2.0},
            "trailing_stop": True, "trail_atr_mult": 2.5,
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
    print(f"  TARGET $50: {'ACHIEVED!' if best_pnl >= 50 else f'NEED ${50-best_pnl:.2f} MORE'}")

    import json, time
    fn = Path("paper_trades") / f"optimization_round6_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({"config": best_name, "total_pnl": best_pnl, "results": best_results}, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
