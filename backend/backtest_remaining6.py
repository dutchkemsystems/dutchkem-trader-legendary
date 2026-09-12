"""
Run optimized backtest on 6 remaining symbols one at a time.
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from backtest_optimized import *
import pandas as pd
from pathlib import Path

symbols = ["USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY"]
all_results = []
all_configs = {}

for symbol in symbols:
    df = load_candles(symbol)
    if df is None:
        print(f"\n  {symbol}: No data, skipping")
        continue

    # Limit to 2000 bars for speed
    if len(df) > 2000:
        df = df.iloc[-2000:]

    print(f"\n  {symbol}: {len(df)} bars | Sweep 32 combos...")
    cfg0 = SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["EURUSD"])
    df_signals = generate_signals(df, cfg0)

    # Quick signal stats
    buy_c = (df_signals["signal"] == "BUY").sum()
    sell_c = (df_signals["signal"] == "SELL").sum()
    hold_c = (df_signals["signal"] == "HOLD").sum()
    print(f"    Signals: {buy_c} BUY / {sell_c} SELL / {hold_c} HOLD")

    t0 = time.time()
    best_cfg, best_result = param_sweep(df_signals, symbol)
    elapsed = time.time() - t0
    print(f"    Sweep done in {elapsed:.1f}s")

    if best_result and best_result["total_trades"] > 0:
        all_results.append(best_result)
        all_configs[symbol] = best_cfg
        print_report(best_result, best_cfg)
    else:
        print(f"    No trades generated!")

# Summary
if all_results:
    print(f"\n{'='*65}")
    print(f"  6 REMAINING SYMBOLS - SUMMARY")
    print(f"{'='*65}")
    total_pnl = sum(r["total_pnl"] for r in all_results)
    for r in sorted(all_results, key=lambda x: x["total_pnl"], reverse=True):
        print(f"    {r['symbol']:8s} trades={r['total_trades']:3d} "
              f"win={r['win_rate']:4.0f}% PF={r['profit_factor']:5.2f} "
              f"DD={r['max_drawdown']:5.2f}% P/L=${r['total_pnl']:+8.2f}")
    print(f"  {'='*65}")
    print(f"  Total P/L: ${total_pnl:+,.2f} ({total_pnl/100:.1f}%)")
    print(f"  Best configs:")
    for sym, cfg in all_configs.items():
        print(f"    {sym}: {json.dumps(cfg)}")
    print(f"{'='*65}")

    # Save
    filename = Path("paper_trades") / f"remaining6_bt_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump({"results": [asdict(r) for r in all_results] if hasattr(all_results[0], 'symbol') else all_results, 
                    "configs": all_configs}, f, indent=2, default=str)
    print(f"\n  Saved to {filename}")
