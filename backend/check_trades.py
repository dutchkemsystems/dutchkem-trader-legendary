"""Quick trade analysis — reads MT5 deal history"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta

import os
mt5.initialize(
    path=os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"),
    login=476963617,
    password="Christ@5436",
    server="Exness-MT5Trial9"
)
info = mt5.account_info()
print(f"Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f} | Profit: ${info.profit:.2f}")

from_date = datetime.now() - timedelta(days=7)
deals = mt5.history_deals_get(from_date=from_date, to_date=datetime.now())

if not deals:
    print("No deals found in last 7 days")
    mt5.shutdown()
    exit()

# Separate opening deals from closing deals
openings = [d for d in deals if d.entry == 1]  # IN deals (opens)
closings = [d for d in deals if d.entry == 0]  # OUT deals (closes)

print(f"\n=== DEALS (last 7 days) ===")
print(f"Open deals: {len(openings)} | Close deals: {len(closings)}")

# Analyze closing deals for P&L
wins = 0
losses = 0
total_win = 0.0
total_loss = 0.0
trades = []

for d in closings:
    pnl = d.profit + d.swap + d.commission
    if d.profit > 0:
        wins += 1
        total_win += pnl
    elif d.profit < 0:
        losses += 1
        total_loss += pnl
    else:
        # breakeven - count as loss for WR
        losses += 1
        total_loss += pnl
    
    direction = "BUY" if d.type == 0 else "SELL"
    trades.append({
        "symbol": d.symbol,
        "direction": direction,
        "volume": d.volume,
        "profit": d.profit,
        "swap": d.swap,
        "commission": d.commission,
        "net": pnl,
        "ticket": d.ticket,
        "time": datetime.fromtimestamp(d.time).strftime("%m-%d %H:%M"),
    })

print(f"\n{'Symbol':8} {'Dir':4} {'Lots':5} {'Profit':>8} {'Swap':>6} {'Comm':>6} {'Net':>8} {'Time'}")
print("-" * 70)
for t in trades:
    net_color = "+" if t["net"] >= 0 else ""
    print(f"{t['symbol']:8} {t['direction']:4} {t['volume']:5.2f} ${t['profit']:+7.2f} ${t['swap']:5.2f} ${t['commission']:5.2f} {net_color}${t['net']:6.2f} {t['time']}")

total = wins + losses
wr = wins / total * 100 if total > 0 else 0
net = total_win + total_loss

print(f"\n=== SUMMARY ===")
print(f"Trades: {total} | Wins: {wins} | Losses: {losses}")
print(f"Win Rate: {wr:.0f}%")
print(f"Total Wins:  ${total_win:+.2f}")
print(f"Total Losses: ${total_loss:+.2f}")
print(f"Net P&L: ${net:+.2f}")
if total_loss != 0:
    pf = total_win / abs(total_loss) if total_loss != 0 else float("inf")
    print(f"Profit Factor: {pf:.2f}")
if wins > 0:
    print(f"Avg Win: ${total_win/wins:.2f}")
if losses > 0:
    print(f"Avg Loss: ${total_loss/losses:.2f}")

# Per-symbol breakdown
print(f"\n=== BY SYMBOL ===")
symbol_stats = {}
for t in trades:
    sym = t["symbol"]
    if sym not in symbol_stats:
        symbol_stats[sym] = {"wins": 0, "losses": 0, "net": 0, "count": 0}
    symbol_stats[sym]["count"] += 1
    symbol_stats[sym]["net"] += t["net"]
    if t["net"] > 0:
        symbol_stats[sym]["wins"] += 1
    else:
        symbol_stats[sym]["losses"] += 1

for sym, stats in sorted(symbol_stats.items(), key=lambda x: x[1]["net"]):
    sw = stats["wins"]
    sl = stats["losses"]
    swr = sw / (sw + sl) * 100 if (sw + sl) > 0 else 0
    print(f"  {sym:8} {stats['count']} trades | WR={swr:.0f}% | Net=${stats['net']:+.2f}")

# Also check open positions
positions = mt5.positions_get()
if positions:
    print(f"\n=== OPEN POSITIONS ({len(positions)}) ===")
    for p in positions:
        direction = "BUY" if p.type == 0 else "SELL"
        print(f"  {p.symbol:8} {direction:4} lots={p.volume:.2f} entry={p.price_open:.5f} current={p.price_current:.5f} profit=${p.profit:+.2f}")

mt5.shutdown()
