import os
"""
Round 3: Final push to $50+
"""
import os, sys, json, time, asyncio
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from pathlib import Path

from apps.analysts.market import MarketAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.compliance import ComplianceAnalyst
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")
DATA_DIR = Path("paper_trades")

SYMBOLS_28 = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP", "EURCHF",
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "US30", "US500", "UK100",
    "AAPL", "AMZN", "NVDA", "TSLA", "META", "MSFT", "GOOGL", "AMD",
]


def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        return False
    info = mt5.account_info()
    print(f"MT5: ${info.balance}")
    return True


def fetch_candles_mt5(symbol, n=1500):
    info = mt5.symbol_info(symbol)
    if info is None: return None
    if not info.visible: mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, n)
    if rates is None or len(rates) == 0: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
    return df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]


def add_indicators(df):
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
    df["momentum_5"] = pd.Series(c).pct_change(5).values
    df["momentum_10"] = pd.Series(c).pct_change(10).values
    df["volatility_10"] = pd.Series(c).pct_change().rolling(10).std().values
    return df


def precompute_signals(analysts, symbol):
    async def _run():
        tasks = [a.analyze(symbol, "1H") for a in analysts]
        return await asyncio.gather(*tasks, return_exceptions=True)
    try: results = asyncio.run(_run())
    except: results = []
    valid = [r for r in results if hasattr(r, "signal")]
    buy = sum(1 for r in valid if r.signal == "BUY")
    sell = sum(1 for r in valid if r.signal == "SELL")
    d = buy + sell
    if d == 0: return "HOLD", 0.0
    if buy > sell: return "BUY", d / max(len(valid), 1)
    if sell > buy: return "SELL", d / max(len(valid), 1)
    return "HOLD", 0.0


def backtest_fast(candles, action, agreement, cfg):
    lb = 50; balance = 10000.0; pos = None; trades = []; cl = 0; filtered = 0
    kelly = KellySizer()
    kf = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
    bh = cfg.get("bad_hours", {19, 22}); bd = cfg.get("bad_days", {1})
    cb = cfg.get("circuit_breaker", 3); ma = cfg.get("min_agreement", 0.25)
    risk = cfg.get("max_risk", 0.25)

    if action == "HOLD" or agreement < ma:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "pnl": 0, "filtered": 0}

    for i in range(lb, len(candles)):
        px = float(candles.iloc[i]["close"])
        hr = candles.index[i].hour; dw = candles.index[i].dayofweek

        if pos is not None and i - pos["bar"] >= 5:
            pnl = ((px - pos["px"]) / pos["px"] if pos["a"] == "BUY" else (pos["px"] - px) / pos["px"]) * pos["s"]
            balance += pnl; trades.append(pnl)
            cl = cl + 1 if pnl <= 0 else 0; pos = None

        if pos is None:
            skip = (cl >= cb) or (hr in bh) or (dw in bd)
            if skip: filtered += 1; continue
            if action in ("BUY", "SELL"):
                sz = max(10, kf * balance * risk)
                if 0 < sz <= balance:
                    pos = {"a": action, "px": px, "bar": i, "s": min(sz, balance * 0.3)}

    w = sum(1 for p in trades if p > 0)
    return {"trades": len(trades), "wins": w, "losses": len(trades) - w,
            "win_rate": w / len(trades) if trades else 0, "pnl": sum(trades), "filtered": filtered}


def run_config(all_data, signals, cfg):
    results = {}
    for sym, df in all_data.items():
        action, agree = signals[sym]
        r = backtest_fast(df, action, agree, cfg)
        r["symbol"] = sym; results[sym] = r
    total_pnl = sum(r["pnl"] for r in results.values())
    total_trades = sum(r["trades"] for r in results.values())
    prof = sum(1 for r in results.values() if r["pnl"] > 0)
    return total_pnl, total_trades, prof, results


def main():
    print("=" * 70)
    print("  ROUND 3: FINAL PUSH TO $50+")
    print("=" * 70)

    if not connect_mt5(): return

    print("\nFetching data...")
    all_data = {}
    for sym in SYMBOLS_28:
        df = fetch_candles_mt5(sym, 1500)
        if df is not None and len(df) > 100:
            df = add_indicators(df); df = df.dropna()
            all_data[sym] = df
    mt5.shutdown()
    print(f"  {len(all_data)} symbols loaded")

    analysts = [MarketAnalyst(), QuantAnalyst(), RiskAnalyst(), ComplianceAnalyst()]
    signals = {}
    for sym in all_data:
        signals[sym] = precompute_signals(analysts, sym)

    # Fine-tune configs around the best zone
    configs = [
        ("Baseline R2 (25%, CB3)", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.25, "min_agreement": 0.25}),
        ("Risk 28% + CB3", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.28, "min_agreement": 0.25}),
        ("Risk 30% + CB3", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.30, "min_agreement": 0.25}),
        ("Risk 28% + CB4", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.28, "min_agreement": 0.25}),
        ("Risk 30% + CB4", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.30, "min_agreement": 0.25}),
        ("Risk 32% + CB4", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.32, "min_agreement": 0.25}),
        ("Risk 30% + CB5", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 5, "max_risk": 0.30, "min_agreement": 0.25}),
        ("Risk 35% + CB4 + h12", {"bad_hours": {12, 19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.35, "min_agreement": 0.25}),
        ("Risk 30% + no CB", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 99, "max_risk": 0.30, "min_agreement": 0.25}),
        ("Risk 28% + no CB", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 99, "max_risk": 0.28, "min_agreement": 0.25}),
    ]

    best_pnl = -999; best_name = None; best_results = None

    for name, cfg in configs:
        t0 = time.time()
        pnl, trades, prof, results = run_config(all_data, signals, cfg)
        el = time.time() - t0
        m = "+" if pnl > 0 else ""
        print(f"  {name:40} | {trades:4} trades | {prof:2}/{len(results)} prof | ${m}{pnl:.2f} ({el:.1f}s)")
        if pnl > best_pnl:
            best_pnl = pnl; best_name = name; best_results = results

    print("\n" + "=" * 70)
    print(f"  BEST: {best_name}")
    print(f"  P&L: ${best_pnl:+.2f}")
    print("=" * 70)

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

    fn = DATA_DIR / f"optimization_round3_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({"config": best_name, "total_pnl": best_pnl, "results": best_results}, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
