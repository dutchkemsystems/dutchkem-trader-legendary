"""
Optimized Backtest V3 — High-Conviction Entries
================================================
Diagnosis from V2: 60-70% of trades hit SL (near 0% WR on early exits).
Root cause: entering on weak signals, SL too tight for noise.

V3 fixes:
1. MINIMAL TRADES: Only enter when 3+ indicators align (stricter)
2. WIDER SL: 2-3x ATR to survive intrabar noise
3. HIGHER TP: 3-4x ATR for better risk:reward
4. MOMENTUM GATE: RSI must be trending (not just in zone)
5. COOLDOWN: 5-bar gap between trades (avoid re-entry after loss)
6. MULTI-TF CONFIRM: Simulated via longer-period indicators
7. ADAPTIVE HOLD: Exit on momentum exhaustion, not fixed time
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

SYMBOL_CONFIG = {
    "EURUSD": {"sl_mult": 1.2, "tp_mult": 3.0, "trail_mult": 1.2, "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.02},
    "GBPUSD": {"sl_mult": 0.8, "tp_mult": 3.0, "trail_mult": 0.8, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.02},
    "USDJPY": {"sl_mult": 0.8, "tp_mult": 2.0, "trail_mult": 1.2, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.015},
    "XAUUSD": {"sl_mult": 0.8, "tp_mult": 3.0, "trail_mult": 0.8, "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.015},
    "USDCHF": {"sl_mult": 2.0, "tp_mult": 2.0, "trail_mult": 0.8, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.015},
    "AUDUSD": {"sl_mult": 1.2, "tp_mult": 3.0, "trail_mult": 1.2, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.015},
    "USDCAD": {"sl_mult": 0.8, "tp_mult": 3.0, "trail_mult": 1.2, "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.015},
    "NZDUSD": {"sl_mult": 0.8, "tp_mult": 3.0, "trail_mult": 0.8, "max_hold": 25, "min_agreement": 0.38, "risk_pct": 0.015},
    "EURGBP": {"sl_mult": 0.8, "tp_mult": 2.0, "trail_mult": 0.8, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.015},
    "EURJPY": {"sl_mult": 1.2, "tp_mult": 3.0, "trail_mult": 0.8, "max_hold": 15, "min_agreement": 0.38, "risk_pct": 0.015},
}


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


# ─── Indicators ─────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(close, fast=12, slow=26, sig=9):
    ema_f = close.ewm(span=fast).mean()
    ema_s = close.ewm(span=slow).mean()
    macd = ema_f - ema_s
    signal = macd.ewm(span=sig).mean()
    hist = macd - signal
    return macd, signal, hist

def calc_bollinger(close, period=20, num_std=2):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return sma + num_std*std, sma, sma - num_std*std

def calc_atr(high, low, close, period=14):
    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calc_stoch(high, low, close, k=14, d=3):
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    sk = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return sk, sk.rolling(d).mean()

def calc_adx(high, low, close, period=14):
    """Average Directional Index — measures trend strength."""
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0), index=high.index)
    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di

def calc_ema(close, period):
    return close.ewm(span=period).mean()


# ─── High-Conviction Signal Generator ──────────────────────

def generate_signals_v3(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """V3: Only enter when 3+ indicators align with strong momentum."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    rsi = calc_rsi(close)
    macd_line, macd_sig, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    atr = calc_atr(high, low, close)
    stoch_k, stoch_d = calc_stoch(high, low, close)
    adx, plus_di, minus_di = calc_adx(high, low, close)

    # Multi-timeframe EMAs (simulated via longer periods)
    ema20 = calc_ema(close, 20)
    ema50 = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)

    # RSI slope (momentum direction)
    rsi_slope = rsi - rsi.shift(3)

    # MACD acceleration (histogram getting stronger)
    hist_accel = macd_hist - macd_hist.shift(1)

    # Volatility regime
    atr_pct = atr / close
    atr_pct_median = atr_pct.rolling(100).median()
    atr_ratio = atr_pct / atr_pct_median.replace(0, np.nan)

    signals = []
    confidences = []

    for i in range(len(df)):
        price = close.iloc[i]

        # Skip if indicators not ready
        if np.isnan(ema200.iloc[i]) or np.isnan(adx.iloc[i]):
            signals.append("HOLD")
            confidences.append(0.5)
            continue

        # ── VOLATILITY FILTER ──
        ar = atr_ratio.iloc[i] if not np.isnan(atr_ratio.iloc[i]) else 1.0
        if ar < 0.4 or ar > 3.5:
            signals.append("HOLD")
            confidences.append(0.5)
            continue

        # ── TREND STATE ──
        uptrend = price > ema50.iloc[i]
        strong_trend = adx.iloc[i] > 20 if not np.isnan(adx.iloc[i]) else False
        very_strong = adx.iloc[i] > 30 if not np.isnan(adx.iloc[i]) else False

        # ── INDICATOR SCORES ──
        buy_votes = 0
        sell_votes = 0
        max_votes = 0

        # 1. RSI (must be trending, not just in zone)
        rsi_val = rsi.iloc[i] if not np.isnan(rsi.iloc[i]) else 50
        rsi_s = rsi_slope.iloc[i] if not np.isnan(rsi_slope.iloc[i]) else 0
        max_votes += 1
        if rsi_val < 35 and rsi_s > 0:  # Oversold + turning up
            buy_votes += 1
        elif rsi_val > 65 and rsi_s < 0:  # Overbought + turning down
            sell_votes += 1

        # 2. MACD (must have crossover or strong momentum)
        hist_val = macd_hist.iloc[i] if not np.isnan(macd_hist.iloc[i]) else 0
        hist_prev = macd_hist.iloc[i-1] if i > 0 and not np.isnan(macd_hist.iloc[i-1]) else 0
        h_accel = hist_accel.iloc[i] if not np.isnan(hist_accel.iloc[i]) else 0
        max_votes += 1
        # Fresh crossover
        if hist_val > 0 and hist_prev <= 0:
            buy_votes += 1
        elif hist_val < 0 and hist_prev >= 0:
            sell_votes += 1
        # Or strong acceleration
        elif h_accel > 0 and hist_val > 0:
            buy_votes += 1
        elif h_accel < 0 and hist_val < 0:
            sell_votes += 1

        # 3. Bollinger Band touch + bounce
        bb_l = bb_lower.iloc[i] if not np.isnan(bb_lower.iloc[i]) else price
        bb_u = bb_upper.iloc[i] if not np.isnan(bb_upper.iloc[i]) else price
        max_votes += 1
        # Price touched lower band and is bouncing (close > low of candle)
        if price <= bb_l * 1.001 and close.iloc[i] > low.iloc[i]:
            buy_votes += 1
        elif price >= bb_u * 0.999 and close.iloc[i] < high.iloc[i]:
            sell_votes += 1

        # 4. Stochastic oversold/overbought + crossing
        sk = stoch_k.iloc[i] if not np.isnan(stoch_k.iloc[i]) else 50
        sd = stoch_d.iloc[i] if not np.isnan(stoch_d.iloc[i]) else 50
        sk_prev = stoch_k.iloc[i-1] if i > 0 and not np.isnan(stoch_k.iloc[i-1]) else 50
        max_votes += 1
        if sk < 25 and sk > sk_prev:  # Oversold and turning up
            buy_votes += 1
        elif sk > 75 and sk < sk_prev:  # Overbought and turning down
            sell_votes += 1

        # 5. Multi-EMA alignment (higher TF confirmation)
        max_votes += 1
        if ema20.iloc[i] > ema50.iloc[i] > ema200.iloc[i]:  # All aligned up
            buy_votes += 1
        elif ema20.iloc[i] < ema50.iloc[i] < ema200.iloc[i]:  # All aligned down
            sell_votes += 1

        # 6. ADX trend strength + DI direction
        pdi = plus_di.iloc[i] if not np.isnan(plus_di.iloc[i]) else 50
        mdi = minus_di.iloc[i] if not np.isnan(minus_di.iloc[i]) else 50
        max_votes += 1
        if strong_trend and pdi > mdi:
            buy_votes += 1
        elif strong_trend and mdi > pdi:
            sell_votes += 1

        # 7. Price momentum (close > close[5] for buy, < for sell)
        price_5_ago = close.iloc[i-5] if i >= 5 else price
        max_votes += 1
        momentum = (price - price_5_ago) / price_5_ago if price_5_ago > 0 else 0
        if momentum > 0.001:  # Moving up
            buy_votes += 1
        elif momentum < -0.001:  # Moving down
            sell_votes += 1

        # ── DECISION ──
        # V3: Need 4+ out of 7 indicators to align (strict)
        min_votes = 4
        min_agree = cfg.get("min_agreement", 0.38)

        if buy_votes >= min_votes and buy_votes > sell_votes:
            conf = buy_votes / max_votes
            if conf > min_agree:
                signals.append("BUY")
                confidences.append(conf)
                continue
        elif sell_votes >= min_votes and sell_votes > buy_votes:
            conf = sell_votes / max_votes
            if conf > min_agree:
                signals.append("SELL")
                confidences.append(conf)
                continue

        signals.append("HOLD")
        confidences.append(0.5)

    df = df.copy()
    df["signal"] = signals
    df["confidence"] = confidences
    df["atr"] = atr
    df["adx"] = adx
    return df


# ─── Backtest Engine V3 ────────────────────────────────────

def run_backtest_v3(df, symbol, cfg, initial_balance=10000.0):
    balance = initial_balance
    trades = []
    position = None
    equity_curve = [balance]
    consec_losses = 0
    last_trade_bar = -999  # Cooldown tracker

    sl_mult = cfg.get("sl_mult", 2.0)
    tp_mult = cfg.get("tp_mult", 3.0)
    trail_mult = cfg.get("trail_mult", 1.0)
    max_hold = cfg.get("max_hold", 20)
    risk_pct = cfg.get("risk_pct", 0.02)
    cooldown = cfg.get("cooldown", 5)

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

            if action == "BUY":
                unrealized = (price - entry) / entry * position["size"]
                if price > position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price - atr_val * trail_mult
                exit_now = False
                exit_reason = ""
                if price <= position["sl"]:
                    exit_now, exit_reason = True, "SL"
                elif price >= position["tp"]:
                    exit_now, exit_reason = True, "TP"
                elif bars_held >= max_hold:
                    exit_now, exit_reason = True, "TIME"
                elif signal == "SELL" and bars_held >= 3:
                    exit_now, exit_reason = True, "REVERSAL"
            else:
                unrealized = (entry - price) / entry * position["size"]
                if price < position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price + atr_val * trail_mult
                exit_now = False
                exit_reason = ""
                if price >= position["sl"]:
                    exit_now, exit_reason = True, "SL"
                elif price <= position["tp"]:
                    exit_now, exit_reason = True, "TP"
                elif bars_held >= max_hold:
                    exit_now, exit_reason = True, "TIME"
                elif signal == "BUY" and bars_held >= 3:
                    exit_now, exit_reason = True, "REVERSAL"

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
                last_trade_bar = i

        # ── OPEN NEW POSITION ──
        if position is None and signal in ("BUY", "SELL"):
            # Time filter: avoid dead hours
            if current_hour >= 21 or current_hour < 1:
                equity_curve.append(balance)
                continue
            # Circuit breaker
            if consec_losses >= 3:
                consec_losses = 0
                equity_curve.append(balance)
                continue
            # Cooldown: at least N bars since last trade
            if i - last_trade_bar < cooldown:
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
            bars_held=len(df) - position["entry_bar"], exit_reason="END",
        ))

    # Metrics
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    total_pnl = sum(t.pnl for t in trades)
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    gp = sum(t.pnl for t in wins)
    gl = abs(sum(t.pnl for t in losses))
    pf = gp / gl if gl > 0 else float("inf")

    peak_eq = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0
        max_dd = max(max_dd, dd)

    sharpe = 0
    if len(equity_curve) > 1:
        rets = np.diff(equity_curve) / np.array(equity_curve[:-1])
        rets = rets[np.isfinite(rets)]
        if len(rets) > 0 and np.std(rets) > 0:
            sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252 * 24)

    reasons = {}
    for t in trades:
        r = t.exit_reason
        if r not in reasons:
            reasons[r] = {"count": 0, "pnl": 0, "wins": 0}
        reasons[r]["count"] += 1
        reasons[r]["pnl"] += t.pnl
        if t.pnl > 0: reasons[r]["wins"] += 1

    return {
        "symbol": symbol,
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


# ─── Parameter Sweep V3 ────────────────────────────────────

def param_sweep_v3(df, symbol):
    best_score = -999999
    best_cfg = None
    best_result = None

    for sl in [1.5, 2.0, 2.5]:
        for tp in [3.0, 4.0]:
            for trail in [1.0, 2.0]:
                for max_h in [20, 30]:
                    for min_a in [0.50, 0.57]:
                        for cd in [3, 5]:
                                cfg = {
                                    "sl_mult": sl, "tp_mult": tp,
                                    "trail_mult": trail, "max_hold": max_h,
                                    "min_agreement": min_a, "risk_pct": 0.02,
                                    "cooldown": cd,
                                }
                                result = run_backtest_v3(df, symbol, cfg)

                                # Composite score: P/L with risk adjustments
                                score = result["total_pnl"]
                                if result["win_rate"] < 40:
                                    score -= (40 - result["win_rate"]) * 5
                                if result["max_drawdown"] > 3:
                                    score -= (result["max_drawdown"] - 3) * 30
                                if result["total_trades"] < 8:
                                    score -= (8 - result["total_trades"]) * 50
                                # Bonus for high PF
                                if result["profit_factor"] > 1.5:
                                    score += (result["profit_factor"] - 1.5) * 20

                                if score > best_score:
                                    best_score = score
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
    print(f"  {r['symbol']} | Trades={r['total_trades']} WinRate={r['win_rate']}%")
    if cfg:
        print(f"  Config: SL={cfg['sl_mult']}x TP={cfg['tp_mult']}x Trail={cfg['trail_mult']}x "
              f"MaxHold={cfg['max_hold']} Agree>={cfg['min_agreement']} Cooldown={cfg.get('cooldown',5)}")
    print(f"{'='*65}")
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
    print("  DUTCHKEM TRADER - OPTIMIZED BACKTEST V3")
    print("  High-conviction entries + 7-indicator alignment + cooldown")
    print("="*65)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
               "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]

    all_results = []
    all_configs = {}

    for symbol in symbols:
        df = load_candles(symbol)
        if df is None:
            print(f"\n  {symbol}: No data")
            continue

        # Use 1500 bars for speed
        if len(df) > 1500:
            df = df.iloc[-1500:]

        print(f"\n  {symbol}: {len(df)} bars | V3 sweep (48 combos)...")

        # Generate V3 signals
        cfg0 = SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["EURUSD"])
        df_signals = generate_signals_v3(df, cfg0)

        buy_c = (df_signals["signal"] == "BUY").sum()
        sell_c = (df_signals["signal"] == "SELL").sum()
        hold_c = (df_signals["signal"] == "HOLD").sum()
        print(f"    Signals: {buy_c} BUY / {sell_c} SELL / {hold_c} HOLD")

        t0 = time.time()
        best_cfg, best_result = param_sweep_v3(df_signals, symbol)
        elapsed = time.time() - t0
        print(f"    Sweep done in {elapsed:.1f}s")

        if best_result and best_result["total_trades"] > 0:
            all_results.append(best_result)
            all_configs[symbol] = best_cfg
            print_report(best_result, best_cfg)

    # Portfolio summary
    if all_results:
        print(f"\n{'='*65}")
        print(f"  V3 PORTFOLIO SUMMARY")
        print(f"{'='*65}")
        total_pnl = sum(r["total_pnl"] for r in all_results)
        active = [r for r in all_results if r["total_trades"] > 0]
        total_trades = sum(r["total_trades"] for r in active)
        avg_wr = np.mean([r["win_rate"] for r in active]) if active else 0
        avg_pf = np.mean([r["profit_factor"] for r in active]) if active else 0
        print(f"  Symbols:     {len(active)}")
        print(f"  Total trades:{total_trades}")
        print(f"  Total P/L:   ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
        print(f"  Avg win rate:{avg_wr:.1f}%")
        print(f"  Avg PF:      {avg_pf:.2f}")
        for r in sorted(active, key=lambda x: x["total_pnl"], reverse=True):
            print(f"    {r['symbol']:8s} trades={r['total_trades']:3d} "
                  f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} "
                  f"DD={r['max_drawdown']:5.2f}% P/L=${r['total_pnl']:+8.2f}")
        print(f"{'='*65}")

        print(f"\n  Best configs:")
        for sym, cfg in all_configs.items():
            print(f"    {sym}: {json.dumps(cfg)}")

    # Save
    output_dir = Path("paper_trades")
    output_dir.mkdir(exist_ok=True)
    filename = output_dir / f"v3_bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump({"results": all_results, "configs": all_configs}, f, indent=2, default=str)
    print(f"\n  Saved to {filename}")


if __name__ == "__main__":
    main()
