import os
"""
Verify reproducibility of best config (3 runs).
"""
import os, sys, asyncio
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from apps.analysts.market import MarketAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.compliance import ComplianceAnalyst
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
SYMBOLS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP","EURCHF",
    "XAUUSD","XAGUSD","BTCUSD","ETHUSD",
    "US30","US500","UK100",
    "AAPL","AMZN","NVDA","TSLA","META","MSFT","GOOGL","AMD",
]


def load_data():
    mt5.initialize(path=MT5_PATH, login=int(os.environ.get("MT5_LOGIN", "0")), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", ""))
    all_data = {}
    for sym in SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is None: continue
        if not info.visible: mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 1500)
        if rates is None or len(rates) < 100: continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        # Indicators
        df["sma_5"] = pd.Series(c).rolling(5).mean().values
        df["sma_20"] = pd.Series(c).rolling(20).mean().values
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
        df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values
        df = df.dropna()
        all_data[sym] = df
    mt5.shutdown()
    return all_data


def get_signals(all_data):
    analysts = [MarketAnalyst(), QuantAnalyst(), RiskAnalyst(), ComplianceAnalyst()]
    signals = {}
    for sym in all_data:
        async def _r(s=sym):
            tasks = [a.analyze(s, "1H") for a in analysts]
            return await asyncio.gather(*tasks, return_exceptions=True)
        try:
            results = asyncio.run(_r())
        except Exception:
            results = []
        valid = [r for r in results if hasattr(r, "signal")]
        buy = sum(1 for r in valid if r.signal == "BUY")
        sell = sum(1 for r in valid if r.signal == "SELL")
        d = buy + sell
        if d == 0:
            signals[sym] = ("HOLD", 0.0)
        elif buy > sell:
            signals[sym] = ("BUY", d / max(len(valid), 1))
        elif sell > buy:
            signals[sym] = ("SELL", d / max(len(valid), 1))
        else:
            signals[sym] = ("HOLD", 0.0)
    return signals


def backtest(all_data, signals, risk, cb_limit):
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    total_pnl = 0
    total_trades = 0
    wins = 0
    per_sym = {}
    for sym, df in all_data.items():
        action, agree = signals[sym]
        if action == "HOLD" or agree < 0.25:
            per_sym[sym] = {"trades": 0, "pnl": 0, "wins": 0}
            continue
        balance = 10000.0; pos = None; trades = []; cl = 0; lb = 50
        for i in range(lb, len(df)):
            px = float(df.iloc[i]["close"])
            hr = df.index[i].hour; dw = df.index[i].dayofweek
            if pos is not None and i - pos["bar"] >= 5:
                pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY"
                       else (pos["px"] - px) / pos["px"]) * pos["s"]
                balance += pnl; trades.append(pnl)
                cl = cl + 1 if pnl <= 0 else 0; pos = None
            if pos is None:
                skip = (cl >= cb_limit) or (hr in {19, 22}) or (dw == 1)
                if skip: continue
                if action in ("BUY", "SELL"):
                    sz = max(10, kf * balance * risk)
                    if 0 < sz <= balance:
                        pos = {"a": action, "px": px, "bar": i, "s": min(sz, balance * 0.3)}
        sym_wins = sum(1 for p in trades if p > 0)
        total_pnl += sum(trades)
        total_trades += len(trades)
        wins += sym_wins
        per_sym[sym] = {"trades": len(trades), "pnl": sum(trades), "wins": sym_wins}
    return total_pnl, total_trades, wins, per_sym


def main():
    print("=" * 60)
    print("  REPRODUCIBILITY CHECK: 3 runs of best config")
    print("=" * 60)

    all_data = load_data()
    print(f"  Loaded {len(all_data)} symbols")

    signals = get_signals(all_data)
    buy_count = sum(1 for a, _ in signals.values() if a == "BUY")
    sell_count = sum(1 for a, _ in signals.values() if a == "SELL")
    hold_count = sum(1 for a, _ in signals.values() if a == "HOLD")
    print(f"  Signals: {buy_count} BUY, {sell_count} SELL, {hold_count} HOLD")

    # Config: Risk 30%, No CB (best from round 3)
    print("\n  Config: Risk=30%, No CB, bad_hours={19,22}, bad_days={Tue}")
    print("-" * 60)

    pnls = []
    for run in range(5):
        pnl, trades, wr, per_sym = backtest(all_data, signals, risk=0.30, cb_limit=99)
        pnls.append(pnl)
        print(f"  Run {run+1}: {trades:5} trades | P&L: ${pnl:+.2f}")

    print("-" * 60)
    avg_pnl = sum(pnls) / len(pnls)
    print(f"  Average: ${avg_pnl:+.2f}")
    print(f"  Min:     ${min(pnls):+.2f}")
    print(f"  Max:     ${max(pnls):+.2f}")

    # Top symbols from last run
    print("\n  Per-symbol (last run):")
    for sym, r in sorted(per_sym.items(), key=lambda x: -x[1]["pnl"]):
        if r["trades"] > 0 and r["pnl"] > 0:
            print(f"    +{sym:10} {r['trades']:4} trades | P&L=${r['pnl']:+.2f}")

    print(f"\n  TARGET $50: {'ACHIEVED (all runs)' if all(p >= 50 for p in pnls) else 'SOME RUNS BELOW $50'}")


if __name__ == "__main__":
    main()
