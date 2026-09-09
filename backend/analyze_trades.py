"""
Trade Failure Analysis
======================
Analyze the 1358 backtest trades to find patterns in losses.
"""
import os, sys, json
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter

DATA_DIR = Path("paper_trades")


def load_latest_backtest():
    """Load the most recent backtest results."""
    files = sorted(DATA_DIR.glob("backtest_*.json"), reverse=True)
    if not files:
        print("No backtest files found!")
        return None
    print(f"Loading {files[0]}")
    with open(files[0]) as f:
        return json.load(f)


def analyze_trades(results):
    """Deep analysis of all trades."""
    all_trades = []
    for r in results:
        for t in r["trades"]:
            t["symbol"] = r["symbol"]
            t["pnl_pct"] = t.get("pnl_pct", 0)
            all_trades.append(t)

    df = pd.DataFrame(all_trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["hour"] = df["entry_time"].dt.hour
    df["day_of_week"] = df["entry_time"].dt.dayofweek
    df["is_win"] = df["pnl"] > 0
    df["abs_pnl"] = df["pnl"].abs()
    df["duration_bars"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 3600

    wins = df[df["is_win"]]
    losses = df[~df["is_win"]]

    print(f"\n{'='*70}")
    print(f"  TRADE FAILURE ANALYSIS")
    print(f"{'='*70}")
    print(f"  Total trades: {len(df)}")
    print(f"  Wins: {len(wins)} ({len(wins)/len(df):.1%}) | Losses: {len(losses)} ({len(losses)/len(df):.1%})")
    print(f"  Total P&L: ${df['pnl'].sum():.2f}")
    print(f"  Avg win: ${wins['pnl'].mean():.3f} | Avg loss: ${losses['pnl'].mean():.3f}")

    # ─── Pattern 1: Losses by Symbol ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 1: Losses by Symbol")
    print(f"{'─'*70}")
    for sym in df["symbol"].unique():
        s = df[df["symbol"] == sym]
        w = s[s["is_win"]]
        l = s[~s["is_win"]]
        wr = len(w) / len(s) if len(s) > 0 else 0
        pnl = s["pnl"].sum()
        avg_loss = l["pnl"].mean() if len(l) > 0 else 0
        print(f"  {sym:8} | {len(s):4} trades | WR: {wr:.1%} | P&L: ${pnl:+.2f} | Avg loss: ${avg_loss:.3f}")

    # ─── Pattern 2: Losses by Hour ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 2: Loss Rate by Hour (UTC)")
    print(f"{'─'*70}")
    for h in range(24):
        hour_df = df[df["hour"] == h]
        if len(hour_df) == 0:
            continue
        hour_losses = hour_df[~hour_df["is_win"]]
        loss_rate = len(hour_losses) / len(hour_df)
        avg_loss = hour_losses["pnl"].mean() if len(hour_losses) > 0 else 0
        bar = "#" * int(loss_rate * 40)
        print(f"  {h:02d}:00 | {len(hour_df):4} trades | Loss: {loss_rate:.1%} | Avg loss: ${avg_loss:+.3f} | {bar}")

    # ─── Pattern 3: Losses by Day of Week ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 3: Loss Rate by Day of Week")
    print(f"{'─'*70}")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for d in range(7):
        day_df = df[df["day_of_week"] == d]
        if len(day_df) == 0:
            continue
        day_losses = day_df[~day_df["is_win"]]
        loss_rate = len(day_losses) / len(day_df)
        print(f"  {days[d]:3} | {len(day_df):4} trades | Loss: {loss_rate:.1%} | P&L: ${day_df['pnl'].sum():+.2f}")

    # ─── Pattern 4: Consecutive Losses ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 4: Consecutive Loss Streaks")
    print(f"{'─'*70}")
    streak = 0
    max_streak = 0
    streak_lengths = []
    for _, row in df.iterrows():
        if not row["is_win"]:
            streak += 1
        else:
            if streak > 0:
                streak_lengths.append(streak)
            streak = 0
    if streak > 0:
        streak_lengths.append(streak)

    if streak_lengths:
        print(f"  Max consecutive losses: {max(streak_lengths)}")
        print(f"  Avg streak length: {np.mean(streak_lengths):.1f}")
        print(f"  Streak distribution: {Counter(streak_lengths)}")

    # ─── Pattern 5: Big Losers Analysis ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 5: Top 20 Biggest Losses")
    print(f"{'─'*70}")
    top_losses = losses.nlargest(20, "abs_pnl")
    print(f"  {'Symbol':8} {'Entry Time':20} {'Act':5} {'Entry':>10} {'Exit':>10} {'P&L':>10} {'Agree':>6}")
    print(f"  {'-'*70}")
    for _, t in top_losses.iterrows():
        print(f"  {t['symbol']:8} {str(t['entry_time'])[:19]:20} {t['action']:5} {t['entry_price']:>10.5f} {t['exit_price']:>10.5f} ${t['pnl']:>+9.3f} {t.get('agreement_pct', 0):>5.0%}")

    # ─── Pattern 6: Win/Loss by Agreement Level ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 6: Win Rate by Agreement Level")
    print(f"{'─'*70}")
    bins = [0, 0.20, 0.30, 0.40, 0.50, 1.01]
    labels = ["0-20%", "20-30%", "30-40%", "40-50%", "50%+"]
    df["agreement_bin"] = pd.cut(df["agreement_pct"], bins=bins, labels=labels, right=False)
    for label in labels:
        subset = df[df["agreement_bin"] == label]
        if len(subset) == 0:
            continue
        wr = subset["is_win"].mean()
        pnl = subset["pnl"].sum()
        print(f"  Agreement {label:>8} | {len(subset):4} trades | WR: {wr:.1%} | P&L: ${pnl:+.2f}")

    # ─── Pattern 7: Market Regime (price direction vs trade direction) ───
    print(f"\n{'─'*70}")
    print(f"  PATTERN 7: Trade Direction vs Market Trend")
    print(f"{'─'*70}")
    # Check if trade made money when price moved in its favor
    for sym in df["symbol"].unique():
        s = df[df["symbol"] == sym]
        buys = s[s["action"] == "BUY"]
        sells = s[s["action"] == "SELL"]
        buy_wr = buys["is_win"].mean() if len(buys) > 0 else 0
        sell_wr = sells["is_win"].mean() if len(sells) > 0 else 0
        print(f"  {sym:8} | BUY: {len(buys)} trades, WR={buy_wr:.1%} | SELL: {len(sells)} trades, WR={sell_wr:.1%}")

    return df


def find_filters(df):
    """Suggest filters based on patterns."""
    print(f"\n{'='*70}")
    print(f"  SUGGESTED FILTERS")
    print(f"{'='*70}")

    filters = []

    # Filter 1: Avoid low-agreement trades
    low_agree = df[df["agreement_pct"] < 0.25]
    if len(low_agree) > 0:
        low_wr = low_agree["is_win"].mean()
        high_agree = df[df["agreement_pct"] >= 0.25]
        high_wr = high_agree["is_win"].mean() if len(high_agree) > 0 else 0
        if low_wr < high_wr:
            filters.append(("min_agreement", 0.25,
                f"Agreement < 25%: WR={low_wr:.1%} vs >=25%: WR={high_wr:.1%}"))

    # Filter 2: Avoid certain hours
    for h in range(24):
        hour_df = df[df["hour"] == h]
        if len(hour_df) >= 10:
            hour_wr = hour_df["is_win"].mean()
            overall_wr = df["is_win"].mean()
            if hour_wr < overall_wr - 0.10:
                filters.append(("avoid_hour", h,
                    f"Hour {h:02d}:00 UTC: WR={hour_wr:.1%} (vs overall {overall_wr:.1%})"))

    # Filter 3: Avoid certain days
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for d in range(7):
        day_df = df[df["day_of_week"] == d]
        if len(day_df) >= 10:
            day_wr = day_df["is_win"].mean()
            overall_wr = df["is_win"].mean()
            if day_wr < overall_wr - 0.10:
                filters.append(("avoid_day", d,
                    f"{days[d]}: WR={day_wr:.1%} (vs overall {overall_wr:.1%})"))

    # Filter 4: Prefer SELL on certain symbols
    for sym in df["symbol"].unique():
        s = df[df["symbol"] == sym]
        buy_wr = s[s["action"] == "BUY"]["is_win"].mean() if len(s[s["action"] == "BUY"]) > 0 else 0
        sell_wr = s[s["action"] == "SELL"]["is_win"].mean() if len(s[s["action"] == "SELL"]) > 0 else 0
        if sell_wr > buy_wr + 0.05:
            filters.append(("prefer_action", f"SELL {sym}",
                f"{sym} SELL WR={sell_wr:.1%} vs BUY WR={buy_wr:.1%}"))
        elif buy_wr > sell_wr + 0.05:
            filters.append(("prefer_action", f"BUY {sym}",
                f"{sym} BUY WR={buy_wr:.1%} vs SELL WR={sell_wr:.1%}"))

    # Filter 5: Avoid consecutive losses (circuit breaker)
    filters.append(("max_streak", 3,
        "Stop trading after 3 consecutive losses (circuit breaker)"))

    for i, (name, value, reason) in enumerate(filters, 1):
        print(f"  {i}. {name}: {value} | {reason}")

    return filters


if __name__ == "__main__":
    results = load_latest_backtest()
    if results:
        df = analyze_trades(results)
        filters = find_filters(df)
