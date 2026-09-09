"""
Combination Test: Stack the profitable improvements.
Base: $+12.32 | Vol Sizing: $+17.21 | Sessions: $+13.67
"""
import os, sys, json
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
DATA_DIR = Path("paper_trades")
SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURJPY","GBPJPY","AUDJPY","EURGBP","EURCHF","XAUUSD","XAGUSD","BTCUSD","ETHUSD","US30","US500","UK100","AAPL","AMZN","NVDA","TSLA","META","MSFT","GOOGL","AMD"]


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


def backtest(all_data, cfg, signal_fn=None):
    if signal_fn is None: signal_fn = generate_signal
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    risk = cfg.get("max_risk", 0.02)
    hold = cfg.get("hold_bars", 5)
    mc = cfg.get("min_confidence", 0.30)
    session_hours = cfg.get("session_hours", None)

    total_pnl = 0; total_trades = 0; wins = 0
    per_sym = {}
    for sym, df in all_data.items():
        bal = 10000.0; pos = None; trades = []
        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"]); hr = df.index[i].hour
            act, conf = signal_fn(row)

            if pos is not None and i - pos["bar"] >= hold:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl); pos = None

            if pos is None:
                if session_hours and hr not in session_hours:
                    continue
                if act in ("BUY", "SELL") and conf >= mc:
                    vol = float(row["volatility_10"]) if "volatility_10" in row.index else 0.01
                    vol_factor = max(0.5, min(2.0, 1.0 / (vol * 100 + 0.01)))
                    sz = max(10, kf * bal * risk * vol_factor)
                    if 0 < sz <= bal:
                        pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}

        sw = sum(1 for p in trades if p > 0)
        p = sum(trades); total_pnl += p; total_trades += len(trades); wins += sw
        per_sym[sym] = {"trades": len(trades), "pnl": p, "wins": sw}
    return total_pnl, total_trades, wins, per_sym


def main():
    print("=" * 70)
    print("  COMBINATION TEST: Stack Profitable Improvements")
    print("=" * 70)

    all_data = load_all_data()
    print(f"  Loaded {len(all_data)} symbols")

    london = set(range(7, 16))
    ny = set(range(13, 22))
    session_hours = london | ny

    configs = [
        ("Base (no improvements)", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5}),
        ("Vol Sizing only", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5}),
        ("Session filter only", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions + Risk3%", {"max_risk": 0.03, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions + Risk4%", {"max_risk": 0.04, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions + Risk5%", {"max_risk": 0.05, "circuit_breaker": 99, "min_confidence": 0.30, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions + minConf25", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.25, "hold_bars": 5, "session_hours": session_hours}),
        ("Vol Sizing + Sessions + minConf20", {"max_risk": 0.02, "circuit_breaker": 99, "min_confidence": 0.20, "hold_bars": 5, "session_hours": session_hours}),
    ]

    best_pnl = -999; best_name = None; best_results = None

    for name, cfg in configs:
        pnl, trades, wr, per = backtest(all_data, cfg)
        prof = sum(1 for r in per.values() if r["pnl"] > 0)
        delta = pnl - 12.32
        print(f"  {name:45} | {trades:5} trades | {prof:2}/27 prof | P&L=${pnl:+.2f} | +${delta:+.2f}")
        if pnl > best_pnl:
            best_pnl = pnl; best_name = name; best_results = per

    # Final detail
    print(f"\n{'='*70}")
    print(f"  BEST: {best_name}")
    print(f"  P&L: ${best_pnl:+.2f} (base was $+12.32, delta=${best_pnl-12.32:+.2f})")
    print(f"{'='*70}")

    for sym, r in sorted(best_results.items(), key=lambda x: -x[1]["pnl"]):
        if r["trades"] > 0 and r["pnl"] != 0:
            m = "+" if r["pnl"] > 0 else ""
            print(f"    {sym:10} {r['trades']:4} trades | P&L=${m}{r['pnl']:.2f}")

    tt = sum(r["trades"] for r in best_results.values())
    tw = sum(r["wins"] for r in best_results.values())
    wr_val = tw / tt if tt > 0 else 0
    np_ = sum(1 for r in best_results.values() if r["pnl"] > 0)
    print(f"\n  TOTAL: {tt} trades | WR={wr_val:.1%} | P&L=${best_pnl:+.2f} | {np_}/27 profitable")

    fn = DATA_DIR / "combination_results.json"
    with open(fn, "w") as f:
        json.dump({"best": best_name, "pnl": best_pnl, "results": {k: v for k, v in best_results.items()}}, f, indent=2, default=str)
    print(f"  Saved to {fn}")


if __name__ == "__main__":
    main()
