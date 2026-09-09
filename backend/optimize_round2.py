"""
Round 2 Optimization: Per-Symbol Sizing + Directional Filtering
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
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"
DATA_DIR = Path("paper_trades")

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
        return "HOLD", 0.0
    if buy > sell:
        return "BUY", directional / total
    elif sell > buy:
        return "SELL", directional / total
    return "HOLD", 0.0


def backtest_fast(candles, action, agreement, config):
    lookback = 50
    balance = 10000.0
    position = None
    trades = []
    consecutive_losses = 0
    kelly = KellySizer()
    kelly_frac = kelly.calculate(win_rate=0.55, avg_win=1.5, avg_loss=1.0)

    bad_hours = config.get("bad_hours", {19, 22})
    bad_days = config.get("bad_days", set())
    cb_limit = config.get("circuit_breaker", 3)
    min_agree = config.get("min_agreement", 0.25)
    risk_pct = config.get("max_risk", 0.25)

    if action == "HOLD" or agreement < min_agree:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "pnl": 0}

    for i in range(lookback, len(candles)):
        price = float(candles.iloc[i]["close"])
        hour = candles.index[i].hour
        dow = candles.index[i].dayofweek

        if position is not None:
            if i - position["bar"] >= 5:
                if position["act"] == "BUY":
                    pnl = (price - position["px"]) / position["px"] * position["sz"]
                else:
                    pnl = (position["px"] - price) / position["px"] * position["sz"]
                balance += pnl
                trades.append(pnl)
                consecutive_losses = consecutive_losses + 1 if pnl <= 0 else 0
                position = None

        if position is None:
            skip = (consecutive_losses >= cb_limit) or (hour in bad_hours) or (dow in bad_days)
            if not skip and action in ("BUY", "SELL"):
                size = max(10, kelly_frac * balance * risk_pct)
                if 0 < size <= balance:
                    position = {"act": action, "px": price, "bar": i, "sz": min(size, balance * 0.3)}

    wins = sum(1 for p in trades if p > 0)
    return {"trades": len(trades), "wins": wins, "losses": len(trades) - wins,
            "win_rate": wins / len(trades) if trades else 0, "pnl": sum(trades)}


def main():
    print("=" * 70)
    print("  ROUND 2: PER-SYMBOL OPTIMIZATION + DIRECTIONAL FILTERING")
    print("=" * 70)

    if not connect_mt5():
        return

    print(f"\nFetching data for {len(SYMBOLS_28)} symbols...")
    all_data = {}
    for sym in SYMBOLS_28:
        df = fetch_candles_mt5(sym, 1500)
        if df is not None and len(df) > 100:
            df = add_indicators(df)
            df = df.dropna()
            all_data[sym] = df
            print(f"  {sym:10} {len(df):5} candles")
    mt5.shutdown()

    analysts = [MarketAnalyst(), QuantAnalyst(), RiskAnalyst(), ComplianceAnalyst()]
    print("\nPre-computing signals...")
    signals = {}
    for sym in all_data:
        action, agreement = precompute_signals(analysts, sym)
        signals[sym] = (action, agreement)
        print(f"  {sym:10} -> {action:5} agree={agreement:.0%}")

    # ─── Strategy: Filter losing BUY signals, boost winners ───
    print("\n" + "=" * 70)
    print("  STRATEGY: Directional + Risk Optimization")
    print("=" * 70)

    # Round 1 winners (keep): META SELL, XAUUSD SELL, ETHUSD SELL, NZDUSD SELL
    # Round 1 losers (filter): BTCUSD BUY, TSLA BUY, MSFT BUY, NVDA SELL
    # Try: No crypto (BTCUSD, ETHUSD), no high-vol stocks

    configs = [
        ("All 27 (baseline)", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.25, "min_agreement": 0.25}),
        ("No crypto", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.25, "min_agreement": 0.25, "skip_symbols": {"BTCUSD", "ETHUSD"}}),
        ("No crypto, no stocks", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.25, "min_agreement": 0.25, "skip_symbols": {"BTCUSD", "ETHUSD", "AAPL", "AMZN", "NVDA", "TSLA", "META", "MSFT", "GOOGL", "AMD"}}),
        ("Forex+Metals only", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 3, "max_risk": 0.30, "min_agreement": 0.25, "only_symbols": {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "EURGBP", "EURCHF", "XAUUSD", "XAGUSD"}}),
        ("High-risk winners (35%)", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.35, "min_agreement": 0.25}),
        ("High-risk (40%) + CB4", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 4, "max_risk": 0.40, "min_agreement": 0.25}),
        ("Risk 45% + CB5", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 5, "max_risk": 0.45, "min_agreement": 0.25}),
        ("Risk 50% + CB5", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 5, "max_risk": 0.50, "min_agreement": 0.25}),
        ("No CB + Risk 30%", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 99, "max_risk": 0.30, "min_agreement": 0.25}),
        ("No CB + Risk 50%", {"bad_hours": {19, 22}, "bad_days": {1}, "circuit_breaker": 99, "max_risk": 0.50, "min_agreement": 0.25}),
    ]

    best_pnl = -999
    best_config_name = None
    best_results = None

    for name, config in configs:
        t0 = time.time()
        results = {}
        skip_syms = config.get("skip_symbols", set())
        only_syms = config.get("only_symbols", set())

        for sym, df in all_data.items():
            if sym in skip_syms:
                continue
            if only_syms and sym not in only_syms:
                continue
            action, agreement = signals[sym]
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
            best_config_name = name
            best_results = results

    # ─── Final ───
    print("\n" + "=" * 70)
    print(f"  BEST: {best_config_name}")
    print(f"  P&L: ${best_pnl:+.2f}")
    print("=" * 70)

    for sym, r in sorted(best_results.items(), key=lambda x: -x[1]["pnl"]):
        if r["pnl"] > 0:
            print(f"  +{sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${r['pnl']:+.2f}")
    for sym, r in sorted(best_results.items(), key=lambda x: -x[1]["pnl"]):
        if r["pnl"] <= 0 and r["trades"] > 0:
            print(f"  -{sym:10} {r['trades']:4} trades | WR={r['win_rate']:.0%} | P&L=${r['pnl']:+.2f}")

    total_trades = sum(r["trades"] for r in best_results.values())
    total_wins = sum(r["wins"] for r in best_results.values())
    wr = total_wins / total_trades if total_trades > 0 else 0
    n_prof = sum(1 for r in best_results.values() if r["pnl"] > 0)

    print(f"\n  PORTFOLIO: {total_trades} trades | WR={wr:.1%} | P&L=${best_pnl:+.2f} | {n_prof}/{len(best_results)} profitable")
    print(f"  Target $50: {'ACHIEVED!' if best_pnl >= 50 else f'Need ${50-best_pnl:.2f} more'}")

    # Save
    output = {"config": best_config_name, "total_pnl": best_pnl, "results": best_results}
    fn = DATA_DIR / f"optimization_round2_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved to {fn}")


if __name__ == "__main__":
    main()
