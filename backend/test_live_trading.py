"""Test live trading engine - one cycle."""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
import MetaTrader5 as mt5
from live_trading import connect_mt5, fetch_latest_candles, compute_indicators, generate_signal, MT5Trader, WATCHLIST, CONFIG

print("Testing live trading engine...")
print()

# Connect
if not connect_mt5():
    print("FAILED: Cannot connect to MT5")
    sys.exit(1)

# Get account info
info = mt5.account_info()
print(f"Account: {info.login} | Balance: ${info.balance:,.2f}")
print()

# Create trader
trader = MT5Trader()
trader.balance = info.balance

# Test signal generation for EURUSD
print("Testing signal generation...")
df = fetch_latest_candles("EURUSD", 200)
if df is not None and len(df) > 60:
    df = compute_indicators(df)
    df = df.dropna()
    latest = df.iloc[-1]
    action, confidence = generate_signal(latest)
    print(f"EURUSD: {action} (confidence={confidence:.2f})")
    print(f"  Price: {latest['close']:.5f}")
    print(f"  MACD: {latest['macd_hist']:.6f}")
    print(f"  RSI: {latest['rsi']:.1f}")
    print(f"  Volatility: {latest['volatility_10']:.4f}")
    
    # Calculate lot size
    lots = trader.get_lot_size("EURUSD", latest["close"], latest["volatility_10"])
    print(f"  Calculated lots: {lots:.2f}")
else:
    print("FAILED: Cannot fetch EURUSD data")

print()
print("Test complete. Ready for live trading.")
mt5.shutdown()
