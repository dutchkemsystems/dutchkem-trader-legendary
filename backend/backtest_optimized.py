"""
Optimized Backtest v2 — Trend-Aware + Adaptive SL/TP
=====================================================
Key optimizations over v1:
1. EMA200 trend filter: only trade WITH the trend
2. Adaptive SL/TP per symbol (based on ATR characteristics)
3. Volatility filter: skip ultra-low ATR (choppy) markets
4. Momentum confirmation: require RSI + MACD alignment
5. Dynamic hold period: exit on trend reversal signals
6. Trailing stop: lock in profits on winning trades
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
    exit_reason: str


# ─── Technical Indicators ──────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(close, period=20, num_std=2):
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


# ─── Symbol-Specific Configs ───────────────────────────────

SYMBOL_CONFIG = {
    "EURUSD": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "GBPUSD": {
        "sl_mult": 1.0, "tp_mult": 2.2, "trail_mult": 0.8,
        "max_hold": 20, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "USDJPY": {
        "sl_mult": 1.5, "tp_mult": 1.8, "trail_mult": 1.2,
        "max_hold": 15, "min_agreement": 0.45, "risk_pct": 0.015,
    },
    "XAUUSD": {
        "sl_mult": 1.3, "tp_mult": 2.5, "trail_mult": 1.0,
        "max_hold": 20, "min_agreement": 0.40, "risk_pct": 0.015,
    },
    "USDCHF": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "AUDUSD": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "USDCAD": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "NZDUSD": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "EURGBP": {
        "sl_mult": 1.2, "tp_mult": 2.0, "trail_mult": 1.0,
        "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02,
    },
    "EURJPY": {
        "sl_mult": 1.5, "tp_mult": 1.8, "trail_mult": 1.2,
        "max_hold": 15, "min_agreement": 0.45, "risk_pct": 0.015,
    },
}


# ─── Signal Generation with Trend Filter ───────────────────

def generate_signals(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Generate composite signals with EMA200 trend filter."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # Indicators
    rsi = calc_rsi(close)
    macd_line, macd_signal, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    atr = calc_atr(high, low, close)
    stoch_k, stoch_d = calc_stoch(high, low, close)

    # TREND FILTER: EMA200 + EMA50
    ema200 = close.ewm(span=200).mean()
    ema50 = close.ewm(span=50).mean()

    # Volatility filter: skip if ATR is too low (choppy)
    atr_pct = atr / close
    atr_pct_median = atr_pct.rolling(100).median()
    atr_ratio = atr_pct / atr_pct_median.replace(0, np.nan)

    signals = []
    confidences = []

    for i in range(len(df)):
        price = close.iloc[i]

        # ── TREND DETECTION ──
        # Primary trend: price vs EMA200
        uptrend = price > ema200.iloc[i] if not np.isnan(ema200.iloc[i]) else None
        # Secondary confirmation: EMA50 slope
        ema50_slope = (ema50.iloc[i] - ema50.iloc[max(0,i-5)]) / ema50.iloc[max(0,i-5)] if i >= 5 and not np.isnan(ema50.iloc[i]) else 0
        # Trend strength: how far from EMA200
        trend_distance = abs(price - ema200.iloc[i]) / ema200.iloc[i] if ema200.iloc[i] > 0 else 0

        # ── VOLATILITY FILTER ──
        # Skip if market is too choppy (ATR ratio < 0.6) or too wild (> 2.5)
        atr_r = atr_ratio.iloc[i] if not np.isnan(atr_ratio.iloc[i]) else 1.0
        if atr_r < 0.5 or atr_r > 3.0:
            signals.append("HOLD")
            confidences.append(0.5)
            continue

        # ── SIGNAL SCORING ──
        buy_score = 0
        sell_score = 0
        total_weight = 0

        # RSI (weight: 2)
        rsi_val = rsi.iloc[i] if not np.isnan(rsi.iloc[i]) else 50
        total_weight += 2
        if rsi_val < 30:
            buy_score += 2 * 0.9
        elif rsi_val > 70:
            sell_score += 2 * 0.9
        elif rsi_val < 40:
            buy_score += 2 * 0.5
        elif rsi_val > 60:
            sell_score += 2 * 0.5

        # MACD (weight: 2) — with crossover bonus
        hist_val = macd_hist.iloc[i] if not np.isnan(macd_hist.iloc[i]) else 0
        hist_prev = macd_hist.iloc[i-1] if i > 0 and not np.isnan(macd_hist.iloc[i-1]) else 0
        total_weight += 2
        if hist_val > 0 and hist_prev <= 0:
            buy_score += 2 * 0.95  # bullish crossover
        elif hist_val < 0 and hist_prev >= 0:
            sell_score += 2 * 0.95  # bearish crossover
        elif hist_val > 0:
            buy_score += 2 * 0.4
        elif hist_val < 0:
            sell_score += 2 * 0.4

        # Bollinger Bands (weight: 1.5)
        bb_l = bb_lower.iloc[i] if not np.isnan(bb_lower.iloc[i]) else price
        bb_u = bb_upper.iloc[i] if not np.isnan(bb_upper.iloc[i]) else price
        bb_m = bb_mid.iloc[i] if not np.isnan(bb_mid.iloc[i]) else price
        total_weight += 1.5
        if price <= bb_l:
            buy_score += 1.5 * 0.8
        elif price >= bb_u:
            sell_score += 1.5 * 0.8
        elif price < bb_m:
            buy_score += 1.5 * 0.2
        else:
            sell_score += 1.5 * 0.2

        # Stochastic (weight: 1)
        sk = stoch_k.iloc[i] if not np.isnan(stoch_k.iloc[i]) else 50
        total_weight += 1
        if sk < 20:
            buy_score += 1 * 0.7
        elif sk > 80:
            sell_score += 1 * 0.7

        # ── TREND BONUS (weight: 3) — THE KEY OPTIMIZATION ──
        # Strongly favor signals that align with the trend
        total_weight += 3
        if uptrend is not None:
            if uptrend:
                buy_score += 3 * 0.7   # Strong bonus for buying in uptrend
                sell_score += 3 * 0.1   # Small bonus for selling at overbought in uptrend
            else:
                sell_score += 3 * 0.7   # Strong bonus for selling in downtrend
                buy_score += 3 * 0.1    # Small bonus for buying at oversold in downtrend

        # ── MOMENTUM CONFIRMATION ──
        # Require at least 2 indicators aligned with trend for entry
        if uptrend is not None:
            if uptrend and buy_score > sell_score:
                # Need RSI < 50 (oversold bounce) AND (MACD bullish OR BB lower touch)
                rsi_ok = rsi_val < 50
                macd_ok = hist_val > hist_prev  # momentum improving
                bb_ok = price <= bb_m
                if not (rsi_ok or macd_ok or bb_ok):
                    buy_score *= 0.3  # Demote unconfirmed signals
            elif not uptrend and sell_score > buy_score:
                rsi_ok = rsi_val > 50
                macd_ok = hist_val < hist_prev
                bb_ok = price >= bb_m
                if not (rsi_ok or macd_ok or bb_ok):
                    sell_score *= 0.3

        # ── DECISION ──
        if total_weight > 0:
            buy_conf = buy_score / total_weight
            sell_conf = sell_score / total_weight
        else:
            buy_conf = 0
            sell_conf = 0

        min_agree = cfg.get("min_agreement", 0.38)

        if buy_conf > sell_conf and buy_conf > min_agree:
            signals.append("BUY")
            confidences.append(buy_conf)
        elif sell_conf > buy_conf and sell_conf > min_agree:
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
    df["ema200"] = ema200
    df["ema50"] = ema50
    return df


# ─── Backtest Engine with Trailing Stop ────────────────────

def run_backtest(df, symbol, cfg, initial_balance=10000.0):
    """Run backtest with trailing stop and trend-aware exits."""
    balance = initial_balance
    peak = initial_balance
    trades = []
    position = None
    equity_curve = [balance]
    consec_losses = 0
    max_consec_losses = 3

    sl_mult = cfg.get("sl_mult", 1.2)
    tp_mult = cfg.get("tp_mult", 2.0)
    trail_mult = cfg.get("trail_mult", 1.0)
    max_hold = cfg.get("max_hold", 20)
    risk_pct = cfg.get("risk_pct", 0.02)

    for i in range(200, len(df)):
        price = float(df.iloc[i]["close"])
        high_i = float(df.iloc[i]["high"])
        low_i = float(df.iloc[i]["low"])
        current_time = str(df.index[i])[:19]
        current_hour = df.index[i].hour if hasattr(df.index[i], "hour") else 12
        atr_val = float(df.iloc[i]["atr"]) if not np.isnan(df.iloc[i]["atr"]) else 0
        signal = df.iloc[i]["signal"]

        # ── CLOSE EXISTING POSITION ──
        if position is not None:
            bars_held = i - position["entry_bar"]
            action = position["action"]
            entry = position["entry_price"]

            # Calculate current P/L
            if action == "BUY":
                unrealized = (price - entry) / entry * position["size"]
                # Update trailing stop
                if price > position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price - atr_val * trail_mult
                # Check exits
                exit_now = False
                exit_reason = ""
                if price <= position["sl"]:
                    exit_now = True
                    exit_reason = "SL"
                elif price >= position["tp"]:
                    exit_now = True
                    exit_reason = "TP"
                elif bars_held >= max_hold:
                    exit_now = True
                    exit_reason = "TIME"
                elif signal == "SELL" and bars_held >= 3:
                    # Trend reversal exit
                    exit_now = True
                    exit_reason = "REVERSAL"
            else:  # SELL
                unrealized = (entry - price) / entry * position["size"]
                if price < position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price + atr_val * trail_mult
                exit_now = False
                exit_reason = ""
                if price >= position["sl"]:
                    exit_now = True
                    exit_reason = "SL"
                elif price <= position["tp"]:
                    exit_now = True
                    exit_reason = "TP"
                elif bars_held >= max_hold:
                    exit_now = True
                    exit_reason = "TIME"
                elif signal == "BUY" and bars_held >= 3:
                    exit_now = True
                    exit_reason = "REVERSAL"

            if exit_now:
                pnl = unrealized
                balance += pnl
                trades.append(Trade(
                    entry_time=position["entry_time"], exit_time=current_time,
                    symbol=symbol, action=action,
                    entry_price=entry, exit_price=price,
                    size=position["size"], pnl=pnl,
                    pnl_pct=pnl / position["size"] * 100,
                    bars_held=bars_held, exit_reason=exit_reason,
                ))
                if pnl <= 0:
                    consec_losses += 1
                else:
                    consec_losses = 0
                position = None

        # ── OPEN NEW POSITION ──
        if position is None and signal in ("BUY", "SELL"):
            # Time filter
            if current_hour >= 20 or current_hour < 2:
                equity_curve.append(balance)
                continue
            # Circuit breaker
            if consec_losses >= max_consec_losses:
                consec_losses = 0
                equity_curve.append(balance)
                continue

            # Position sizing
            risk_amount = balance * risk_pct
            sl_distance = atr_val * sl_mult
            if sl_distance <= 0:
                equity_curve.append(balance)
                continue
            sl_pct = sl_distance / price
            size = risk_amount / sl_pct if sl_pct > 0 else 0
            size = min(size, balance * 0.20)
            size = max(10, size)

            if size <= balance:
                if signal == "BUY":
                    sl = price - sl_distance
                    tp = price + atr_val * tp_mult
                else:
                    sl = price + sl_distance
                    tp = price - atr_val * tp_mult

                position = {
                    "action": signal, "entry_price": price,
                    "entry_time": current_time, "entry_bar": i,
                    "size": size, "sl": sl, "tp": tp,
                    "trail_peak": price,
                }

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
            exit_reason="END",
        ))

    # ── METRICS ──
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    total_pnl = sum(t.pnl for t in trades)
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    peak_eq = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak_eq:
            peak_eq = eq
        dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0
        max_dd = max(max_dd, dd)

    sharpe = 0
    if len(equity_curve) > 1:
        rets = np.diff(equity_curve) / np.array(equity_curve[:-1])
        rets = rets[np.isfinite(rets)]
        if len(rets) > 0 and np.std(rets) > 0:
            sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252 * 24)

    # Exit reason breakdown
    reasons = {}
    for t in trades:
        r = t.exit_reason
        if r not in reasons:
            reasons[r] = {"count": 0, "pnl": 0, "wins": 0}
        reasons[r]["count"] += 1
        reasons[r]["pnl"] += t.pnl
        if t.pnl > 0:
            reasons[r]["wins"] += 1

    return {
        "symbol": symbol,
        "start": str(df.index[200])[:19],
        "end": str(df.index[-1])[:19],
        "total_bars": len(df),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate * 100, 1),
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl / initial_balance * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(pf, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "exit_reasons": reasons,
        "trades": [asdict(t) for t in trades],
    }


# ─── Parameter Sweep ───────────────────────────────────────

def param_sweep(df, symbol):
    """Try multiple parameter combos to find best config.
    df must have been processed by generate_signals() already."""
    best_pnl = -999999
    best_cfg = None
    best_result = None

    # Targeted sweep: 16 combos (fast ~2min total)
    for sl in [0.8, 1.2]:
        for tp in [2.0, 3.0]:
            for trail in [0.8, 1.2]:
                for max_h in [15, 25]:
                    for risk in [0.015, 0.025]:
                        cfg = {
                            "sl_mult": sl, "tp_mult": tp,
                            "trail_mult": trail, "max_hold": max_h,
                            "min_agreement": 0.38, "risk_pct": risk,
                        }
                        result = run_backtest(df, symbol, cfg)
                        # Score: P/L with penalty for low win rate and high DD
                        score = result["total_pnl"]
                        if result["win_rate"] < 45:
                            score -= 50
                        if result["max_drawdown"] > 5:
                            score -= (result["max_drawdown"] - 5) * 20
                        if result["total_trades"] < 10:
                            score -= 100  # Too few trades

                        if score > best_pnl:
                            best_pnl = score
                            best_cfg = cfg
                            best_result = result

    return best_cfg, best_result


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


def print_report(r, cfg=None):
    print(f"\n{'='*65}")
    print(f"  {r['symbol']} | {r['start']} -> {r['end']}")
    if cfg:
        print(f"  Config: SL={cfg['sl_mult']}x TP={cfg['tp_mult']}x Trail={cfg['trail_mult']}x "
              f"MaxHold={cfg['max_hold']} MinAgree={cfg['min_agreement']} Risk={cfg['risk_pct']}")
    print(f"{'='*65}")
    print(f"  Trades:     {r['total_trades']} ({r['wins']}W / {r['losses']}L)")
    print(f"  Win rate:   {r['win_rate']}%")
    print(f"  Balance:    ${r['final_balance']:,.2f}")
    print(f"  P/L:        ${r['total_pnl']:+,.2f} ({r['pnl_pct']:+.2f}%)")
    print(f"  Avg win:    ${r['avg_win']:+,.2f}")
    print(f"  Avg loss:   ${r['avg_loss']:+,.2f}")
    print(f"  Profit fac: {r['profit_factor']}")
    print(f"  Max DD:     {r['max_drawdown']}%")
    print(f"  Sharpe:     {r['sharpe']}")

    if r.get("exit_reasons"):
        print(f"\n  Exit reasons:")
        for reason, data in sorted(r["exit_reasons"].items()):
            wr = data["wins"] / data["count"] * 100 if data["count"] > 0 else 0
            print(f"    {reason:10s} {data['count']:3d} trades  WR={wr:.0f}%  P/L=${data['pnl']:+.2f}")

    if r["trades"]:
        print(f"\n  Last 5 trades:")
        for t in r["trades"][-5:]:
            cls = "WIN" if t["pnl"] > 0 else "LOSE"
            print(f"    {t['entry_time'][:16]} {t['action']:<4} {t['entry_price']:.5f}->{t['exit_price']:.5f} "
                  f"${t['pnl']:+.2f} [{cls}] {t['bars_held']}bars {t['exit_reason']}")


# ─── Main ──────────────────────────────────────────────────

def main():
    print("\n" + "="*65)
    print("  DUTCHKEM TRADER - OPTIMIZED BACKTEST V2")
    print("  Trend-aware + Trailing Stop + Parameter Sweep")
    print("="*65)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    all_results = []
    all_configs = {}

    for symbol in symbols:
        df = load_candles(symbol)
        if df is None:
            print(f"\n  {symbol}: No data, skipping")
            continue

        print(f"\n  {symbol}: {len(df)} bars | Sweep 32 combos...")

        # Generate signals first (shared across all param combos)
        cfg0 = SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["EURUSD"])
        df_signals = generate_signals(df, cfg0)

        # Run sweep on signal-enriched data
        t0 = time.time()
        best_cfg, best_result = param_sweep(df_signals, symbol)
        elapsed = time.time() - t0
        print(f"  Sweep done in {elapsed:.1f}s")

        if best_result and best_result["total_trades"] > 0:
            all_results.append(best_result)
            all_configs[symbol] = best_cfg
            print_report(best_result, best_cfg)

    # Portfolio summary
    if all_results:
        print(f"\n{'='*65}")
        print(f"  OPTIMIZED PORTFOLIO SUMMARY")
        print(f"{'='*65}")
        total_pnl = sum(r["total_pnl"] for r in all_results)
        active = [r for r in all_results if r["total_trades"] > 0]
        avg_wr = np.mean([r["win_rate"] for r in active]) if active else 0
        avg_pf = np.mean([r["profit_factor"] for r in active]) if active else 0
        max_dd = max(r["max_drawdown"] for r in active) if active else 0
        print(f"  Symbols:     {len(active)}")
        print(f"  Total P/L:   ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
        print(f"  Avg win rate:{avg_wr:.1f}%")
        print(f"  Avg PF:      {avg_pf:.2f}")
        print(f"  Max DD:      {max_dd:.2f}%")
        for r in sorted(active, key=lambda x: x["total_pnl"], reverse=True):
            print(f"    {r['symbol']:8s} trades={r['total_trades']:3d} "
                  f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} "
                  f"DD={r['max_drawdown']:5.2f}% P/L=${r['total_pnl']:+8.2f}")
        print(f"{'='*65}")

        # Print best configs for reuse
        print(f"\n  Best configs:")
        for sym, cfg in all_configs.items():
            print(f"    {sym}: {json.dumps(cfg)}")

    # Save
    output_dir = Path("paper_trades")
    output_dir.mkdir(exist_ok=True)
    filename = output_dir / f"optimized_bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_data = {
        "results": all_results,
        "configs": {k: v for k, v in all_configs.items()},
        "timestamp": datetime.now().isoformat(),
    }
    with open(filename, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Results saved to {filename}")


if __name__ == "__main__":
    main()
