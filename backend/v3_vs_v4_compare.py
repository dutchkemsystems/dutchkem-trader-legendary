"""Run V3 with 3% sizing — direct comparison to V4."""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
import numpy as np
import pandas as pd
from backtest_v3 import *
from dataclasses import asdict

symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
           "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]

all_results = []; all_configs = {}

for symbol in symbols:
    csv_path = Path("paper_trades") / f"{symbol}_1H.csv"
    if not csv_path.exists(): continue
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    req = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in req): continue
    df = df[req]
    if len(df) > 1500: df = df.iloc[-1500:]

    print(f"\n  {symbol}: {len(df)} bars")

    # Generate V3 signals (strict 7-indicator alignment)
    cfg0 = SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["EURUSD"])
    df_s = generate_signals_v3(df, cfg0)
    buy_c = (df_s["signal"] == "BUY").sum()
    sell_c = (df_s["signal"] == "SELL").sum()
    print(f"    V3 signals: {buy_c} BUY / {sell_c} SELL (total={buy_c+sell_c})")

    if buy_c + sell_c == 0: print(f"    No signals!"); continue

    t0 = time.time()
    best_score = -999999; best_cfg = None; best_result = None
    combos = 0
    for sl in [1.5, 2.0, 2.5]:
        for tp in [3.0, 4.0]:
            for trail in [1.0, 2.0]:
                for cd in [3, 5]:
                    for ma in [0.50, 0.57]:
                        cfg = {"sl_mult": sl, "tp_mult": tp, "trail_mult": trail,
                               "max_hold": 25, "risk_pct": 0.03, "cooldown": cd,
                               "min_agreement": ma}
                        result = run_backtest_v3(df_s, symbol, cfg)
                        combos += 1
                        score = result["total_pnl"]
                        if result["win_rate"] < 40: score -= (40 - result["win_rate"]) * 5
                        if result["max_drawdown"] > 3: score -= (result["max_drawdown"] - 3) * 30
                        if result["total_trades"] < 8: score -= (8 - result["total_trades"]) * 50
                        if result["profit_factor"] > 1.5: score += (result["profit_factor"] - 1.5) * 20
                        if score > best_score:
                            best_score = score; best_cfg = cfg.copy(); best_result = result
    elapsed = time.time() - t0
    print(f"    Sweep: {elapsed:.1f}s ({combos} combos)")

    if best_result and best_result["total_trades"] > 0:
        all_results.append(best_result)
        all_configs[symbol] = best_cfg
        r = best_result
        print(f"    P/L=${r['total_pnl']:+8.2f} WR={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} DD={r['max_drawdown']:5.2f}% Sharpe={r['sharpe']:5.2f} trades={r['total_trades']}")
        print(f"    Config: SL={best_cfg['sl_mult']}x TP={best_cfg['tp_mult']}x Trail={best_cfg['trail_mult']}x Risk=3% Agree>={best_cfg['min_agreement']} CD={best_cfg['cooldown']}")

if all_results:
    print(f"\n{'='*65}")
    print(f"  V3 @ 3% SIZING — PORTFOLIO SUMMARY")
    print(f"{'='*65}")
    total_pnl = sum(r["total_pnl"] for r in all_results)
    total_trades = sum(r["total_trades"] for r in all_results)
    avg_wr = np.mean([r["win_rate"] for r in all_results])
    avg_pf = np.mean([r["profit_factor"] for r in all_results])
    avg_dd = np.mean([r["max_drawdown"] for r in all_results])
    avg_sharpe = np.mean([r["sharpe"] for r in all_results])
    print(f"  Symbols:      {len(all_results)}")
    print(f"  Total trades: {total_trades}")
    print(f"  Total P/L:    ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
    print(f"  Avg win rate: {avg_wr:.1f}%")
    print(f"  Avg PF:       {avg_pf:.2f}")
    print(f"  Avg DD:       {avg_dd:.2f}%")
    print(f"  Avg Sharpe:   {avg_sharpe:.2f}")
    print(f"\n  V3 vs V4 Comparison:")
    print(f"  ──────────────────────────────────────────────────────")
    print(f"  {'Symbol':8s} {'V3 P/L':>10s}  {'V4 P/L':>10s}  {'Winner':8s}")
    print(f"  ──────────────────────────────────────────────────────")

    v4_data = {
        "EURJPY": 71.75, "NZDUSD": 66.34, "GBPUSD": 32.38, "EURGBP": 32.23,
        "USDCAD": 29.96, "AUDUSD": 12.83, "EURUSD": 8.24, "XAUUSD": 6.33,
        "USDJPY": -6.05, "USDCHF": -28.07
    }
    v3_total = 0; v4_total = 0
    for r in sorted(all_results, key=lambda x: x["total_pnl"], reverse=True):
        v4p = v4_data.get(r["symbol"], 0)
        v3p = r["total_pnl"]
        v3_total += v3p; v4_total += v4p
        winner = "V3" if v3p > v4p else "V4" if v4p > v3p else "TIE"
        print(f"  {r['symbol']:8s} ${v3p:+8.2f}  ${v4p:+8.2f}  {winner:8s}")
    print(f"  ──────────────────────────────────────────────────────")
    print(f"  {'TOTAL':8s} ${v3_total:+8.2f}  ${v4_total:+8.2f}  {'V3' if v3_total > v4_total else 'V4'}")
    print(f"{'='*65}")

    print(f"\n  Best V3 configs (3% sizing):")
    for sym, cfg in all_configs.items():
        print(f"    {sym}: {json.dumps(cfg)}")

filename = Path("paper_trades") / f"v3_3pct_compare_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(filename, "w") as f:
    json.dump({"results": all_results, "configs": all_configs}, f, indent=2, default=str)
print(f"\n  Saved to {filename}")
