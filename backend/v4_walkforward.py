"""
V4 WALK-FORWARD — STREAMLINED (16 combos per symbol)
"""
import sys, json, time, random
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime
from backtest_v4_hybrid import generate_signals_v4, run_backtest_v4

def load_data(symbol):
    csv_path = Path("paper_trades") / f"{symbol}_1H.csv"
    if not csv_path.exists(): return None
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    req = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in req): return None
    return df[req]

def monte_carlo(trades, n_sims=1000):
    pnls = [t["pnl"] for t in trades]
    if not pnls: return {"median": 0, "p5": 0, "p95": 0, "prob_pos": 0}
    results = sorted([sum(random.choices(pnls, k=len(pnls))) for _ in range(n_sims)])
    return {"median": round(np.median(results),2), "p5": round(results[50],2),
            "p95": round(results[949],2), "prob_pos": round(sum(1 for r in results if r>0)/10,1)}

SYMBOLS = ["EURUSD","GBPUSD","USDJPY","XAUUSD","USDCHF","AUDUSD","USDCAD","NZDUSD","EURGBP","EURJPY"]

# Sweep: 16 combos
SWEEP = []
for sl in [1.5, 3.0]:
    for tp in [3.0, 6.0]:
        for ma in [0.38, 0.52]:
            for risk in [0.025, 0.035]:
                SWEEP.append({"sl_mult": sl, "tp_mult": tp, "trail_mult": 1.5,
                              "max_hold": 25, "risk_pct": risk, "cooldown": 5, "min_agreement": ma})

print(f"\n{'='*65}")
print(f"  V4 WALK-FORWARD OPTIMIZER — STREAMLINED")
print(f"  16 combos | 70/30 split | Monte Carlo | {len(SYMBOLS)} symbols")
print(f"{'='*65}")

all_validated = {}
all_final = []
final_configs = {}

for symbol in SYMBOLS:
    df = load_data(symbol)
    if df is None or len(df) < 300:
        print(f"\n  {symbol}: No data"); continue

    split = int(len(df) * 0.7)
    df_is, df_oos = df.iloc[:split], df.iloc[split:]
    if len(df_oos) < 80:
        print(f"\n  {symbol}: OOS too small"); continue

    print(f"\n  {symbol}: IS={len(df_is)} OOS={len(df_oos)} bars")

    # IS: generate signals + sweep
    df_is_sigs = generate_signals_v4(df_is, 0.35)
    buy_c = (df_is_sigs["signal"]=="BUY").sum()
    sell_c = (df_is_sigs["signal"]=="SELL").sum()
    print(f"    Signals: {buy_c}B / {sell_c}S")
    if buy_c + sell_c == 0: continue

    t0 = time.time()
    is_results = []
    for cfg in SWEEP:
        result = run_backtest_v4(df_is_sigs, symbol, cfg)
        score = result["total_pnl"]
        if result["win_rate"] < 40: score -= (40-result["win_rate"])*3
        if result["max_drawdown"] > 2: score -= (result["max_drawdown"]-2)*50
        if result["total_trades"] < 5: score -= (5-result["total_trades"])*30
        is_results.append((cfg, result, score))
    is_results.sort(key=lambda x: x[2], reverse=True)
    elapsed = time.time() - t0

    # OOS: test top 5 configs
    df_oos_sigs = generate_signals_v4(df_oos, 0.35)
    valid = []
    for cfg, is_r, score in is_results[:5]:
        oos_r = run_backtest_v4(df_oos_sigs, symbol, cfg)
        if oos_r["max_drawdown"] <= 2.0 and oos_r["sharpe"] >= 0 and oos_r["total_trades"] >= 3:
            valid.append((cfg, is_r, oos_r))

    print(f"    Sweep: {elapsed:.1f}s | OOS passed: {len(valid)}/{min(5, len(is_results))}")

    if valid:
        best_cfg, best_is, best_oos = valid[0]
        mc = monte_carlo(best_oos["trades"]) if best_oos["trades"] else {}
        all_final.append({"symbol": symbol, "cfg": best_cfg, "is": best_is, "oos": best_oos, "mc": mc})
        final_configs[symbol] = best_cfg
        print(f"    IS:  P/L=${best_is['total_pnl']:+.2f} WR={best_is['win_rate']}% PF={best_is['profit_factor']} DD={best_is['max_drawdown']}%")
        print(f"    OOS: P/L=${best_oos['total_pnl']:+.2f} WR={best_oos['win_rate']}% PF={best_oos['profit_factor']} DD={best_oos['max_drawdown']}% Sh={best_oos['sharpe']}")
        if mc:
            print(f"    MC:  Median=${mc['median']:+.2f} P5=${mc['p5']:+.2f} P95=${mc['p95']:+.2f} P(+)={mc['prob_pos']}%")

# ── SUMMARY ──
print(f"\n{'='*65}")
print(f"  V4 OPTIMIZED — FINAL RESULTS (OOS)")
print(f"{'='*65}")

if all_final:
    total_oos = sum(f["oos"]["total_pnl"] for f in all_final)
    total_is = sum(f["is"]["total_pnl"] for f in all_final)
    total_trades = sum(f["oos"]["total_trades"] for f in all_final)
    avg_wr = np.mean([f["oos"]["win_rate"] for f in all_final])
    avg_pf = np.mean([f["oos"]["profit_factor"] for f in all_final])
    avg_dd = np.mean([f["oos"]["max_drawdown"] for f in all_final])
    avg_sh = np.mean([f["oos"]["sharpe"] for f in all_final])
    prof_sym = sum(1 for f in all_final if f["oos"]["total_pnl"] > 0)

    print(f"\n  Symbols traded: {len(all_final)} ({prof_sym} profitable)")
    print(f"  Total IS P/L:   ${total_is:+,.2f} ({total_is/100:.1f}%)")
    print(f"  Total OOS P/L:  ${total_oos:+,.2f} ({total_oos/100:.1f}%)")
    print(f"  Total trades:   {total_trades}")
    print(f"  Avg win rate:   {avg_wr:.1f}%")
    print(f"  Avg PF:         {avg_pf:.2f}")
    print(f"  Avg DD:         {avg_dd:.2f}%")
    print(f"  Avg Sharpe:     {avg_sh:.2f}")

    print(f"\n  Per Symbol (OOS):")
    for f in sorted(all_final, key=lambda x: x["oos"]["total_pnl"], reverse=True):
        mc_info = ""
        if f["mc"]:
            mc_info = f" MC:P(+)={f['mc']['prob_pos']}%"
        print(f"    {f['symbol']:8s} OOS=${f['oos']['total_pnl']:+8.2f} "
              f"WR={f['oos']['win_rate']:4.0f}% PF={f['oos']['profit_factor']:5.2f} "
              f"DD={f['oos']['max_drawdown']:5.2f}% Sh={f['oos']['sharpe']:5.2f}{mc_info}")

    print(f"\n  COMPARISON:")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"  {'Strategy':20s} {'P/L':>10s} {'WR':>6s} {'PF':>6s} {'DD':>6s} {'Sh':>6s}")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"  {'V2 Original':20s} {'+$335':>10s} {'40%':>6s} {'1.20':>6s} {'3.0%':>6s} {'1.7':>6s}")
    print(f"  {'V3 @2%':20s} {'+$300':>10s} {'47%':>6s} {'1.84':>6s} {'0.9%':>6s} {'4.0':>6s}")
    print(f"  {'V3 @3%':20s} {'+$297':>10s} {'47%':>6s} {'1.82':>6s} {'0.2%':>6s} {'1.8':>6s}")
    print(f"  {'V4 Unopt':20s} {'+$226':>10s} {'45%':>6s} {'1.54':>6s} {'1.0%':>6s} {'2.0':>6s}")
    v4opt_str = f"${total_oos:+,.2f}"
    print(f"  {'V4 Optimized (OOS)':20s} {v4opt_str:>10s} {f'{avg_wr:.0f}%':>6s} {f'{avg_pf:.2f}':>6s} {f'{avg_dd:.1f}%':>6s} {f'{avg_sh:.1f}':>6s}")
    print(f"  ─────────────────────────────────────────────────────")

    if total_oos > 300 and avg_pf > 1.8 and avg_dd < 2.0 and avg_sh > 2.0:
        print(f"\n  VERDICT: V4-OPT WINS!")
        verdict = "V4_OPT"
    elif total_oos > 226 and avg_pf > 1.54:
        print(f"\n  VERDICT: V4-OPT IMPROVES over unopt V4 but doesn't beat V3")
        verdict = "V4_BETTER"
    else:
        print(f"\n  VERDICT: V3 @3% SIZING IS STILL BEST")
        verdict = "V3"

    print(f"\n  Best configs:")
    for sym, cfg in final_configs.items():
        print(f"    {sym}: {json.dumps(cfg)}")

    filename = Path("paper_trades") / f"v4_opt_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump({"verdict": verdict, "configs": final_configs,
                    "total_oos_pnl": total_oos, "total_is_pnl": total_is,
                    "avg_wr": avg_wr, "avg_pf": avg_pf, "avg_dd": avg_dd, "avg_sharpe": avg_sh,
                    "per_symbol": [{"sym": x["symbol"], "oos_pnl": x["oos"]["total_pnl"],
                                    "wr": x["oos"]["win_rate"], "pf": x["oos"]["profit_factor"],
                                    "dd": x["oos"]["max_drawdown"], "sh": x["oos"]["sharpe"],
                                    "mc": x["mc"]} for x in all_final]}, f, indent=2, default=str)
    print(f"\n  Saved to {filename}")
else:
    print(f"\n  No validated configs found!")
