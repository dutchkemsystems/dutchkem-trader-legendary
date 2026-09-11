import os
"""Quick verify: deterministic best configs."""
import os, sys, json, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURJPY","GBPJPY","AUDJPY","EURGBP","EURCHF","XAUUSD","XAGUSD","BTCUSD","ETHUSD","US30","US500","UK100","AAPL","AMZN","NVDA","TSLA","META","MSFT","GOOGL","AMD"]


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
        df["sma_5"] = pd.Series(c).rolling(5).mean().values
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
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
        df["atr"] = pd.Series(tr).rolling(14).mean().values
        df["momentum_5"] = pd.Series(c).pct_change(5).values
        df = df.dropna()
        all_data[sym] = df
    mt5.shutdown()
    return all_data


def gen_signal(row):
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


def bt(all_data, risk, cb, bh, bd, mc):
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    total_pnl = 0; total_trades = 0; wins = 0; per_sym = {}
    for sym, df in all_data.items():
        bal = 10000.0; pos = None; trades = []; cl = 0
        for i in range(50, len(df)):
            row = df.iloc[i]; px = float(row["close"])
            hr = df.index[i].hour; dw = df.index[i].dayofweek
            act, conf = gen_signal(row)
            if pos is not None and i - pos["bar"] >= 5:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                bal += pnl; trades.append(pnl)
                cl = cl + 1 if pnl <= 0 else 0; pos = None
            if pos is None:
                skip = (cl >= cb) or (hr in bh) or (dw in bd)
                if not skip and act in ("BUY", "SELL") and conf >= mc:
                    sz = max(10, kf * bal * risk)
                    if 0 < sz <= bal:
                        pos = {"a": act, "px": px, "bar": i, "s": min(sz, bal * 0.3)}
        sw = sum(1 for p in trades if p > 0)
        p = sum(trades); total_pnl += p; total_trades += len(trades); wins += sw
        per_sym[sym] = {"trades": len(trades), "pnl": p, "wins": sw}
    return total_pnl, total_trades, wins, per_sym


def main():
    print("=" * 70)
    print("  VERIFICATION: Top 4 deterministic configs (run 3x each)")
    print("=" * 70)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols")

    configs = [
        ("Risk40 noCB noBad", 0.40, 99, set(), set(), 0.30),
        ("Risk35 noCB", 0.35, 99, {19, 22}, set(), 0.30),
        ("Risk30 CB4 Tue", 0.30, 4, {19, 22}, {1}, 0.30),
        ("Risk25 noCB noBad", 0.25, 99, set(), set(), 0.30),
    ]

    for name, risk, cb, bh, bd, mc in configs:
        print(f"\n  --- {name} ---")
        for run in range(3):
            pnl, trades, wr, per = bt(all_data, risk, cb, bh, bd, mc)
            prof = sum(1 for r in per.values() if r["pnl"] > 0)
            print(f"    Run {run+1}: P&L=${pnl:+.2f} | {trades} trades | {prof}/27 prof")

    # Best config detailed output
    print("\n" + "=" * 70)
    print("  BEST CONFIG DETAIL: Risk40 noCB noBad")
    print("=" * 70)
    pnl, trades, wr, per = bt(all_data, 0.40, 99, set(), set(), 0.30)
    for sym, r in sorted(per.items(), key=lambda x: -x[1]["pnl"]):
        if r["trades"] > 0:
            m = "+" if r["pnl"] > 0 else ""
            print(f"    {sym:10} {r['trades']:4} trades | WR={r['wins']/r['trades']:.0%} | P&L=${m}{r['pnl']:.2f}")

    tt = sum(r["trades"] for r in per.values())
    tw = sum(r["wins"] for r in per.values())
    wr_val = tw / tt if tt > 0 else 0
    np_ = sum(1 for r in per.values() if r["pnl"] > 0)
    print(f"\n  TOTAL: {tt} trades | WR={wr_val:.1%} | P&L=${pnl:+.2f} | {np_}/27 profitable")


if __name__ == "__main__":
    main()
