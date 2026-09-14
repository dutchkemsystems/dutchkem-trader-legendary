"""
Fast V3: Run all 10 symbols one at a time with targeted sweep.
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from backtest_v3 import *
import pandas as pd
from pathlib import Path

symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
           "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]

all_results = []
all_configs = {}

for symbol in symbols:
    df = load_candles(symbol)
    if df is None:
        print(f"\n  {symbol}: No data")
        continue
    if len(df) > 1500:
        df = df.iloc[-1500:]

    print(f"\n  {symbol}: {len(df)} bars")

    cfg0 = SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["EURUSD"])
    df_s = generate_signals_v3(df, cfg0)

    buy_c = (df_s["signal"] == "BUY").sum()
    sell_c = (df_s["signal"] == "SELL").sum()
    total_sig = buy_c + sell_c
    print(f"    Signals: {buy_c} BUY / {sell_c} SELL (total={total_sig})")

    if total_sig == 0:
        print(f"    No signals, skipping")
        continue

    # Targeted sweep: 24 combos only
    best_score = -999999
    best_cfg = None
    best_result = None
    t0 = time.time()

    for sl in [1.5, 2.5]:
        for tp in [3.0, 4.0]:
            for trail in [1.0, 2.0]:
                for cd in [3, 5]:
                    cfg = {
                        "sl_mult": sl, "tp_mult": tp,
                        "trail_mult": trail, "max_hold": 25,
                        "min_agreement": 0.50, "risk_pct": 0.02,
                        "cooldown": cd,
                    }
                    result = run_backtest_v3(df_s, symbol, cfg)
                    score = result["total_pnl"]
                    if result["win_rate"] < 40:
                        score -= (40 - result["win_rate"]) * 5
                    if result["max_drawdown"] > 3:
                        score -= (result["max_drawdown"] - 3) * 30
                    if result["total_trades"] < 5:
                        score -= (5 - result["total_trades"]) * 50
                    if result["profit_factor"] > 1.5:
                        score += (result["profit_factor"] - 1.5) * 20
                    if score > best_score:
                        best_score = score
                        best_cfg = cfg
                        best_result = result

    elapsed = time.time() - t0
    print(f"    Sweep: {elapsed:.1f}s")

    if best_result and best_result["total_trades"] > 0:
        all_results.append(best_result)
        all_configs[symbol] = best_cfg
        print_report(best_result, best_cfg)
    else:
        print(f"    No trades!")

# Summary
if all_results:
    print(f"\n{'='*65}")
    print(f"  V3 PORTFOLIO SUMMARY")
    print(f"{'='*65}")
    total_pnl = sum(r["total_pnl"] for r in all_results)
    total_trades = sum(r["total_trades"] for r in all_results)
    avg_wr = np.mean([r["win_rate"] for r in all_results]) if all_results else 0
    avg_pf = np.mean([r["profit_factor"] for r in all_results]) if all_results else 0
    print(f"  Symbols:     {len(all_results)}")
    print(f"  Total trades:{total_trades}")
    print(f"  Total P/L:   ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
    print(f"  Avg win rate:{avg_wr:.1f}%")
    print(f"  Avg PF:      {avg_pf:.2f}")
    for r in sorted(all_results, key=lambda x: x["total_pnl"], reverse=True):
        print(f"    {r['symbol']:8s} trades={r['total_trades']:3d} "
              f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} "
              f"DD={r['max_drawdown']:5.2f}% P/L=${r['total_pnl']:+8.2f}")
    print(f"{'='*65}")
    print(f"\n  Best configs:")
    for sym, cfg in all_configs.items():
        print(f"    {sym}: {json.dumps(cfg)}")

filename = Path("paper_trades") / f"v3_final_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(filename, "w") as f:
    json.dump({"results": all_results, "configs": all_configs}, f, indent=2, default=str)
print(f"\n  Saved to {filename}")
