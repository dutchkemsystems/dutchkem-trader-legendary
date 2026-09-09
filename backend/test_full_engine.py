"""Test comprehensive live trading engine - full scan."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
import MetaTrader5 as mt5
from live_trading_full import connect_mt5, analyze_symbol_mtf, WATCHLIST, TIMEFRAMES, CONFIG

print("=" * 90)
print("COMPREHENSIVE LIVE TRADING ENGINE - TEST")
print(f"Instruments: {len(WATCHLIST)} | Timeframes: {len(TIMEFRAMES)}")
print(f"Total analyses: {len(WATCHLIST) * len(TIMEFRAMES)}")
print("=" * 90)

if not connect_mt5():
    print("FAILED: Cannot connect")
    sys.exit(1)

info = mt5.account_info()
print(f"Account: {info.login} | Balance: ${info.balance:,.2f}")
print()

# Analyze ALL 27 instruments
print("Scanning ALL 27 instruments across 7 timeframes...")
print()

signals = []
for i, sym in enumerate(WATCHLIST, 1):
    print(f"  [{i:2d}/27] {sym}...", end="", flush=True)
    action, total_score, weighted_score, details, atr, volatility = analyze_symbol_mtf(sym)

    tf_summary = ""
    if details:
        buy_tfs = [tf for tf, info in details.items() if info["action"] == "BUY"]
        sell_tfs = [tf for tf, info in details.items() if info["action"] == "SELL"]
        hold_tfs = [tf for tf, info in details.items() if info["action"] == "HOLD"]
        tf_summary = f"B={len(buy_tfs)} S={len(sell_tfs)} H={len(hold_tfs)}"

    if action != "HOLD":
        signals.append({
            "symbol": sym,
            "action": action,
            "total_score": total_score,
            "weighted_score": weighted_score,
            "price": details.get("H1", {}).get("price", 0),
            "atr": atr,
            "volatility": volatility,
            "details": details,
        })
        print(f" {action} (score={weighted_score:.2f}) [{tf_summary}]")
    else:
        print(f" HOLD [{tf_summary}]")

# Summary
print()
print("=" * 90)
print("RESULTS")
print("=" * 90)

if signals:
    signals.sort(key=lambda x: x["weighted_score"], reverse=True)
    print(f"\nSIGNALS FOUND: {len(signals)}")
    print(f"{'Symbol':<10} {'Action':<6} {'W.Score':<10} {'Price':<12} {'ATR':<10} {'Vol':<10} {'TFs'}")
    print("-" * 80)
    for sig in signals:
        tf_count = sum(1 for info in sig["details"].values() if info["action"] == sig["action"])
        print(f"{sig['symbol']:<10} {sig['action']:<6} {sig['weighted_score']:<10.2f} {sig['price']:<12.5f} {sig['atr']:<10.6f} {sig['volatility']:<10.4f} {tf_count}/7")

    # Check if any would execute (4+ TFs agree)
    executable = [s for s in signals if sum(1 for info in s["details"].values() if info["action"] == s["action"]) >= CONFIG["min_timeframes_agree"]]
    print(f"\nExecutable (4+ TFs agree): {len(executable)}")
    for sig in executable:
        print(f"  {sig['symbol']}: {sig['action']} with {sum(1 for info in sig['details'].values() if info['action'] == sig['action'])}/7 TFs")
else:
    print("\nNO SIGNALS - All instruments HOLD across all timeframes")

print()
print("Test complete.")
mt5.shutdown()
