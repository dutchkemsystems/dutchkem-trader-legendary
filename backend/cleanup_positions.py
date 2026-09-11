import os
"""Close all open MT5 positions — cleanup script."""
import MetaTrader5 as mt5

mt5.initialize(
    path=r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    login=int(os.environ.get("MT5_LOGIN", "0")),
    password=os.environ.get("MT5_PASSWORD", ""),
    server=os.environ.get("MT5_SERVER", ""),
)

positions = mt5.positions_get()
if not positions:
    print("No positions to close")
else:
    for p in positions:
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        close_price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "price": close_price,
            "deviation": 20,
            "magic": 234000,
            "comment": "cleanup_close",
        }
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"Closed {p.symbol} {p.volume} lots")
        else:
            msg = result.comment if result else "error"
            print(f"Failed {p.symbol}: {msg}")

info = mt5.account_info()
print(f"Balance after close: ${info.balance:,.2f}")
mt5.shutdown()
