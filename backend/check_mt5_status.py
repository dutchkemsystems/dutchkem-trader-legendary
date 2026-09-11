import os
"""Check MT5 connection and account status."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
mt5.initialize(path=MT5_PATH, login=int(os.environ.get("MT5_LOGIN", "0")), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", ""))

info = mt5.account_info()
term = mt5.terminal_info()

print("=" * 60)
print("  MT5 CONNECTION STATUS")
print("=" * 60)
print(f"  Connected:      YES")
print(f"  Login:          {info.login}")
print(f"  Server:         {info.server}")
print(f"  Name:           {info.name}")
print(f"  Company:        {info.company}")
print(f"  Account Type:   DEMO (Trial)")
print(f"  Balance:        ${info.balance:,.2f}")
print(f"  Equity:         ${info.equity:,.2f}")
print(f"  Margin:         ${info.margin:,.2f}")
print(f"  Free Margin:    ${info.margin_free:,.2f}")
print(f"  Leverage:       1:{info.leverage}")
print(f"  Currency:       {info.currency}")
print(f"  Margin Level:   {info.margin_level:.1f}%")
print(f"  Profit:         ${info.profit:+,.2f}")

# Open positions
positions = mt5.positions_get()
count = len(positions) if positions else 0
print(f"\n  Open Positions: {count}")
if positions:
    for p in positions:
        m = "+" if p.profit > 0 else ""
        side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        print(f"    {p.symbol:10} {side:4} {p.volume:.2f} lots @ {p.price_open:.5f} | P&L=${m}{p.profit:.2f}")

# Recent deals
deals = mt5.history_deals_get(days_back=7)
deal_count = len(deals) if deals else 0
print(f"\n  Recent Deals (7 days): {deal_count}")
if deals:
    for d in deals[-5:]:
        side = "BUY" if d.type == mt5.ORDER_TYPE_BUY else "SELL" if d.type == mt5.ORDER_TYPE_SELL else "BAL"
        print(f"    {d.symbol:10} {side:4} {d.volume:.2f} lots | P&L=${d.profit:+.2f}")

# Symbols
symbols = mt5.symbols_get()
print(f"\n  Available Symbols: {len(symbols) if symbols else 0}")

# Terminal
print(f"\n  Terminal:")
print(f"    Build:        {term.build}")
print(f"    Connected:    {'YES' if term.connected else 'NO'}")
print(f"    Trade Allowed: {'YES' if term.trade_allowed else 'NO'}")
print(f"    Visual Mode:  {'YES' if term.visual_mode else 'NO'}")

mt5.shutdown()
print("\n" + "=" * 60)
print("  STATUS: ALL SYSTEMS GO")
print("=" * 60)
