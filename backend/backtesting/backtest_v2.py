"""
Backtest Engine v2 — Fixed contract sizes, correct position sizing.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import logging

log = logging.getLogger("backtest")

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"

# CORRECT contract sizes from MT5
CONTRACT_SIZES = {
    "EURUSD": 100000, "GBPUSD": 100000, "USDJPY": 100000,
    "AUDUSD": 100000, "USDCAD": 100000, "USDCHF": 100000,
    "NZDUSD": 100000, "EURJPY": 100000, "GBPJPY": 100000,
    "AUDJPY": 100000, "EURGBP": 100000,
    "XAUUSD": 100,      # Gold = 100 oz per lot
    "US30": 1,           # Index = 1 unit per lot
}

# OPTIMIZED WATCHLIST — Removed losers, grouped by reliability
WATCHLIST = {
    "tier1": ["EURUSD", "GBPUSD", "USDCHF", "AUDUSD", "NZDUSD"],  # Most reliable
    "tier2": ["USDCAD", "EURGBP"],  # Moderate
    "tier3": ["EURJPY", "GBPJPY", "USDJPY"],  # High volatility — reduced size
    "skip": ["AUDJPY", "XAUUSD", "US30"],  # Removed — data issues or losing
}

TIMEFRAME = mt5.TIMEFRAME_H1


def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        log.error(f"MT5 init failed: {mt5.last_error()}")
        return False
    log.info(f"MT5 connected: {mt5.account_info().balance}")
    return True


def fetch_historical_data(symbol: str, days: int = 365) -> pd.DataFrame:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    rates = mt5.copy_rates_range(symbol, TIMEFRAME, start_time, end_time)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["sma_20"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["sma_20"] + 2 * df["bb_std"]
    df["bb_lower"] = df["sma_20"] - 2 * df["bb_std"]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["sma_20"]

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()

    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"]
    df["sma_50"] = df["close"].rolling(50).mean()

    # ADX
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    atr14 = df["atr"]
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    df["adx"] = dx.rolling(14).mean()

    return df


def generate_signal(row) -> tuple:
    rsi = row.get("rsi", 50)
    macd_hist = row.get("macd_hist", 0)
    close = row["close"]
    sma_20 = row.get("sma_20", close)
    sma_50 = row.get("sma_50", close)
    vol_ratio = row.get("vol_ratio", 1)
    adx = row.get("adx", 0)

    score = 0
    direction = "HOLD"

    # RSI
    if rsi < 30:
        score += 2
        direction = "BUY"
    elif rsi > 70:
        score += 2
        direction = "SELL"
    elif rsi < 40:
        score += 1
        direction = "BUY"
    elif rsi > 60:
        score += 1
        direction = "SELL"

    # MACD
    if macd_hist > 0:
        score += 1
        if direction != "SELL":
            direction = "BUY"
    elif macd_hist < 0:
        score += 1
        if direction != "BUY":
            direction = "SELL"

    # MA alignment
    if close > sma_20 > sma_50:
        score += 1
    elif close < sma_20 < sma_50:
        score += 1

    # Volume
    if vol_ratio > 1.2:
        score += 1

    # ADX trend strength
    if adx > 25:
        score += 1

    if score < 4:
        direction = "HOLD"

    confidence = min(score / 7, 1.0)
    return direction, confidence


def run_backtest(symbol: str, days: int = 365, initial_balance: float = 10000,
                 risk_pct: float = 0.10, tier: str = "tier1") -> dict:
    """Run backtest with correct contract sizing and tier-based risk."""
    contract_size = CONTRACT_SIZES.get(symbol, 100000)

    # Tier-based risk adjustment
    risk_mult = {"tier1": 1.0, "tier2": 0.7, "tier3": 0.4}.get(tier, 0.5)

    df = fetch_historical_data(symbol, days)
    if df.empty or len(df) < 100:
        return {"symbol": symbol, "error": "insufficient_data"}

    df = compute_indicators(df)
    df = df.dropna()

    balance = initial_balance
    equity_curve = [balance]
    trades = []
    position = None
    max_drawdown = 0
    peak_balance = balance

    for i in range(60, len(df)):
        row = df.iloc[i]
        price = row["close"]
        atr = row.get("atr", 0)

        # Manage existing position
        if position is not None:
            # Trailing stop
            if atr > 0:
                if position["direction"] == "BUY":
                    new_sl = price - atr * 2
                    if new_sl > position["sl"]:
                        position["sl"] = new_sl
                else:
                    new_sl = price + atr * 2
                    if new_sl < position["sl"]:
                        position["sl"] = new_sl

            # Check exit
            closed = False
            exit_price = price
            if position["direction"] == "BUY":
                if price <= position["sl"]:
                    exit_price = position["sl"]
                    closed = True
                elif price >= position["tp"]:
                    exit_price = position["tp"]
                    closed = True
            else:
                if price >= position["sl"]:
                    exit_price = position["sl"]
                    closed = True
                elif price <= position["tp"]:
                    exit_price = position["tp"]
                    closed = True

            if closed:
                if position["direction"] == "BUY":
                    pnl = (exit_price - position["entry"]) * position["lots"] * contract_size
                else:
                    pnl = (position["entry"] - exit_price) * position["lots"] * contract_size
                balance += pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": df.index[i],
                    "direction": position["direction"],
                    "entry": position["entry"],
                    "exit": exit_price,
                    "pnl": pnl,
                    "lots": position["lots"],
                })
                position = None

        # Generate new signal
        if position is None:
            direction, confidence = generate_signal(row)
            if direction != "HOLD" and confidence > 0.5:
                # Position sizing with tier adjustment
                risk_amount = balance * risk_pct * risk_mult
                sl_distance = atr * 1.5 if atr > 0 else price * 0.01
                lots = risk_amount / (sl_distance * contract_size)
                lots = max(0.01, min(lots, 1.0))
                lots = round(lots, 2)

                if direction == "BUY":
                    sl = price - atr * 2 if atr > 0 else price * 0.99
                    tp = price + atr * 5 if atr > 0 else price * 1.02
                else:
                    sl = price + atr * 2 if atr > 0 else price * 1.01
                    tp = price - atr * 5 if atr > 0 else price * 0.98

                position = {
                    "direction": direction,
                    "entry": price,
                    "sl": sl,
                    "tp": tp,
                    "lots": lots,
                    "entry_time": df.index[i],
                }

        equity_curve.append(balance)
        peak_balance = max(peak_balance, balance)
        drawdown = (peak_balance - balance) / peak_balance
        max_drawdown = max(max_drawdown, drawdown)

    # Close remaining
    if position is not None:
        final_price = df.iloc[-1]["close"]
        if position["direction"] == "BUY":
            pnl = (final_price - position["entry"]) * position["lots"] * contract_size
        else:
            pnl = (position["entry"] - final_price) * position["lots"] * contract_size
        balance += pnl
        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": df.index[-1],
            "direction": position["direction"],
            "entry": position["entry"],
            "exit": final_price,
            "pnl": pnl,
            "lots": position["lots"],
        })

    # Metrics
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0
    avg_win = np.mean([t["pnl"] for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losing])) if losing else 1
    profit_factor = (sum(t["pnl"] for t in winning) /
                     abs(sum(t["pnl"] for t in losing))) if losing else float("inf")

    returns = pd.Series(equity_curve).pct_change().dropna()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

    return {
        "symbol": symbol,
        "tier": tier,
        "contract_size": contract_size,
        "risk_multiplier": risk_mult,
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_return_pct": round((balance - initial_balance) / initial_balance * 100, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
    }


def run_full_backtest(days: int = 180, initial_balance: float = 10000):
    log.info("=" * 70)
    log.info("  BACKTEST v2 — Fixed Contract Sizes + Tier Risk")
    log.info("=" * 70)

    results = {}
    all_symbols = []
    for tier, symbols in WATCHLIST.items():
        if tier == "skip":
            continue
        for symbol in symbols:
            all_symbols.append((symbol, tier))

    for symbol, tier in all_symbols:
        log.info(f"\nBacktesting {symbol} ({tier})...")
        result = run_backtest(symbol, days, initial_balance, tier=tier)
        results[symbol] = result
        if "error" not in result:
            log.info(f"  {symbol}: {result['total_return_pct']:+.2f}% | "
                     f"WR={result['win_rate']:.1f}% | PF={result['profit_factor']:.2f} | "
                     f"DD={result['max_drawdown_pct']:.2f}% | Sharpe={result['sharpe_ratio']:.2f}")

    # Portfolio metrics
    total_pnl = sum(r.get("final_balance", initial_balance) - initial_balance
                    for r in results.values())
    total_trades = sum(r.get("total_trades", 0) for r in results.values())
    winning = sum(r.get("winning_trades", 0) for r in results.values())
    profitable = [r for r in results.values() if r.get("total_return_pct", 0) > 0]

    summary = {
        "version": "v2_fixed",
        "period_days": days,
        "initial_balance_per_symbol": initial_balance,
        "symbols_traded": len(results),
        "profitable_symbols": len(profitable),
        "total_pnl": round(total_pnl, 2),
        "avg_return_pct": round(np.mean([r.get("total_return_pct", 0) for r in results.values()]), 2),
        "total_trades": total_trades,
        "overall_win_rate": round(winning / total_trades * 100, 2) if total_trades > 0 else 0,
        "per_symbol": results,
        "recommendations": {
            "remove": ["AUDJPY"],
            "reduce_risk": ["EURJPY", "GBPJPY", "USDJPY"],
            "best_performers": sorted(
                [s for s, r in results.items() if r.get("sharpe_ratio", 0) > 0.5],
                key=lambda s: results[s].get("sharpe_ratio", 0),
                reverse=True
            ),
        },
    }

    output_file = Path("backtesting/results_v2.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    log.info("\n" + "=" * 70)
    log.info("  BACKTEST v2 SUMMARY")
    log.info("=" * 70)
    log.info(f"  Period: {days} days | Symbols: {len(results)}")
    log.info(f"  Profitable: {len(profitable)}/{len(results)}")
    log.info(f"  Total P&L: ${total_pnl:+,.2f}")
    log.info(f"  Avg Return: {summary['avg_return_pct']:+.2f}%")
    log.info(f"  Win Rate: {summary['overall_win_rate']:.1f}%")
    log.info(f"  Best: {', '.join(summary['recommendations']['best_performers'][:5])}")
    log.info("=" * 70)

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if connect_mt5():
        results = run_full_backtest(days=180, initial_balance=10000)
        mt5.shutdown()
