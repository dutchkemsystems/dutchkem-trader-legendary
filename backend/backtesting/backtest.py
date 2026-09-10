"""
Backtest Engine — Run strategy on real MT5 historical data.
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

# ═══════════════════════════════════════════════════════════════
# MT5 CONFIGURATION
# ═══════════════════════════════════════════════════════════════
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
           "EURJPY", "GBPJPY", "AUDJPY", "EURGBP", "XAUUSD", "US30"]

TIMEFRAME = mt5.TIMEFRAME_H1


def connect_mt5():
    """Connect to MT5."""
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        log.error(f"MT5 init failed: {mt5.last_error()}")
        return False
    log.info(f"MT5 connected: {mt5.account_info().balance}")
    return True


def fetch_historical_data(symbol: str, days: int = 365) -> pd.DataFrame:
    """Fetch historical OHLCV data from MT5."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    rates = mt5.copy_rates_range(symbol, TIMEFRAME, start_time, end_time)
    if rates is None or len(rates) == 0:
        log.warning(f"No data for {symbol}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "tick_volume": "volume"}, inplace=True)

    log.info(f"Fetched {len(df)} bars for {symbol} ({days} days)")
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators."""
    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    df["sma_20"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["sma_20"] + 2 * df["bb_std"]
    df["bb_lower"] = df["sma_20"] - 2 * df["bb_std"]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["sma_20"]

    # ATR
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()

    # Volume ratio
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"]

    # SMA 50
    df["sma_50"] = df["close"].rolling(50).mean()

    return df


def generate_signal(row) -> tuple:
    """Generate trading signal from indicators."""
    rsi = row.get("rsi", 50)
    macd_hist = row.get("macd_hist", 0)
    bb_width = row.get("bb_width", 0)
    close = row["close"]
    sma_20 = row.get("sma_20", close)
    sma_50 = row.get("sma_50", close)
    vol_ratio = row.get("vol_ratio", 1)

    score = 0
    direction = "HOLD"

    # RSI signals
    if rsi < 30:
        score += 2
        direction = "BUY"
    elif rsi > 70:
        score += 2
        direction = "SELL"

    # MACD signals
    if macd_hist > 0:
        score += 1
        if direction != "SELL":
            direction = "BUY"
    elif macd_hist < 0:
        score += 1
        if direction != "BUY":
            direction = "SELL"

    # Moving average alignment
    if close > sma_20 > sma_50:
        score += 1
    elif close < sma_20 < sma_50:
        score += 1

    # Volume confirmation
    if vol_ratio > 1.2:
        score += 1

    # Minimum score to generate signal
    if score < 3:
        direction = "HOLD"

    confidence = min(score / 6, 1.0)
    return direction, confidence


def run_backtest(symbol: str, days: int = 365, initial_balance: float = 10000) -> dict:
    """Run backtest for a single symbol."""
    df = fetch_historical_data(symbol, days)
    if df.empty or len(df) < 100:
        return {"symbol": symbol, "error": "insufficient_data"}

    df = compute_indicators(df)
    df = df.dropna()

    # Simulation
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

        # Check existing position
        if position is not None:
            # Calculate P&L
            if position["direction"] == "BUY":
                pnl = (price - position["entry"]) * position["lots"] * 100000
            else:
                pnl = (position["entry"] - price) * position["lots"] * 100000

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

            # Check SL/TP
            if position["direction"] == "BUY":
                if price <= position["sl"] or price >= position["tp"]:
                    # Close trade
                    if price <= position["sl"]:
                        pnl = (position["sl"] - position["entry"]) * position["lots"] * 100000
                    else:
                        pnl = (position["tp"] - position["entry"]) * position["lots"] * 100000
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": df.index[i],
                        "direction": position["direction"],
                        "entry": position["entry"],
                        "exit": price,
                        "pnl": pnl,
                        "lots": position["lots"],
                    })
                    position = None
            else:
                if price >= position["sl"] or price <= position["tp"]:
                    if price >= position["sl"]:
                        pnl = (position["entry"] - position["sl"]) * position["lots"] * 100000
                    else:
                        pnl = (position["entry"] - position["tp"]) * position["lots"] * 100000
                    balance += pnl
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": df.index[i],
                        "direction": position["direction"],
                        "entry": position["entry"],
                        "exit": price,
                        "pnl": pnl,
                        "lots": position["lots"],
                    })
                    position = None

        # Generate new signal
        if position is None:
            direction, confidence = generate_signal(row)
            if direction != "HOLD" and confidence > 0.5:
                # Calculate position size
                risk_pct = 0.10
                risk_amount = balance * risk_pct
                sl_distance = atr * 1.5 if atr > 0 else price * 0.01
                lots = risk_amount / (sl_distance * 100000)
                lots = max(0.01, min(lots, 1.0))

                # Set SL/TP
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

        # Track equity
        equity_curve.append(balance)

        # Track drawdown
        peak_balance = max(peak_balance, balance)
        drawdown = (peak_balance - balance) / peak_balance
        max_drawdown = max(max_drawdown, drawdown)

    # Close any remaining position
    if position is not None:
        final_price = df.iloc[-1]["close"]
        if position["direction"] == "BUY":
            pnl = (final_price - position["entry"]) * position["lots"] * 100000
        else:
            pnl = (position["entry"] - final_price) * position["lots"] * 100000
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

    # Calculate metrics
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] <= 0]

    win_rate = len(winning_trades) / len(trades) if trades else 0
    avg_win = np.mean([t["pnl"] for t in winning_trades]) if winning_trades else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losing_trades])) if losing_trades else 1
    profit_factor = (sum(t["pnl"] for t in winning_trades) /
                     abs(sum(t["pnl"] for t in losing_trades))) if losing_trades else float("inf")

    # Sharpe ratio (simplified)
    returns = pd.Series(equity_curve).pct_change().dropna()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

    return {
        "symbol": symbol,
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_return_pct": round((balance - initial_balance) / initial_balance * 100, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": round(win_rate * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trades": trades[:10],  # First 10 trades for inspection
    }


def run_full_backtest(days: int = 365, initial_balance: float = 10000):
    """Run backtest across all symbols."""
    log.info("=" * 70)
    log.info("  FULL BACKTEST — All Symbols")
    log.info("=" * 70)

    results = {}
    for symbol in SYMBOLS:
        log.info(f"\nBacktesting {symbol}...")
        result = run_backtest(symbol, days, initial_balance)
        results[symbol] = result
        if "error" not in result:
            log.info(f"  {symbol}: {result['total_return_pct']:+.2f}% | "
                     f"WR={result['win_rate']:.1f}% | PF={result['profit_factor']:.2f} | "
                     f"DD={result['max_drawdown_pct']:.2f}% | Sharpe={result['sharpe_ratio']:.2f}")

    # Portfolio-level metrics
    total_pnl = sum(r.get("final_balance", initial_balance) - initial_balance
                    for r in results.values())
    total_trades = sum(r.get("total_trades", 0) for r in results.values())
    winning = sum(r.get("winning_trades", 0) for r in results.values())

    portfolio_return = total_pnl / (initial_balance * len(SYMBOLS)) * 100

    summary = {
        "period_days": days,
        "initial_balance_per_symbol": initial_balance,
        "symbols_traded": len([r for r in results.values() if "error" not in r]),
        "total_pnl": round(total_pnl, 2),
        "portfolio_return_pct": round(portfolio_return, 2),
        "total_trades": total_trades,
        "overall_win_rate": round(winning / total_trades * 100, 2) if total_trades > 0 else 0,
        "per_symbol": {s: {k: v for k, v in r.items() if k != "trades"}
                      for s, r in results.items()},
    }

    # Save results
    output_file = Path("backtesting/results.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    log.info("\n" + "=" * 70)
    log.info("  BACKTEST SUMMARY")
    log.info("=" * 70)
    log.info(f"  Period: {days} days")
    log.info(f"  Symbols: {summary['symbols_traded']}")
    log.info(f"  Total P&L: ${summary['total_pnl']:+,.2f}")
    log.info(f"  Portfolio Return: {summary['portfolio_return_pct']:+.2f}%")
    log.info(f"  Total Trades: {summary['total_trades']}")
    log.info(f"  Win Rate: {summary['overall_win_rate']:.1f}%")
    log.info("=" * 70)

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if connect_mt5():
        results = run_full_backtest(days=180, initial_balance=10000)
        mt5.shutdown()
    else:
        log.error("Cannot run backtest without MT5 connection")
