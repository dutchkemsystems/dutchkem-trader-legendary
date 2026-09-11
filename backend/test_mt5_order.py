import os
"""
Manual MT5 Order Test
=====================
Tests: BUY order, SELL order, close position.
Uses the MT5Connector from the execution module.
"""
import os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()

import MetaTrader5 as mt5
from decimal import Decimal
from execution.mt5_connector import MT5Connector
from execution.broker import BrokerOrder, OrderSide, OrderType

MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

def main():
    print("=" * 60)
    print("  MANUAL MT5 ORDER TEST")
    print("=" * 60)

    # 1. Initialize MT5 directly
    print("\n[1] Connecting to MT5...")
    if not mt5.initialize(path=MT5_PATH, login=int(os.environ.get("MT5_LOGIN", "0")), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", "")):
        print(f"  FAILED: {mt5.last_error()}")
        return

    info = mt5.account_info()
    print(f"  Connected: {info.login} | {info.server}")
    print(f"  Balance: ${info.balance:,.2f}")
    print(f"  Free Margin: ${info.margin_free:,.2f}")

    # 2. Check symbol info
    print("\n[2] Checking EURUSD symbol...")
    symbol_info = mt5.symbol_info("EURUSD")
    if symbol_info is None:
        print("  FAILED: EURUSD not found")
        mt5.shutdown()
        return
    print(f"  EURUSD: {symbol_info.name} | Spread: {symbol_info.spread} | Digits: {symbol_info.digits}")
    print(f"  Trade Mode: {symbol_info.trade_mode}")
    print(f"  Volume Min: {symbol_info.volume_min} | Max: {symbol_info.volume_max} | Step: {symbol_info.volume_step}")

    # 3. Get current price
    print("\n[3] Current prices...")
    tick = mt5.symbol_info_tick("EURUSD")
    if tick is None:
        print("  FAILED: Cannot get tick")
        mt5.shutdown()
        return
    print(f"  Bid: {tick.bid:.5f} | Ask: {tick.ask:.5f}")
    print(f"  Spread: {(tick.ask - tick.bid) * 10000:.1f} pips")

    # 4. Test BUY order (0.01 lot)
    print("\n[4] Placing BUY order (EURUSD, 0.01 lot)...")
    buy_order = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": "EURUSD",
        "volume": 0.01,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "deviation": 20,
        "magic": 234000,
        "comment": "dutchkem_test",
    }
    result = mt5.order_send(buy_order)
    if result is None:
        print("  FAILED: order_send returned None")
        mt5.shutdown()
        return
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  FAILED: {result.comment} (code={result.retcode})")
        mt5.shutdown()
        return
    print(f"  SUCCESS! Order #{result.order}")
    print(f"  Fill Price: {result.price:.5f}")
    print(f"  Volume: {result.volume}")

    # 5. Check open position
    print("\n[5] Checking open positions...")
    positions = mt5.positions_get()
    print(f"  Open positions: {len(positions)}")
    for p in positions:
        side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        print(f"    #{p.ticket} {p.symbol} {side} {p.volume:.2f} lots @ {p.price_open:.5f}")
        print(f"    P&L: ${p.profit:+.2f} | Swap: ${p.swap:.2f}")

    # 6. Close the position
    if positions and len(positions) > 0:
        pos = positions[0]
        print(f"\n[6] Closing position #{pos.ticket}...")
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        close_order = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": 20,
            "magic": 234000,
            "comment": "dutchkem_close",
        }
        result = mt5.order_send(close_order)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            print(f"  FAILED: {err}")
        else:
            print(f"  SUCCESS! Closed at {result.price:.5f}")

    # 7. Final account state
    print("\n[7] Final account state...")
    info = mt5.account_info()
    print(f"  Balance: ${info.balance:,.2f}")
    print(f"  Equity: ${info.equity:,.2f}")
    print(f"  Profit: ${info.profit:+.2f}")

    # 8. Check deal history
    print("\n[8] Recent deals...")
    deals = mt5.history_deals_get(days_back=1)
    if deals:
        for d in deals[-5:]:
            side = "BUY" if d.type == mt5.ORDER_TYPE_BUY else "SELL" if d.type == mt5.ORDER_TYPE_SELL else "BAL"
            print(f"    {d.symbol} {side} {d.volume:.2f} lots @ {d.price:.5f} | P&L=${d.profit:+.2f}")
    else:
        print("  No deals found")

    mt5.shutdown()
    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
