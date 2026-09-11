import os
"""Get all available symbols from MT5."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

if not mt5.initialize(path=MT5_PATH, login=int(os.environ.get("MT5_LOGIN", "0")), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", "")):
    print(f"FAILED: {mt5.last_error()}")
    sys.exit(1)

info = mt5.account_info()
print(f"Connected: {info.login} | {info.server} | ${info.balance}")

symbols = mt5.symbols_get()
print(f"\nTotal symbols: {len(symbols)}")

# Group by type
forex_majors = []
forex_crosses = []
metals = []
crypto = []
indices = []
other = []

for s in symbols:
    name = s.name
    if not s.visible:
        continue
    if "XAU" in name or "XAG" in name or "GOLD" in name or "SILVER" in name:
        metals.append(name)
    elif "BTC" in name or "ETH" in name or "SOL" in name or "DOG" in name:
        crypto.append(name)
    elif "JP50" in name or "US30" in name or "US500" in name or "NAS" in name or "SPX" in name or "DAX" in name or "GER" in name or "UK100" in name or "EUGERMANY" in name:
        indices.append(name)
    elif any(x in name for x in ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]):
        # Count how many major currencies
        majors = sum(1 for m in ["EUR", "GBP", "USD", "JPY"] if m in name)
        if majors >= 2:
            if "JPY" in name and ("EUR" in name or "GBP" in name or "AUD" in name or "NZD" in name or "CAD" in name or "CHF" in name):
                forex_crosses.append(name)
            elif ("EUR" in name and "GBP" in name) or ("EUR" in name and "CHF" in name) or ("GBP" in name and "CHF" in name):
                forex_crosses.append(name)
            else:
                forex_majors.append(name)
        else:
            forex_crosses.append(name)
    else:
        other.append(name)

print(f"\n--- FOREX MAJORS ({len(forex_majors)}) ---")
for s in sorted(forex_majors):
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

print(f"\n--- FOREX CROSSES ({len(forex_crosses)}) ---")
for s in sorted(forex_crosses):
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

print(f"\n--- METALS ({len(metals)}) ---")
for s in sorted(metals):
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

print(f"\n--- CRYPTO ({len(crypto)}) ---")
for s in sorted(crypto):
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

print(f"\n--- INDICES ({len(indices)}) ---")
for s in sorted(indices):
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

print(f"\n--- OTHER ({len(other)}) ---")
for s in sorted(other)[:20]:
    tick = mt5.symbol_info_tick(s)
    spread = (tick.ask - tick.bid) if tick else 0
    print(f"  {s:12} spread={spread:.5f}")

mt5.shutdown()
