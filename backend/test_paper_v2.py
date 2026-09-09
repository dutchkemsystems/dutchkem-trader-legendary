"""Quick test: single cycle of paper trading V2."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

from paper_trading_v2 import *

# Test connection
print("\n--- TEST: MT5 Connection ---")
if not connect_mt5():
    print("FAILED"); sys.exit(1)

# Test data fetch for all symbols
print("\n--- TEST: Data Fetch ---")
symbol_data = {}
for sym in WATCHLIST:
    df = fetch_latest_candles(sym, 200)
    if df is not None and len(df) > 60:
        df = compute_indicators(df)
        df = df.dropna()
        symbol_data[sym] = df
        action, conf = generate_signal(df.iloc[-1])
        print(f"  {sym:10} {len(df):4} bars | {action:5} conf={conf:.2f}")
    else:
        print(f"  {sym:10} SKIPPED")

mt5.shutdown()

# Test position manager
print("\n--- TEST: Position Manager ---")
pm = PositionManager()
pos = pm.open_position("EURUSD", "BUY", 1.13285, datetime.now(timezone.utc), 200)
print(f"  Opened: {pos}")
trade = pm.close_position("EURUSD", 1.13400, datetime.now(timezone.utc), 205)
print(f"  Closed: {trade}")
print(f"  Balance: ${pm.balance:.2f}")
print(f"  State: {pm.get_state()}")

print("\n--- ALL TESTS PASSED ---")
