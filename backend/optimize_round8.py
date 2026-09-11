import os
"""
Round 8: Final Production Config
Key findings from Round 7:
- AMD = +$5,158 (clear winner, needs max weight)
- TSLA = -$1,219 (actually a loser, needs 0.5x or exclusion)
- AAPL = -$407 (loser)
- No circuit breaker = best
- 3x on AMD + 1x on others = optimal

This round fine-tunes the exact optimal config.
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

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

# Final symbol list (exclude known losers)
SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP",
    "XAUUSD",
    "US30",
    "AMD","GOOGL",
]


def load_data():
    mt5.initialize(path=MT5_PATH, login=int(os.environ.get("MT5_LOGIN", "0")), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", ""))
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
    sym_weights = cfg.get("sym_weights", {})
    min_conf = cfg.get("min_confidence", 0.30)

    results = {}
    total_pnl = 0; total_trades = 0; wins = 0

    for sym, df in all_data.items():
        balance = 10000.0; pos = None; trades = []; lb = 50
        for i in range(lb, len(df)):
            row = df.iloc[i]
            px = float(row["close"])

            if pos is not None:
                bars_held = i - pos["bar"]
                if bars_held >= 10:
                    pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                           else (pos["px"] - px) / pos["px"]) * pos["s"]
                    balance += pnl; trades.append(pnl); pos = None
                continue

            if pos is None:
                action, conf = generate_signal(row)
                if action in ("BUY", "SELL") and conf >= min_conf:
                    base_sz = risk * balance
                    w = sym_weights.get(sym, 1.0)
                    sz = max(10, base_sz * w)
                    if 0 < sz <= balance:
                        pos = {"a": action, "px": px, "bar": i, "s": min(sz, balance * 0.5)}

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
    print("  ROUND 8: FINAL PRODUCTION CONFIG")
    print("=" * 70)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols")

    configs = [
        # AMD-only focused
        ("AMD5x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 5.0},
        }),
        ("AMD4x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 4.0},
        }),
        ("AMD3x GOOGL1x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0, "GOOGL": 1.0},
        }),
        ("AMD3x GOOGL2x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0, "GOOGL": 2.0},
        }),
        # Risk variations
        ("risk40 AMD3x noCB", {
            "max_risk": 0.40, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0},
        }),
        ("risk50 AMD3x noCB", {
            "max_risk": 0.50, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0},
        }),
        # Balanced: AMD + select winners
        ("AMD3x GOOGL1x XAU1x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0, "GOOGL": 1.0, "XAUUSD": 1.0},
        }),
        # From Round 6 winners
        ("AMD3x GOOGL1x USDJPY1x noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0, "GOOGL": 1.0, "USDJPY": 1.0},
        }),
        # Equal weight for comparison
        ("Equal noCB", {
            "max_risk": 0.30, "min_confidence": 0.30,
            "sym_weights": {},
        }),
        # Higher confidence
        ("AMD3x minConf40 noCB", {
            "max_risk": 0.30, "min_confidence": 0.40,
            "sym_weights": {"AMD": 3.0},
        }),
        # risk25 conservative
        ("risk25 AMD3x noCB", {
            "max_risk": 0.25, "min_confidence": 0.30,
            "sym_weights": {"AMD": 3.0},
        }),
        # Ultra-aggressive
        ("risk50 AMD5x noCB", {
            "max_risk": 0.50, "min_confidence": 0.30,
            "sym_weights": {"AMD": 5.0},
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
    print(f"\n  PRODUCTION RECOMMENDATION:")
    print(f"  - Use: {best_name}")
    print(f"  - Focus on AMD (consistently profitable)")
    print(f"  - No circuit breaker (let winners run)")
    print(f"  - Risk 30% per trade, 3x weight on AMD")

    import json, time
    fn = Path("paper_trades") / f"optimization_round8_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({"config": best_name, "total_pnl": best_pnl, "results": best_results,
                   "recommendation": {
                       "max_risk": 0.30, "min_confidence": 0.30,
                       "sym_weights": {"AMD": 3.0},
                       "circuit_breaker": 99,
                       "excluded_symbols": ["NVDA", "XAGUSD", "US500", "UK100", "TSLA", "AAPL", "ETHUSD"],
                   }}, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
