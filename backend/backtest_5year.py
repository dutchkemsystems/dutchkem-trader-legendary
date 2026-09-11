import os
"""
DUTCHKEM TRADER - 5-YEAR BACKTEST
===================================
Full 5-year historical backtest on 15 optimized symbols.
Config: 30% risk, AMD 3x weight, no circuit breaker, min confidence 0.30.

Uses ATR-based SL/TP for realistic trade management.

Reports:
- Total P&L, win rate, profit factor
- Max drawdown, Sharpe ratio, Sortino ratio
- Monthly P&L breakdown
- Per-symbol performance
- Equity curve data
"""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")

# ═══════════════════════════════════════════════════════════════
# OPTIMIZED PRODUCTION CONFIG
# ═══════════════════════════════════════════════════════════════
SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURGBP",
    "XAUUSD",
    "US30",
    "AMD", "GOOGL",
]

CONFIG = {
    "max_risk": 0.30,           # 30% risk per trade
    "min_confidence": 0.30,     # Minimum signal confidence
    "sym_weights": {"AMD": 3.0, "GOOGL": 1.0},  # AMD gets 3x position size
    "sl_atr_mult": 1.5,        # Stop-loss = 1.5x ATR
    "tp_atr_mult": 2.5,        # Take-profit = 2.5x ATR
    "max_bars_held": 48,       # Max 48 hours hold (time-based exit)
    "trailing_breakeven": 0.005,  # Move SL to breakeven after +0.5%
}

INITIAL_BALANCE = 10000.0
BARS_NEEDED = 13000  # ~5 years of H1 data (252 days * 5 * ~10 H1 bars/day)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════
def load_data():
    """Load 5 years of H1 data from MT5 for all symbols."""
    print("  Connecting to MT5...")
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("  ERROR: MT5 connection failed")
        return {}

    all_data = {}
    for sym in SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  SKIP {sym}: not found")
            continue
        if not info.visible:
            mt5.symbol_select(sym, True)

        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, BARS_NEEDED)
        if rates is None or len(rates) < 500:
            print(f"  SKIP {sym}: only {len(rates) if rates is not None else 0} bars")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]

        # Compute indicators
        c = df["close"].values.astype(float)
        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)

        df["sma_20"] = pd.Series(c).rolling(20).mean().values
        df["sma_50"] = pd.Series(c).rolling(50).mean().values
        df["ema_12"] = pd.Series(c).ewm(span=12).mean().values
        df["ema_26"] = pd.Series(c).ewm(span=26).mean().values
        df["macd"] = df["ema_12"] - df["ema_26"]
        df["macd_signal"] = pd.Series(df["macd"]).ewm(span=9).mean().values
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # RSI
        deltas = np.diff(c, prepend=c[0])
        gains = np.where(deltas > 0, deltas, 0)
        losses_arr = np.where(deltas < 0, -deltas, 0)
        avg_gain = pd.Series(gains).ewm(span=14, adjust=False).mean().values
        avg_loss = pd.Series(losses_arr).ewm(span=14, adjust=False).mean().values
        rs = np.where(avg_loss > 1e-10, avg_gain / avg_loss, 100)
        df["rsi"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        bb_std = pd.Series(c).rolling(20).std().values
        df["bb_upper"] = df["sma_20"] + 2 * bb_std
        df["bb_lower"] = df["sma_20"] - 2 * bb_std

        # ATR
        prev_c = np.roll(c, 1)
        prev_c[0] = c[0]
        tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
        df["atr"] = pd.Series(tr).rolling(14).mean().values

        # Momentum
        df["momentum_5"] = pd.Series(c).pct_change(5).values

        df = df.dropna()
        all_data[sym] = df
        print(f"  {sym:10} {len(df):5} bars | {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")

    mt5.shutdown()
    return all_data


# ═══════════════════════════════════════════════════════════════
# SIGNAL GENERATION (same as optimized rounds)
# ═══════════════════════════════════════════════════════════════
def generate_signal(row):
    score = 0
    if row["macd_hist"] > 0:
        score += 1
    elif row["macd_hist"] < 0:
        score -= 1

    if row["rsi"] < 35:
        score += 2
    elif row["rsi"] < 45:
        score += 1
    elif row["rsi"] > 65:
        score -= 2
    elif row["rsi"] > 55:
        score -= 1

    if row["close"] > row["sma_20"] > row["sma_50"]:
        score += 2
    elif row["close"] < row["sma_20"] < row["sma_50"]:
        score -= 2

    if row["momentum_5"] > 0.005:
        score += 1
    elif row["momentum_5"] < -0.005:
        score -= 1

    if row["close"] < row["bb_lower"]:
        score += 1
    elif row["close"] > row["bb_upper"]:
        score -= 1

    if score >= 3:
        return "BUY", min(score / 6.0, 1.0)
    if score <= -3:
        return "SELL", min(abs(score) / 6.0, 1.0)
    return "HOLD", 0.0


# ═══════════════════════════════════════════════════════════════
# BACKTEST ENGINE (with ATR-based SL/TP)
# ═══════════════════════════════════════════════════════════════
def backtest(all_data, cfg):
    """
    Full backtest with ATR-based SL/TP, trailing stop, and position sizing.
    Returns detailed results including equity curve and monthly breakdown.
    """
    risk = cfg["max_risk"]
    sym_weights = cfg.get("sym_weights", {})
    min_conf = cfg.get("min_confidence", 0.30)
    sl_mult = cfg.get("sl_atr_mult", 1.5)
    tp_mult = cfg.get("tp_atr_mult", 2.5)
    max_hold = cfg.get("max_bars_held", 48)
    be_trigger = cfg.get("trailing_breakeven", 0.005)

    balance = INITIAL_BALANCE
    peak_balance = balance
    max_drawdown = 0
    max_dd_pct = 0

    all_trades = []
    equity_curve = [(datetime(2021, 9, 1), balance)]
    monthly_pnl = {}

    for sym, df in all_data.items():
        pos = None
        w = sym_weights.get(sym, 1.0)

        for i in range(50, len(df)):
            row = df.iloc[i]
            px = float(row["close"])
            high_px = float(row["high"])
            low_px = float(row["low"])
            atr_val = float(row["atr"])
            ts = df.index[i]

            # --- Manage open position ---
            if pos is not None:
                bars_held = i - pos["entry_bar"]

                # Update trailing SL
                if pos["direction"] == "BUY":
                    unrealized = (px - pos["entry_px"]) / pos["entry_px"]
                    # Move to breakeven after trigger
                    if unrealized >= be_trigger and pos["sl"] < pos["entry_px"]:
                        pos["sl"] = pos["entry_px"]
                    # Trailing stop
                    new_sl = px - sl_mult * atr_val
                    if new_sl > pos["sl"]:
                        pos["sl"] = new_sl

                    # Check SL hit
                    if low_px <= pos["sl"]:
                        pnl = (pos["sl"] - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({
                            "sym": sym, "dir": "BUY", "entry": pos["entry_px"],
                            "exit": pos["sl"], "pnl": pnl, "bars": bars_held,
                            "exit_reason": "SL", "time": ts,
                        })
                        pos = None
                        continue

                    # Check TP hit
                    if high_px >= pos["tp"]:
                        pnl = (pos["tp"] - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({
                            "sym": sym, "dir": "BUY", "entry": pos["entry_px"],
                            "exit": pos["tp"], "pnl": pnl, "bars": bars_held,
                            "exit_reason": "TP", "time": ts,
                        })
                        pos = None
                        continue

                elif pos["direction"] == "SELL":
                    unrealized = (pos["entry_px"] - px) / pos["entry_px"]
                    if unrealized >= be_trigger and pos["sl"] > pos["entry_px"]:
                        pos["sl"] = pos["entry_px"]
                    new_sl = px + sl_mult * atr_val
                    if new_sl < pos["sl"]:
                        pos["sl"] = new_sl

                    # Check SL hit
                    if high_px >= pos["sl"]:
                        pnl = (pos["entry_px"] - pos["sl"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({
                            "sym": sym, "dir": "SELL", "entry": pos["entry_px"],
                            "exit": pos["sl"], "pnl": pnl, "bars": bars_held,
                            "exit_reason": "SL", "time": ts,
                        })
                        pos = None
                        continue

                    # Check TP hit
                    if low_px <= pos["tp"]:
                        pnl = (pos["entry_px"] - pos["tp"]) / pos["entry_px"] * pos["size"]
                        balance += pnl
                        all_trades.append({
                            "sym": sym, "dir": "SELL", "entry": pos["entry_px"],
                            "exit": pos["tp"], "pnl": pnl, "bars": bars_held,
                            "exit_reason": "TP", "time": ts,
                        })
                        pos = None
                        continue

                # Time-based exit
                if bars_held >= max_hold:
                    if pos["direction"] == "BUY":
                        pnl = (px - pos["entry_px"]) / pos["entry_px"] * pos["size"]
                    else:
                        pnl = (pos["entry_px"] - px) / pos["entry_px"] * pos["size"]
                    balance += pnl
                    all_trades.append({
                        "sym": sym, "dir": pos["direction"], "entry": pos["entry_px"],
                        "exit": px, "pnl": pnl, "bars": bars_held,
                        "exit_reason": "TIME", "time": ts,
                    })
                    pos = None
                    continue

                continue  # Still holding, don't enter new

            # --- Check for new entry ---
            action, conf = generate_signal(row)
            if action in ("BUY", "SELL") and conf >= min_conf:
                base_sz = risk * balance
                sz = max(10, base_sz * w)

                # Cap at 30% of balance
                sz = min(sz, balance * 0.30)

                if sz > 0 and sz <= balance:
                    if action == "BUY":
                        sl_px = px - sl_mult * atr_val
                        tp_px = px + tp_mult * atr_val
                    else:
                        sl_px = px + sl_mult * atr_val
                        tp_px = px - tp_mult * atr_val

                    pos = {
                        "direction": action,
                        "entry_px": px,
                        "entry_bar": i,
                        "sl": sl_px,
                        "tp": tp_px,
                        "size": sz,
                        "confidence": conf,
                    }

            # Track equity
            if i % 24 == 0:  # Daily
                equity_curve.append((ts.to_pydatetime(), balance))

            # Drawdown tracking
            if balance > peak_balance:
                peak_balance = balance
            dd = peak_balance - balance
            dd_pct = dd / peak_balance if peak_balance > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            # Monthly tracking
            month_key = ts.strftime("%Y-%m")
            if month_key not in monthly_pnl:
                monthly_pnl[month_key] = 0

    # Close any remaining position at market
    if pos is not None:
        px = float(df.iloc[-1]["close"])
        if pos["direction"] == "BUY":
            pnl = (px - pos["entry_px"]) / pos["entry_px"] * pos["size"]
        else:
            pnl = (pos["entry_px"] - px) / pos["entry_px"] * pos["size"]
        balance += pnl
        all_trades.append({
            "sym": sym, "dir": pos["direction"], "entry": pos["entry_px"],
            "exit": px, "pnl": pnl, "bars": len(df) - 1 - pos["entry_bar"],
            "exit_reason": "EOD", "time": df.index[-1],
        })

    # Compute monthly P&L from trades
    for t in all_trades:
        if t["time"] is not None:
            mk = pd.Timestamp(t["time"]).strftime("%Y-%m")
            monthly_pnl[mk] = monthly_pnl.get(mk, 0) + t["pnl"]

    return {
        "trades": all_trades,
        "final_balance": balance,
        "total_pnl": balance - INITIAL_BALANCE,
        "total_return_pct": (balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_dd_pct * 100,
        "equity_curve": equity_curve,
        "monthly_pnl": monthly_pnl,
        "num_trades": len(all_trades),
    }


# ═══════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════
def generate_report(result):
    """Generate full backtest report."""
    trades = result["trades"]
    fb = result["final_balance"]
    tp = result["total_pnl"]
    tr = result["total_return_pct"]
    mdd = result["max_drawdown"]
    mdd_pct = result["max_drawdown_pct"]
    mp = result["monthly_pnl"]

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) if trades else 0

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    expectancy = tp / len(trades) if trades else 0

    # Sharpe ratio (using monthly returns)
    monthly_vals = list(mp.values())
    if len(monthly_vals) > 1:
        monthly_ret = np.array(monthly_vals) / INITIAL_BALANCE
        sharpe = (np.mean(monthly_ret) / np.std(monthly_ret)) * np.sqrt(12) if np.std(monthly_ret) > 0 else 0
        sortino_denom = np.std([r for r in monthly_ret if r < 0]) if any(r < 0 for r in monthly_ret) else 1e-10
        sortino = (np.mean(monthly_ret) / sortino_denom) * np.sqrt(12)
    else:
        sharpe = 0
        sortino = 0

    # Consecutive wins/losses
    max_consec_win = 0; max_consec_loss = 0; cw = 0; cl = 0
    for t in trades:
        if t["pnl"] > 0:
            cw += 1; cl = 0
        else:
            cl += 1; cw = 0
        max_consec_win = max(max_consec_win, cw)
        max_consec_loss = max(max_consec_loss, cl)

    # Per-symbol
    sym_stats = {}
    for t in trades:
        s = t["sym"]
        if s not in sym_stats:
            sym_stats[s] = {"trades": 0, "wins": 0, "pnl": 0, "sl": 0, "tp": 0, "time": 0}
        sym_stats[s]["trades"] += 1
        sym_stats[s]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            sym_stats[s]["wins"] += 1
        if t["exit_reason"] == "SL":
            sym_stats[s]["sl"] += 1
        elif t["exit_reason"] == "TP":
            sym_stats[s]["tp"] += 1
        else:
            sym_stats[s]["time"] += 1

    # Monthly sorted
    sorted_months = sorted(mp.items())

    # Print report
    print()
    print("=" * 80)
    print("  DUTCHKEM TRADER - 5-YEAR BACKTEST REPORT")
    print("  Config: 30% risk | AMD 3x | No circuit breaker | ATR-based SL/TP")
    print("=" * 80)

    print(f"\n  {'PERFORMANCE SUMMARY':^80}")
    print(f"  {'-' * 60}")
    print(f"  Initial Balance:     ${INITIAL_BALANCE:>12,.2f}")
    print(f"  Final Balance:       ${fb:>12,.2f}")
    print(f"  Total P&L:           ${tp:>+12,.2f}")
    print(f"  Total Return:        {tr:>+11.1f}%")
    print(f"  Max Drawdown:        ${mdd:>12,.2f} ({mdd_pct:.1f}%)")
    print(f"  Sharpe Ratio:        {sharpe:>12.2f}")
    print(f"  Sortino Ratio:       {sortino:>12.2f}")
    print(f"  Profit Factor:       {profit_factor:>12.2f}")

    print(f"\n  {'TRADE STATISTICS':^80}")
    print(f"  {'-' * 60}")
    print(f"  Total Trades:        {len(trades):>12}")
    print(f"  Winning Trades:      {len(wins):>12} ({win_rate:.1%})")
    print(f"  Losing Trades:       {len(losses):>12} ({1 - win_rate:.1%})")
    print(f"  Avg Win:             ${avg_win:>12,.2f}")
    print(f"  Avg Loss:            ${avg_loss:>12,.2f}")
    print(f"  Avg P&L/Trade:       ${expectancy:>12,.2f}")
    print(f"  Max Consec Wins:     {max_consec_win:>12}")
    print(f"  Max Consec Losses:   {max_consec_loss:>12}")

    print(f"\n  {'EXIT REASON BREAKDOWN':^80}")
    print(f"  {'-' * 60}")
    sl_count = sum(1 for t in trades if t["exit_reason"] == "SL")
    tp_count = sum(1 for t in trades if t["exit_reason"] == "TP")
    time_count = sum(1 for t in trades if t["exit_reason"] == "TIME")
    print(f"  Take-Profit exits:   {tp_count:>8} ({tp_count/len(trades)*100:.1f}%)")
    print(f"  Stop-Loss exits:     {sl_count:>8} ({sl_count/len(trades)*100:.1f}%)")
    print(f"  Time-based exits:    {time_count:>8} ({time_count/len(trades)*100:.1f}%)")

    print(f"\n  {'PER-SYMBOL PERFORMANCE':^80}")
    print(f"  {'-' * 60}")
    print(f"  {'Symbol':<12} {'Trades':>6} {'Wins':>6} {'WR':>7} {'P&L':>12} {'SL':>5} {'TP':>5} {'Time':>5}")
    print(f"  {'-' * 60}")
    for sym, st in sorted(sym_stats.items(), key=lambda x: -x[1]["pnl"]):
        wr = st["wins"] / st["trades"] if st["trades"] > 0 else 0
        m = "+" if st["pnl"] > 0 else ""
        print(f"  {sym:<12} {st['trades']:>6} {st['wins']:>6} {wr:>6.0%} ${m}{st['pnl']:>10,.2f} {st['sl']:>5} {st['tp']:>5} {st['time']:>5}")

    print(f"\n  {'MONTHLY PERFORMANCE':^80}")
    print(f"  {'-' * 60}")
    print(f"  {'Month':<10} {'P&L':>12} {'Cumulative':>14}")
    print(f"  {'-' * 60}")
    cumul = 0
    for month, pnl in sorted_months:
        cumul += pnl
        m = "+" if pnl > 0 else ""
        mc = "+" if cumul > 0 else ""
        print(f"  {month:<10} ${m}{pnl:>10,.2f}  ${mc}{cumul:>12,.2f}")

    # Yearly summary
    print(f"\n  {'YEARLY SUMMARY':^80}")
    print(f"  {'-' * 60}")
    yearly = {}
    for month, pnl in sorted_months:
        y = month[:4]
        yearly[y] = yearly.get(y, 0) + pnl
    for year, pnl in sorted(yearly.items()):
        m = "+" if pnl > 0 else ""
        print(f"  {year}:  ${m}{pnl:>10,.2f}  ({pnl / INITIAL_BALANCE * 100:>+6.1f}%)")

    print(f"\n{'=' * 80}")
    print(f"  VERDICT: ", end="")
    if tp > 0 and win_rate >= 0.48 and profit_factor >= 1.1:
        print("PROFITABLE - Strategy shows edge over 5 years")
    elif tp > 0:
        print("MARGINALLY PROFITABLE - Edge exists but thin")
    else:
        print("NOT PROFITABLE - Strategy needs refinement")

    print(f"  {'=' * 80}")

    return {
        "summary": {
            "initial_balance": INITIAL_BALANCE,
            "final_balance": fb,
            "total_pnl": tp,
            "total_return_pct": tr,
            "max_drawdown": mdd,
            "max_drawdown_pct": mdd_pct,
            "sharpe": sharpe,
            "sortino": sortino,
            "profit_factor": profit_factor,
        },
        "trades": {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
        },
        "symbol_stats": sym_stats,
        "yearly": yearly,
        "monthly_pnl": mp,
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 80)
    print("  DUTCHKEM TRADER - 5-YEAR BACKTEST")
    print("  Config: Risk 30% | AMD 3x | No CB | ATR SL 1.5x / TP 2.5x")
    print("  Symbols: 15 optimized | Timeframe: H1 | Period: 5 years")
    print("=" * 80)

    # Load data
    all_data = load_data()
    if not all_data:
        print("  ERROR: No data loaded. Exiting.")
        return

    print(f"\n  Loaded {len(all_data)} symbols")

    # Run backtest
    print("\n  Running backtest...")
    result = backtest(all_data, CONFIG)

    # Generate report
    report = generate_report(result)

    # Save to JSON
    fn = Path("paper_trades") / f"backtest_5yr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w") as f:
        json.dump({
            "config": CONFIG,
            "initial_balance": INITIAL_BALANCE,
            "symbols": SYMBOLS,
            "report": report,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2, default=str)
    print(f"\n  Saved report to {fn}")


if __name__ == "__main__":
    main()
