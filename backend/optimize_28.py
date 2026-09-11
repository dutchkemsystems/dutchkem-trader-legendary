import os
"""
Full 28-Instrument Optimization (Fast)
=======================================
Pre-computes analyst signals, then runs filter optimization in pure Python.
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
from apps.vision import ChartAnalyzer
from execution.kelly_sizer import KellySizer

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")
DATA_DIR = Path("paper_trades")
DATA_DIR.mkdir(exist_ok=True)

SYMBOLS_28 = [
    "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY",
    "EURGBP", "EURCHF",
    "XAUUSD", "XAGUSD",
    "BTCUSD", "ETHUSD",
    "US30", "US500", "UK100",
    "AAPL", "AMZN", "NVDA", "TSLA", "META", "MSFT", "GOOGL", "AMD",
]


def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"MT5 FAILED: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    print(f"MT5: {info.login} | {info.server} | ${info.balance}")
    return True


def fetch_candles_mt5(symbol, num_candles=1500):
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    if not info.visible:
        mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, num_candles)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return df


def add_indicators(df):
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
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
    """Run analysts ONCE per symbol, return their static signal."""
    async def _run():
        tasks = [a.analyze(symbol, "1H") for a in analysts]
        return await asyncio.gather(*tasks, return_exceptions=True)

    try:
        results = asyncio.run(_run())
    except Exception:
        results = []
    valid = [r for r in results if hasattr(r, "signal")]
    buy = sum(1 for r in valid if r.signal == "BUY")
    sell = sum(1 for r in valid if r.signal == "SELL")
    total = max(len(valid), 1)
    directional = buy + sell

    if directional == 0:
        return "HOLD", 0.0, 0.5
    if buy > sell:
        return "BUY", directional / total, buy / directional
    elif sell > buy:
        return "SELL", directional / total, sell / directional
    return "HOLD", 0.0, 0.5


def backtest_fast(candles, action, agreement, filters_config):
    """Ultra-fast backtest: analysts return same signal for entire symbol."""
    lookback = 50
    balance = 10000.0
    position = None
    trades = []
    consecutive_losses = 0
    kelly = KellySizer()
    kelly_frac = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)

    bad_hours = filters_config.get("bad_hours", {19, 22})
    bad_days = filters_config.get("bad_days", set())
    cb_limit = filters_config.get("circuit_breaker", 3)
    min_agree = filters_config.get("min_agreement", 0.25)
    max_risk = filters_config.get("max_risk", 0.25)

    if action == "HOLD" or agreement < min_agree:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "pnl": 0, "filtered": 0}

    filtered = 0
    for i in range(lookback, len(candles)):
        current_price = float(candles.iloc[i]["close"])
        current_hour = candles.index[i].hour
        current_dow = candles.index[i].dayofweek

        # Close position
        if position is not None:
            bars_held = i - position["entry_bar"]
            if bars_held >= 5:
                if position["action"] == "BUY":
                    pnl = (current_price - position["entry_price"]) / position["entry_price"] * position["size"]
                else:
                    pnl = (position["entry_price"] - current_price) / position["entry_price"] * position["size"]
                balance += pnl
                trades.append(pnl)
                consecutive_losses = consecutive_losses + 1 if pnl <= 0 else 0
                position = None

        # Open position
        if position is None:
            skip = False
            if consecutive_losses >= cb_limit:
                skip = True; filtered += 1
            elif current_hour in bad_hours:
                skip = True; filtered += 1
            elif current_dow in bad_days:
                skip = True; filtered += 1

            if not skip and action in ("BUY", "SELL"):
                size = max(10, kelly_frac * balance * max_risk)
                if 0 < size <= balance:
                    position = {
                        "action": action, "entry_price": current_price,
                        "entry_bar": i, "size": min(size, balance * 0.2),
                    }

    wins = sum(1 for p in trades if p > 0)
    total_pnl = sum(trades)
    return {
        "trades": len(trades), "wins": wins, "losses": len(trades) - wins,
        "win_rate": wins / len(trades) if trades else 0,
        "pnl": total_pnl, "filtered": filtered,
    }


def main():
    print("=" * 70)
    print("  DUTCHKEM TRADER - 28-INSTRUMENT OPTIMIZATION (FAST)")
    print("=" * 70)

    if not connect_mt5():
        return

    # Fetch data
    print(f"\nFetching data for {len(SYMBOLS_28)} symbols...")
    all_data = {}
    for sym in SYMBOLS_28:
        df = fetch_candles_mt5(sym, 1500)
        if df is not None and len(df) > 100:
            df = add_indicators(df)
            df = df.dropna()
            all_data[sym] = df
            print(f"  {sym:10} {len(df):5} candles")
        else:
            print(f"  {sym:10} SKIPPED")

    mt5.shutdown()
    print(f"\n  Got data for {len(all_data)}/{len(SYMBOLS_28)} symbols")

    # Pre-compute analyst signals
    print("\nPre-computing analyst signals...")
    analysts = [MarketAnalyst(), QuantAnalyst(), RiskAnalyst(), ComplianceAnalyst()]
    symbol_signals = {}
    for sym in all_data:
        action, agreement, confidence = precompute_signals(analysts, sym)
        symbol_signals[sym] = (action, agreement, confidence)
        print(f"  {sym:10} -> {action:5} agree={agreement:.0%} conf={confidence:.2f}")

    # ─── Optimization ───
    print("\n" + "=" * 70)
    print("  OPTIMIZATION: Testing filter combinations")
    print("=" * 70)

    base = {
        "bad_hours": {19, 22}, "bad_days": set(), "circuit_breaker": 3,
        "min_agreement": 0.25, "max_risk": 0.25,
    }

    configs = [
        ("Base (CB3, h19/22)", base),
        ("+Tue bad day", {**base, "bad_days": {1}}),
        ("+h16 bad", {**base, "bad_hours": {16, 19, 22}}),
        ("CB=2", {**base, "circuit_breaker": 2}),
        ("CB=5", {**base, "circuit_breaker": 5}),
        ("No CB", {**base, "circuit_breaker": 99}),
        ("Agree>=30%", {**base, "min_agreement": 0.30}),
        ("Risk=15%", {**base, "max_risk": 0.15}),
        ("Risk=50%", {**base, "max_risk": 0.50}),
        ("Bad hours 12,16,19,22", {**base, "bad_hours": {12, 16, 19, 22}}),
        ("CB=4 + bad h16/19/22", {**base, "circuit_breaker": 4, "bad_hours": {16, 19, 22}}),
        ("CB=3 + bad h12/14/16/19/22", {**base, "circuit_breaker": 3, "bad_hours": {12, 14, 16, 19, 22}}),
        ("Risk=35% + CB4", {**base, "max_risk": 0.35, "circuit_breaker": 4}),
        ("Risk=40% + No CB", {**base, "max_risk": 0.40, "circuit_breaker": 99}),
    ]

    best_pnl = -999
    best_config = None
    best_results = None

    for name, config in configs:
        t0 = time.time()
        results = {}
        for sym, df in all_data.items():
            action, agreement, conf = symbol_signals[sym]
            r = backtest_fast(df, action, agreement, config)
            r["symbol"] = sym
            results[sym] = r

        total_pnl = sum(r["pnl"] for r in results.values())
        total_trades = sum(r["trades"] for r in results.values())
        profitable = sum(1 for r in results.values() if r["pnl"] > 0)
        elapsed = time.time() - t0

        marker = "+" if total_pnl > 0 else ""
        print(f"\n  {name} ({elapsed:.1f}s)")
        print(f"    Trades: {total_trades} | Profitable: {profitable}/{len(results)} | P&L: ${marker}{total_pnl:.2f}")

        if total_pnl > best_pnl:
            best_pnl = total_pnl
            best_config = (name, config)
            best_results = results

    # ─── Final Results ───
    print("\n" + "=" * 70)
    print(f"  BEST CONFIG: {best_config[0]}")
    print(f"  BEST P&L: ${best_pnl:+.2f}")
    print("=" * 70)

    # Top profitable
    profitable = sorted(best_results.items(), key=lambda x: -x[1]["pnl"])
    print(f"\n  TOP PROFITABLE:")
    for sym, r in profitable[:10]:
        if r["pnl"] > 0:
            print(f"    {sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${r['pnl']:+.2f}")

    # All results
    print(f"\n  ALL RESULTS:")
    for sym, r in profitable:
        print(f"    {sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${r['pnl']:+.2f}")

    total_trades = sum(r["trades"] for r in best_results.values())
    total_wins = sum(r["wins"] for r in best_results.values())
    overall_wr = total_wins / total_trades if total_trades > 0 else 0
    n_profitable = sum(1 for r in best_results.values() if r["pnl"] > 0)

    print(f"\n  PORTFOLIO SUMMARY:")
    print(f"    Symbols: {len(best_results)}")
    print(f"    Total trades: {total_trades}")
    print(f"    Win rate: {overall_wr:.1%}")
    print(f"    Total P&L: ${best_pnl:+.2f}")
    print(f"    Profitable: {n_profitable}/{len(best_results)}")
    target_gap = 50 - best_pnl
    print(f"    Target $50: {'ACHIEVED!' if best_pnl >= 50 else f'Need ${target_gap:.2f} more'}")

    # Save
    output = {
        "config": best_config[0],
        "filters": {k: list(v) if isinstance(v, set) else v for k, v in best_config[1].items()},
        "total_pnl": best_pnl,
        "results": best_results,
        "signals": {sym: {"action": a, "agreement": g} for sym, (a, g, c) in symbol_signals.items()},
    }
    filename = DATA_DIR / f"optimization_28_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {filename}")


if __name__ == "__main__":
    main()
