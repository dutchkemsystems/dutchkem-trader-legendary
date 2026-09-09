"""Test multi-timeframe trading engine."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
import MetaTrader5 as mt5
from live_trading_mtf import connect_mt5, generate_multitimeframe_signal, WATCHLIST, TIMEFRAMES

print("Testing Multi-Timeframe Trading Engine...")
print(f"Timeframes: {', '.join(TIMEFRAMES.keys())}")
print()

if not connect_mt5():
    print("FAILED: Cannot connect to MT5")
    sys.exit(1)

# Test EURUSD across all timeframes
print("=" * 70)
print("EURUSD - Multi-Timeframe Analysis")
print("=" * 70)

action, score, details = generate_multitimeframe_signal("EURUSD")

print(f"\nFINAL: {action} (score={score:.2f})")
print("\nTimeframe Breakdown:")
print("-" * 70)
print(f"{'TF':<6} {'Action':<8} {'Score':<8} {'Conf':<8} {'Price':<12} {'RSI':<8}")
print("-" * 70)

for tf, info in details.items():
    score_str = f"{info['score']:+d}"
    print(f"{tf:<6} {info['action']:<8} {score_str:<8} {info['confidence']:.2f}   {info['price']:<12.5f} {info['rsi']:.1f}")

# Check agreement
buy_count = sum(1 for info in details.values() if info["action"] == "BUY")
sell_count = sum(1 for info in details.values() if info["action"] == "SELL")
hold_count = sum(1 for info in details.values() if info["action"] == "HOLD")

print("-" * 70)
print(f"Agreement: BUY={buy_count} | SELL={sell_count} | HOLD={hold_count}")

# Test a few more symbols
print("\n\nTop 5 Signals Across All Symbols:")
print("=" * 70)

signals = []
for sym in WATCHLIST[:10]:  # Test first 10
    action, score, details = generate_multitimeframe_signal(sym)
    if action != "HOLD":
        signals.append((sym, action, score, details))

signals.sort(key=lambda x: x[2], reverse=True)

for sym, action, score, details in signals[:5]:
    buy_tfs = [tf for tf, info in details.items() if info["action"] == "BUY"]
    sell_tfs = [tf for tf, info in details.items() if info["action"] == "SELL"]
    print(f"{sym}: {action} (score={score:.2f})")
    print(f"  BUY TFs: {', '.join(buy_tfs) if buy_tfs else 'None'}")
    print(f"  SELL TFs: {', '.join(sell_tfs) if sell_tfs else 'None'}")

print("\nTest complete. Ready for multi-timeframe live trading.")
mt5.shutdown()
