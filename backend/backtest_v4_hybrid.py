"""
V4 HYBRID BACKTEST — Best of Both Worlds
==========================================
- SIGNALS: V2's aggressive weighted scoring (min_agreement 0.38) — more trades
- EXITS: V3's wider SL/TP + trailing stop + cooldown — better risk mgmt
- SIZING: 3% risk per trade (up from 2%) — higher returns
- ENTRY GATE: Require at least 1 confirmation (RSI/MACD/BB) — fewer false entries
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from datetime import datetime

SYMBOL_CONFIG = {
    "EURUSD": {"sl_mult": 1.5, "tp_mult": 3.5, "trail_mult": 1.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
    "GBPUSD": {"sl_mult": 1.5, "tp_mult": 3.5, "trail_mult": 2.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 5},
    "USDJPY": {"sl_mult": 2.5, "tp_mult": 3.5, "trail_mult": 1.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
    "XAUUSD": {"sl_mult": 1.5, "tp_mult": 3.0, "trail_mult": 2.0, "max_hold": 25, "risk_pct": 0.02, "cooldown": 5},
    "USDCHF": {"sl_mult": 2.5, "tp_mult": 3.0, "trail_mult": 2.0, "max_hold": 25, "risk_pct": 0.02, "cooldown": 3},
    "AUDUSD": {"sl_mult": 1.5, "tp_mult": 3.5, "trail_mult": 2.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
    "USDCAD": {"sl_mult": 2.5, "tp_mult": 3.5, "trail_mult": 1.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 5},
    "NZDUSD": {"sl_mult": 2.5, "tp_mult": 3.5, "trail_mult": 1.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
    "EURGBP": {"sl_mult": 1.5, "tp_mult": 3.0, "trail_mult": 1.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
    "EURJPY": {"sl_mult": 1.5, "tp_mult": 3.5, "trail_mult": 2.0, "max_hold": 25, "risk_pct": 0.03, "cooldown": 3},
}


@dataclass
class Trade:
    entry_time: str; exit_time: str; symbol: str; action: str
    entry_price: float; exit_price: float; size: float
    pnl: float; pnl_pct: float; bars_held: int; exit_reason: str


# ─── Indicators (same as V3) ──────────────────────────────

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
    return macd, signal, macd - signal

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

def calc_ema(close, period):
    return close.ewm(span=period).mean()


# ─── V2 SIGNAL GENERATOR (aggressive, more trades) ────────

def generate_signals_v4(df: pd.DataFrame, min_agreement: float = 0.38) -> pd.DataFrame:
    """V2's weighted scoring — produces more trades than V3's strict 4/7 gate."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    rsi = calc_rsi(close)
    macd_line, macd_signal, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    atr = calc_atr(high, low, close)
    stoch_k, stoch_d = calc_stoch(high, low, close)

    ema200 = close.ewm(span=200).mean()
    ema50 = close.ewm(span=50).mean()

    atr_pct = atr / close
    atr_pct_median = atr_pct.rolling(100).median()
    atr_ratio = atr_pct / atr_pct_median.replace(0, np.nan)

    signals = []
    confidences = []

    for i in range(len(df)):
        price = close.iloc[i]

        uptrend = price > ema200.iloc[i] if not np.isnan(ema200.iloc[i]) else None
        atr_r = atr_ratio.iloc[i] if not np.isnan(atr_ratio.iloc[i]) else 1.0
        if atr_r < 0.5 or atr_r > 3.0:
            signals.append("HOLD")
            confidences.append(0.5)
            continue

        buy_score = 0; sell_score = 0; total_weight = 0

        # RSI (w: 2)
        rsi_val = rsi.iloc[i] if not np.isnan(rsi.iloc[i]) else 50
        total_weight += 2
        if rsi_val < 30: buy_score += 2 * 0.9
        elif rsi_val > 70: sell_score += 2 * 0.9
        elif rsi_val < 40: buy_score += 2 * 0.5
        elif rsi_val > 60: sell_score += 2 * 0.5

        # MACD (w: 2)
        hist_val = macd_hist.iloc[i] if not np.isnan(macd_hist.iloc[i]) else 0
        hist_prev = macd_hist.iloc[i-1] if i > 0 and not np.isnan(macd_hist.iloc[i-1]) else 0
        total_weight += 2
        if hist_val > 0 and hist_prev <= 0: buy_score += 2 * 0.95
        elif hist_val < 0 and hist_prev >= 0: sell_score += 2 * 0.95
        elif hist_val > 0: buy_score += 2 * 0.4
        elif hist_val < 0: sell_score += 2 * 0.4

        # BB (w: 1.5)
        bb_l = bb_lower.iloc[i] if not np.isnan(bb_lower.iloc[i]) else price
        bb_u = bb_upper.iloc[i] if not np.isnan(bb_upper.iloc[i]) else price
        bb_m = bb_mid.iloc[i] if not np.isnan(bb_mid.iloc[i]) else price
        total_weight += 1.5
        if price <= bb_l: buy_score += 1.5 * 0.8
        elif price >= bb_u: sell_score += 1.5 * 0.8
        elif price < bb_m: buy_score += 1.5 * 0.2
        else: sell_score += 1.5 * 0.2

        # Stoch (w: 1)
        sk = stoch_k.iloc[i] if not np.isnan(stoch_k.iloc[i]) else 50
        total_weight += 1
        if sk < 20: buy_score += 1 * 0.7
        elif sk > 80: sell_score += 1 * 0.7

        # Trend bonus (w: 3)
        total_weight += 3
        if uptrend is not None:
            if uptrend:
                buy_score += 3 * 0.7; sell_score += 3 * 0.1
            else:
                sell_score += 3 * 0.7; buy_score += 3 * 0.1

        # Momentum confirmation
        if uptrend is not None:
            if uptrend and buy_score > sell_score:
                rsi_ok = rsi_val < 50; macd_ok = hist_val > hist_prev; bb_ok = price <= bb_m
                if not (rsi_ok or macd_ok or bb_ok): buy_score *= 0.3
            elif not uptrend and sell_score > buy_score:
                rsi_ok = rsi_val > 50; macd_ok = hist_val < hist_prev; bb_ok = price >= bb_m
                if not (rsi_ok or macd_ok or bb_ok): sell_score *= 0.3

        buy_conf = buy_score / total_weight if total_weight > 0 else 0
        sell_conf = sell_score / total_weight if total_weight > 0 else 0

        if buy_conf > sell_conf and buy_conf > min_agreement:
            signals.append("BUY"); confidences.append(buy_conf)
        elif sell_conf > buy_conf and sell_conf > min_agreement:
            signals.append("SELL"); confidences.append(sell_conf)
        else:
            signals.append("HOLD"); confidences.append(0.5)

    df = df.copy()
    df["signal"] = signals
    df["confidence"] = confidences
    df["atr"] = atr
    return df


# ─── V4 BACKTEST ENGINE (V3 exits + 3% sizing) ────────────

def run_backtest_v4(df, symbol, cfg, initial_balance=10000.0):
    """V4 backtest. If cfg has min_agreement, filter signals by confidence threshold."""
    balance = initial_balance
    trades = []
    position = None
    equity_curve = [balance]
    consec_losses = 0
    last_trade_bar = -999

    sl_mult = cfg.get("sl_mult", 2.0)
    tp_mult = cfg.get("tp_mult", 3.5)
    trail_mult = cfg.get("trail_mult", 1.0)
    max_hold = cfg.get("max_hold", 25)
    risk_pct = cfg.get("risk_pct", 0.03)
    cooldown = cfg.get("cooldown", 3)
    min_conf = cfg.get("min_agreement", 0.35)

    for i in range(200, len(df)):
        price = float(df.iloc[i]["close"])
        high_i = float(df.iloc[i]["high"])
        low_i = float(df.iloc[i]["low"])
        current_time = str(df.index[i])[:19]
        current_hour = df.index[i].hour if hasattr(df.index[i], "hour") else 12
        atr_val = float(df.iloc[i]["atr"]) if not np.isnan(df.iloc[i]["atr"]) else 0
        signal = df.iloc[i]["signal"]
        confidence = df.iloc[i].get("confidence", 0.5)

        # Filter by confidence threshold
        if signal in ("BUY", "SELL") and confidence < min_conf:
            signal = "HOLD"

        # ── CLOSE EXISTING ──
        if position is not None:
            bars_held = i - position["entry_bar"]
            action = position["action"]
            entry = position["entry_price"]

            if action == "BUY":
                if price > position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price - atr_val * trail_mult
                exit_now = False; exit_reason = ""
                if price <= position["sl"]: exit_now, exit_reason = True, "SL"
                elif price >= position["tp"]: exit_now, exit_reason = True, "TP"
                elif bars_held >= max_hold: exit_now, exit_reason = True, "TIME"
                elif signal == "SELL" and bars_held >= 3: exit_now, exit_reason = True, "REVERSAL"
            else:
                if price < position.get("trail_peak", entry):
                    position["trail_peak"] = price
                    position["sl"] = price + atr_val * trail_mult
                exit_now = False; exit_reason = ""
                if price >= position["sl"]: exit_now, exit_reason = True, "SL"
                elif price <= position["tp"]: exit_now, exit_reason = True, "TP"
                elif bars_held >= max_hold: exit_now, exit_reason = True, "TIME"
                elif signal == "BUY" and bars_held >= 3: exit_now, exit_reason = True, "REVERSAL"

            if exit_now:
                pnl = (price - entry) / entry * position["size"] if action == "BUY" else (entry - price) / entry * position["size"]
                balance += pnl
                trades.append(Trade(
                    entry_time=position["entry_time"], exit_time=current_time,
                    symbol=symbol, action=action, entry_price=entry, exit_price=price,
                    size=position["size"], pnl=pnl,
                    pnl_pct=pnl / position["size"] * 100,
                    bars_held=bars_held, exit_reason=exit_reason,
                ))
                consec_losses = consec_losses + 1 if pnl <= 0 else 0
                position = None
                last_trade_bar = i

        # ── OPEN NEW ──
        if position is None and signal in ("BUY", "SELL"):
            if current_hour >= 21 or current_hour < 1:
                equity_curve.append(balance); continue
            if consec_losses >= 3:
                consec_losses = 0; equity_curve.append(balance); continue
            if i - last_trade_bar < cooldown:
                equity_curve.append(balance); continue

            risk_amount = balance * risk_pct
            sl_distance = atr_val * sl_mult
            if sl_distance <= 0:
                equity_curve.append(balance); continue
            sl_pct = sl_distance / price
            size = min(max(10, risk_amount / sl_pct if sl_pct > 0 else 0), balance * 0.20)

            if size <= balance:
                if signal == "BUY":
                    sl = price - sl_distance; tp = price + atr_val * tp_mult
                else:
                    sl = price + sl_distance; tp = price - atr_val * tp_mult
                position = {"action": signal, "entry_price": price, "entry_time": current_time,
                            "entry_bar": i, "size": size, "sl": sl, "tp": tp, "trail_peak": price}

        equity_curve.append(balance)

    if position is not None:
        price = float(df.iloc[-1]["close"])
        pnl = (price - position["entry_price"]) / position["entry_price"] * position["size"] if position["action"] == "BUY" else (position["entry_price"] - price) / position["entry_price"] * position["size"]
        balance += pnl
        trades.append(Trade(entry_time=position["entry_time"], exit_time=str(df.index[-1])[:19],
                            symbol=symbol, action=position["action"], entry_price=position["entry_price"],
                            exit_price=price, size=position["size"], pnl=pnl,
                            pnl_pct=pnl / position["size"] * 100,
                            bars_held=len(df) - position["entry_bar"], exit_reason="END"))

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    total_pnl = sum(t.pnl for t in trades)
    gp = sum(t.pnl for t in wins); gl = abs(sum(t.pnl for t in losses))
    pf = gp / gl if gl > 0 else float("inf")
    peak_eq = equity_curve[0]; max_dd = 0
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
        if r not in reasons: reasons[r] = {"count": 0, "pnl": 0, "wins": 0}
        reasons[r]["count"] += 1; reasons[r]["pnl"] += t.pnl
        if t.pnl > 0: reasons[r]["wins"] += 1

    return {
        "symbol": symbol, "total_trades": len(trades), "wins": len(wins),
        "losses": len(losses), "win_rate": round(win_rate * 100, 1),
        "final_balance": round(balance, 2), "total_pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl / initial_balance * 100, 2),
        "avg_win": round(np.mean([t.pnl for t in wins]), 2) if wins else 0,
        "avg_loss": round(np.mean([t.pnl for t in losses]), 2) if losses else 0,
        "profit_factor": round(pf, 2), "max_drawdown": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2), "exit_reasons": reasons,
        "trades": [asdict(t) for t in trades],
    }


# ─── Main ─────────────────────────────────────────────────

def main():
    print("\n" + "="*65)
    print("  DUTCHKEM TRADER — V4 HYBRID BACKTEST")
    print("  V2 signals (aggressive) + V3 exits (wider SL/TP) + 3% sizing")
    print("="*65)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
               "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]
    all_results = []; all_configs = {}

    for symbol in symbols:
        csv_path = Path("paper_trades") / f"{symbol}_1H.csv"
        if not csv_path.exists():
            print(f"\n  {symbol}: No data"); continue
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        req = ["open", "high", "low", "close", "volume"]
        if not all(c in df.columns for c in req):
            print(f"\n  {symbol}: Missing columns"); continue
        df = df[req]
        if len(df) > 1500: df = df.iloc[-1500:]

        print(f"\n  {symbol}: {len(df)} bars")

        t0 = time.time()
        # Generate signals once at lowest threshold
        df_signals = generate_signals_v4(df, 0.35)
        buy_c = (df_signals["signal"] == "BUY").sum()
        sell_c = (df_signals["signal"] == "SELL").sum()
        print(f"    Signals: {buy_c} BUY / {sell_c} SELL (total={buy_c+sell_c})")
        if buy_c + sell_c == 0:
            print(f"    No signals!"); continue

        best_score = -999999; best_cfg = None; best_result = None
        combos = 0
        for sl in [1.5, 2.5]:
            for tp in [3.0, 4.0]:
                for trail in [1.0, 2.0]:
                    for cd in [3, 5]:
                        for ma in [0.38, 0.45]:
                            cfg = {"sl_mult": sl, "tp_mult": tp, "trail_mult": trail,
                                   "max_hold": 25, "risk_pct": 0.03, "cooldown": cd,
                                   "min_agreement": ma}
                            result = run_backtest_v4(df_signals, symbol, cfg)
                            combos += 1
                            score = result["total_pnl"]
                            if result["win_rate"] < 40: score -= (40 - result["win_rate"]) * 5
                            if result["max_drawdown"] > 3: score -= (result["max_drawdown"] - 3) * 30
                            if result["total_trades"] < 8: score -= (8 - result["total_trades"]) * 50
                            if result["profit_factor"] > 1.5: score += (result["profit_factor"] - 1.5) * 20
                            if score > best_score:
                                best_score = score; best_cfg = cfg.copy()
                                best_result = result
        elapsed = time.time() - t0
        print(f"    Sweep: {elapsed:.1f}s ({combos} combos)")

        if best_result and best_result["total_trades"] > 0:
            all_results.append(best_result)
            all_configs[symbol] = best_cfg
            r = best_result
            print(f"  ── {symbol} ── Trades={r['total_trades']} WinRate={r['win_rate']}% PF={r['profit_factor']} ──")
            print(f"    Config: SL={best_cfg['sl_mult']}x TP={best_cfg['tp_mult']}x Trail={best_cfg['trail_mult']}x Risk={best_cfg['risk_pct']*100}% Agree>={best_cfg['min_agreement']} CD={best_cfg['cooldown']}")
            print(f"    P/L: ${r['total_pnl']:+,.2f} ({r['pnl_pct']:+.2f}%) | DD={r['max_drawdown']}% | Sharpe={r['sharpe']}")
            print(f"    AvgW=${r['avg_win']:+.2f} AvgL=${r['avg_loss']:+.2f}")
            for reason, data in sorted(r["exit_reasons"].items()):
                wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
                print(f"      {reason:10s} {data['count']:3d}t  WR={wr:.0f}%  P/L=${data['pnl']:+.2f}")

    if all_results:
        print(f"\n{'='*65}")
        print(f"  V4 HYBRID PORTFOLIO SUMMARY")
        print(f"{'='*65}")
        total_pnl = sum(r["total_pnl"] for r in all_results)
        total_trades = sum(r["total_trades"] for r in all_results)
        avg_wr = np.mean([r["win_rate"] for r in all_results])
        avg_pf = np.mean([r["profit_factor"] for r in all_results])
        print(f"  Symbols:      {len(all_results)}")
        print(f"  Total trades: {total_trades}")
        print(f"  Total P/L:    ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
        print(f"  Avg win rate: {avg_wr:.1f}%")
        print(f"  Avg PF:       {avg_pf:.2f}")
        print(f"  ── Per Symbol ──")
        for r in sorted(all_results, key=lambda x: x["total_pnl"], reverse=True):
            print(f"    {r['symbol']:8s} trades={r['total_trades']:3d} "
                  f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} "
                  f"DD={r['max_drawdown']:5.2f}% P/L=${r['total_pnl']:+8.2f}")
        print(f"{'='*65}")

        print(f"\n  Final configs for live engine:")
        for sym, cfg in all_configs.items():
            print(f"    {sym}: {json.dumps(cfg)}")

    filename = Path("paper_trades") / f"v4_hybrid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump({"results": all_results, "configs": all_configs}, f, indent=2, default=str)
    print(f"\n  Saved to {filename}")


if __name__ == "__main__":
    main()
