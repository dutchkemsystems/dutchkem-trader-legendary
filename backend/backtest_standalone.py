"""
Standalone Fast Backtest — Technical Signals from OHLCV
========================================================
No analyst framework, no MT5 dependency, no network calls.
Computes RSI, MACD, Bollinger Bands directly from price data.
Validates whether the trading strategy is profitable.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    symbol: str
    action: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    bars_held: int


# ─── Technical Indicators ──────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(close: pd.Series, period=20, num_std=2):
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return upper, sma, lower


def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calc_stoch(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(window=d_period).mean()
    return k, d


# ─── Signal Generation ─────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Generate composite buy/sell signals from OHLCV data."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # Indicators
    rsi = calc_rsi(close)
    macd_line, macd_signal, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    atr = calc_atr(high, low, close)
    stoch_k, stoch_d = calc_stoch(high, low, close)

    signals = []
    confidences = []

    for i in range(len(df)):
        buy_score = 0
        sell_score = 0
        total_weight = 0

        # RSI (weight: 2)
        if not np.isnan(rsi.iloc[i]):
            total_weight += 2
            if rsi.iloc[i] < 30:
                buy_score += 2 * 0.8
            elif rsi.iloc[i] > 70:
                sell_score += 2 * 0.8
            elif rsi.iloc[i] < 40:
                buy_score += 2 * 0.4
            elif rsi.iloc[i] > 60:
                sell_score += 2 * 0.4

        # MACD (weight: 2)
        if not np.isnan(macd_hist.iloc[i]) and not np.isnan(macd_hist.iloc[i-1] if i > 0 else np.nan):
            total_weight += 2
            if macd_hist.iloc[i] > 0 and (i == 0 or macd_hist.iloc[i-1] <= 0):
                buy_score += 2 * 0.9  # bullish crossover
            elif macd_hist.iloc[i] < 0 and (i == 0 or macd_hist.iloc[i-1] >= 0):
                sell_score += 2 * 0.9  # bearish crossover
            elif macd_hist.iloc[i] > 0:
                buy_score += 2 * 0.3
            elif macd_hist.iloc[i] < 0:
                sell_score += 2 * 0.3

        # Bollinger Bands (weight: 1.5)
        if not np.isnan(bb_lower.iloc[i]):
            total_weight += 1.5
            price = close.iloc[i]
            if price <= bb_lower.iloc[i]:
                buy_score += 1.5 * 0.8
            elif price >= bb_upper.iloc[i]:
                sell_score += 1.5 * 0.8
            elif price < bb_mid.iloc[i]:
                buy_score += 1.5 * 0.2
            elif price > bb_mid.iloc[i]:
                sell_score += 1.5 * 0.2

        # Stochastic (weight: 1)
        if not np.isnan(stoch_k.iloc[i]):
            total_weight += 1
            if stoch_k.iloc[i] < 20:
                buy_score += 1 * 0.7
            elif stoch_k.iloc[i] > 80:
                sell_score += 1 * 0.7

        # Trend filter: price vs BB mid (weight: 1.5)
        if not np.isnan(bb_mid.iloc[i]):
            total_weight += 1.5
            if close.iloc[i] > bb_mid.iloc[i]:
                buy_score += 1.5 * 0.5
            else:
                sell_score += 1.5 * 0.5

        # ATR filter: only trade if volatility is reasonable
        atr_val = atr.iloc[i] if not np.isnan(atr.iloc[i]) else 0
        atr_pct = atr_val / close.iloc[i] if close.iloc[i] > 0 else 0

        if total_weight > 0:
            buy_conf = buy_score / total_weight
            sell_conf = sell_score / total_weight
        else:
            buy_conf = 0
            sell_conf = 0

        # Decision
        min_agreement = 0.35
        if buy_conf > sell_conf and buy_conf > min_agreement:
            signals.append("BUY")
            confidences.append(buy_conf)
        elif sell_conf > buy_conf and sell_conf > min_agreement:
            signals.append("SELL")
            confidences.append(sell_conf)
        else:
            signals.append("HOLD")
            confidences.append(0.5)

    df = df.copy()
    df["signal"] = signals
    df["confidence"] = confidences
    df["rsi"] = rsi
    df["macd_hist"] = macd_hist
    df["atr"] = atr
    return df


# ─── Backtest Engine ───────────────────────────────────────

def run_backtest(df: pd.DataFrame, symbol: str, initial_balance: float = 10000.0,
                 risk_pct: float = 0.02, atr_sl_mult: float = 1.5, atr_tp_mult: float = 2.5,
                 max_hold_bars: int = 20):
    """Run backtest on pre-computed signals."""
    balance = initial_balance
    peak = initial_balance
    trades = []
    position = None
    equity_curve = [balance]
    consec_losses = 0

    for i in range(50, len(df)):
        price = float(df.iloc[i]["close"])
        current_time = str(df.index[i])[:19]
        current_hour = df.index[i].hour if hasattr(df.index[i], "hour") else 12
        atr_val = float(df.iloc[i]["atr"]) if not np.isnan(df.iloc[i]["atr"]) else 0
        signal = df.iloc[i]["signal"]
        confidence = df.iloc[i]["confidence"]

        # Close existing position
        if position is not None:
            bars_held = i - position["entry_bar"]
            if bars_held >= max_hold_bars or (
                position["action"] == "BUY" and price >= position["tp"]
            ) or (
                position["action"] == "SELL" and price <= position["tp"]
            ):
                if position["action"] == "BUY":
                    pnl = (price - position["entry_price"]) / position["entry_price"] * position["size"]
                else:
                    pnl = (position["entry_price"] - price) / position["entry_price"] * position["size"]
                balance += pnl
                trades.append(Trade(
                    entry_time=position["entry_time"], exit_time=current_time,
                    symbol=symbol, action=position["action"],
                    entry_price=position["entry_price"], exit_price=price,
                    size=position["size"], pnl=pnl,
                    pnl_pct=pnl / position["size"] * 100,
                    bars_held=bars_held,
                ))
                if pnl <= 0:
                    consec_losses += 1
                else:
                    consec_losses = 0
                position = None

        # Open new position
        if position is None and signal in ("BUY", "SELL"):
            # Filters
            if current_hour >= 20 or current_hour < 2:
                equity_curve.append(balance)
                continue
            if consec_losses >= 3:
                consec_losses = 0  # reset after skip
                equity_curve.append(balance)
                continue

            # Position sizing: fixed risk
            risk_amount = balance * risk_pct
            sl_distance = atr_val * atr_sl_mult
            if sl_distance <= 0:
                equity_curve.append(balance)
                continue

            # Size = risk_amount / sl_distance_pct
            sl_pct = sl_distance / price
            size = risk_amount / sl_pct if sl_pct > 0 else 0
            size = min(size, balance * 0.25)  # Max 25% of balance
            size = max(10, size)  # Min $10

            if size <= balance:
                sl = price - sl_distance if signal == "BUY" else price + sl_distance
                tp = price + atr_val * atr_tp_mult if signal == "BUY" else price - atr_val * atr_tp_mult
                position = {
                    "action": signal, "entry_price": price,
                    "entry_time": current_time, "entry_bar": i,
                    "size": size, "sl": sl, "tp": tp,
                }

        # Track equity
        equity_curve.append(balance)
        if balance > peak:
            peak = balance

    # Close remaining
    if position is not None:
        price = float(df.iloc[-1]["close"])
        if position["action"] == "BUY":
            pnl = (price - position["entry_price"]) / position["entry_price"] * position["size"]
        else:
            pnl = (position["entry_price"] - price) / position["entry_price"] * position["size"]
        balance += pnl
        trades.append(Trade(
            entry_time=position["entry_time"],
            exit_time=str(df.index[-1])[:19],
            symbol=symbol, action=position["action"],
            entry_price=position["entry_price"], exit_price=price,
            size=position["size"], pnl=pnl,
            pnl_pct=pnl / position["size"] * 100,
            bars_held=len(df) - position["entry_bar"],
        ))

    # Metrics
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    total_pnl = sum(t.pnl for t in trades)
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown
    peak_eq = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak_eq:
            peak_eq = eq
        dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0
        max_dd = max(max_dd, dd)

    # Sharpe
    sharpe = 0
    if len(equity_curve) > 1:
        rets = np.diff(equity_curve) / np.array(equity_curve[:-1])
        rets = rets[np.isfinite(rets)]
        if len(rets) > 0 and np.std(rets) > 0:
            sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252 * 24)

    return {
        "symbol": symbol,
        "start": str(df.index[50])[:19],
        "end": str(df.index[-1])[:19],
        "total_bars": len(df),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate * 100, 1),
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl / initial_balance * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd * 100, 1),
        "sharpe": round(sharpe, 2),
        "trades": [asdict(t) for t in trades],
    }


# ─── Data Loading ──────────────────────────────────────────

def load_candles(symbol):
    csv_path = Path("paper_trades") / f"{symbol}_1H.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            required = ["open", "high", "low", "close", "volume"]
            if all(c in df.columns for c in required):
                return df[required]
        except Exception:
            pass
    return None


def print_report(r):
    print(f"\n{'='*60}")
    print(f"  {r['symbol']} | {r['start']} -> {r['end']}")
    print(f"{'='*60}")
    print(f"  Trades:     {r['total_trades']} ({r['wins']}W / {r['losses']}L)")
    print(f"  Win rate:   {r['win_rate']}%")
    print(f"  Balance:    ${r['final_balance']:,.2f}")
    print(f"  P/L:        ${r['total_pnl']:+,.2f} ({r['pnl_pct']:+.1f}%)")
    print(f"  Avg win:    ${r['avg_win']:+,.2f}")
    print(f"  Avg loss:   ${r['avg_loss']:+,.2f}")
    print(f"  Profit fac: {r['profit_factor']}")
    print(f"  Max DD:     {r['max_drawdown']}%")
    print(f"  Sharpe:     {r['sharpe']}")
    if r["trades"]:
        print(f"\n  Last 5 trades:")
        for t in r["trades"][-5:]:
            cls = "WIN" if t["pnl"] > 0 else "LOSE"
            print(f"    {t['entry_time']} {t['action']:<4} {t['entry_price']:.5f}->{t['exit_price']:.5f} ${t['pnl']:+.2f} [{cls}] {t['bars_held']}bars")


# ─── Main ──────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  DUTCHKEM TRADER - STANDALONE BACKTEST")
    print("  Technical signals: RSI + MACD + Bollinger + Stochastic")
    print("  ATR-based SL/TP | Fixed risk 2% | Max hold 20 bars")
    print("="*60)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF",
               "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]

    all_results = []

    for symbol in symbols:
        df = load_candles(symbol)
        if df is None:
            print(f"\n  {symbol}: No data, skipping")
            continue

        print(f"\n  {symbol}: {len(df)} bars ({df.index[0]} -> {df.index[-1]})")

        # Generate signals
        df = generate_signals(df)

        # Count signal distribution
        buy_count = (df["signal"] == "BUY").sum()
        sell_count = (df["signal"] == "SELL").sum()
        hold_count = (df["signal"] == "HOLD").sum()
        print(f"    Signals: {buy_count} BUY / {sell_count} SELL / {hold_count} HOLD")

        # Run backtest with different parameters
        for risk in [0.01, 0.02, 0.03]:
            result = run_backtest(df, symbol, risk_pct=risk, max_hold_bars=20)
            if result["total_trades"] > 0:
                all_results.append(result)

        # Print best result for this symbol
        sym_results = [r for r in all_results if r["symbol"] == symbol and r["total_trades"] > 0]
        if sym_results:
            best = max(sym_results, key=lambda r: r["total_pnl"])
            print_report(best)

    # Portfolio summary
    if all_results:
        print(f"\n{'='*60}")
        print(f"  PORTFOLIO SUMMARY (all risk levels)")
        print(f"{'='*60}")
        active = [r for r in all_results if r["total_trades"] > 0]
        for r in sorted(active, key=lambda x: x["total_pnl"], reverse=True):
            print(f"    {r['symbol']:8s} risk={r['total_pnl']/10000*100/3:+5.1f}% trades={r['total_trades']:3d} "
                  f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} DD={r['max_drawdown']:5.1f}% "
                  f"P/L=${r['total_pnl']:+8.2f}")
        total_pnl = sum(r["total_pnl"] for r in active)
        avg_wr = np.mean([r["win_rate"] for r in active]) if active else 0
        print(f"  {'='*60}")
        print(f"  Total P/L: ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
        print(f"  Avg win rate: {avg_wr:.1f}%")
        print(f"{'='*60}")

    # Save
    output_dir = Path("paper_trades")
    output_dir.mkdir(exist_ok=True)
    filename = output_dir / f"standalone_bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to {filename}")


if __name__ == "__main__":
    main()
