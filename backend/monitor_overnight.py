"""
Overnight Trade Monitor
=======================
Watches unified_engine.log for trade events and errors.
Optionally sends Telegram alerts.

Usage:
  python monitor_overnight.py                    # Console only
  python monitor_overnight.py --telegram         # Console + Telegram
  python monitor_overnight.py --telegram --chat_id=XXX --bot_token=XXX

Set environment variables for Telegram:
  TELEGRAM_BOT_TOKEN=your_bot_token
  TELEGRAM_CHAT_ID=your_chat_id
"""

import os
import sys
import time
import json
import re
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent / "unified_engine.log"

# Patterns to watch for
TRADE_OPENED = re.compile(r"EXECUTED\s+(\w+)\s+(BUY|SELL)\s+@\s+([\d.]+)\s+lots=([\d.]+)\s+SL=([\d.]+)\s+TP=([\d.]+)\s+profile=(\w+)\s+ticket=(\d+)")
TRADE_FAILED = re.compile(r"FAILED\s+(\w+)\s*—?\s*(.*)")
TRADE_CLOSED = re.compile(r"CLOSED\s+(\w+)\s+(WIN|LOSS|BE)\s+profit=([+-]?[\d.]+)")
ORDER_FAILED = re.compile(r"order not placed|MT5 rejected|market closed")
ERROR_LINE = re.compile(r"\[ERROR\]|CRITICAL|Traceback|Exception")
ANALYST_CONSENSUS = re.compile(r"ANALYSTS\s+\[(\d+)\]\s+consensus=(\w+)\s+agreement=(\d+)%")
SIGNAL_PASSED = re.compile(r"SIGNAL\s+(\w+)\s+(BUY|SELL)\s+\|\s+Score=([\d.]+)")
SKIP_SYMBOL = re.compile(r"SKIP\s+(\w+)\s*—?\s*(.*)")

# Stats
stats = {
    "started": datetime.now(timezone.utc).isoformat(),
    "trades_opened": 0,
    "trades_failed": 0,
    "trades_closed": 0,
    "errors": 0,
    "signals_passed": 0,
    "symbols_skipped": {},
    "cycle_count": 0,
    "alerts_sent": 0,
}


def send_telegram(message: str, bot_token: str, chat_id: str) -> bool:
    """Send a Telegram message."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  [Telegram Error] {e}")
        return False


def format_trade_alert(match) -> str:
    """Format a trade execution alert."""
    symbol, direction, price, lots, sl, tp, profile, ticket = match.groups()
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return (
        f"🟢 <b>TRADE OPENED</b>\n"
        f"Symbol: <code>{symbol}</code>\n"
        f"Direction: <b>{direction}</b>\n"
        f"Entry: <code>{price}</code>\n"
        f"Lots: <code>{lots}</code>\n"
        f"SL: <code>{sl}</code> | TP: <code>{tp}</code>\n"
        f"Profile: {profile}\n"
        f"Ticket: <code>{ticket}</code>\n"
        f"Time: {now}"
    )


def format_close_alert(match) -> str:
    """Format a trade close alert."""
    symbol, result, profit = match.groups()
    emoji = "💰" if result == "WIN" else "💸" if result == "LOSS" else "➖"
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return (
        f"{emoji} <b>TRADE CLOSED — {result}</b>\n"
        f"Symbol: <code>{symbol}</code>\n"
        f"Profit: <code>${profit}</code>\n"
        f"Time: {now}"
    )


def format_error_alert(msg: str) -> str:
    """Format an error alert."""
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return f"🔴 <b>ERROR</b>\n<code>{msg[:500]}</code>\nTime: {now}"


def format_summary() -> str:
    """Format a periodic summary."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"📊 <b>OVERNIGHT SUMMARY</b>\n"
        f"Since: {stats['started'][:19]}\n"
        f"Trades opened: {stats['trades_opened']}\n"
        f"Trades closed: {stats['trades_closed']}\n"
        f"Signals passed: {stats['signals_passed']}\n"
        f"Errors: {stats['errors']}\n"
        f"Alerts sent: {stats['alerts_sent']}\n"
        f"Time: {now}"
    )


def main():
    parser = argparse.ArgumentParser(description="Overnight Trade Monitor")
    parser.add_argument("--telegram", action="store_true", help="Enable Telegram alerts")
    parser.add_argument("--chat_id", type=str, default=os.environ.get("TELEGRAM_CHAT_ID", ""))
    parser.add_argument("--bot_token", type=str, default=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    parser.add_argument("--summary_interval", type=int, default=3600, help="Summary interval in seconds (default: 3600)")
    args = parser.parse_args()

    telegram_enabled = args.telegram and args.bot_token and args.chat_id

    print("=" * 60)
    print("  OVERNIGHT TRADE MONITOR")
    print(f"  Log: {LOG_FILE}")
    print(f"  Telegram: {'ENABLED' if telegram_enabled else 'DISABLED'}")
    print(f"  Started: {stats['started']}")
    print("=" * 60)

    if telegram_enabled:
        send_telegram(
            f"🚀 <b>Monitor Started</b>\nTime: {stats['started'][:19]}\nWatching: <code>unified_engine.log</code>",
            args.bot_token,
            args.chat_id,
        )
        stats["alerts_sent"] += 1

    # Track last file size for new content detection
    last_size = 0
    last_summary_time = time.time()

    while True:
        try:
            if not LOG_FILE.exists():
                time.sleep(5)
                continue

            current_size = LOG_FILE.stat().st_size

            # File was rotated or truncated
            if current_size < last_size:
                last_size = 0

            # New content available
            if current_size > last_size:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_size)
                    new_lines = f.readlines()
                    last_size = current_size

                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue

                        # Check for trade execution
                        m = TRADE_OPENED.search(line)
                        if m:
                            stats["trades_opened"] += 1
                            alert = format_trade_alert(m)
                            print(f"\n{'='*50}")
                            print(alert.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
                            print(f"{'='*50}")
                            if telegram_enabled:
                                send_telegram(alert, args.bot_token, args.chat_id)
                                stats["alerts_sent"] += 1
                            continue

                        # Check for trade close
                        m = TRADE_CLOSED.search(line)
                        if m:
                            stats["trades_closed"] += 1
                            alert = format_close_alert(m)
                            print(f"\n{'='*50}")
                            print(alert.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
                            print(f"{'='*50}")
                            if telegram_enabled:
                                send_telegram(alert, args.bot_token, args.chat_id)
                                stats["alerts_sent"] += 1
                            continue

                        # Check for failed trade
                        if TRADE_FAILED.search(line) or ORDER_FAILED.search(line):
                            stats["trades_failed"] += 1
                            print(f"  ⚠️  {line[-120:]}")
                            continue

                        # Check for signal passing V3 gate
                        m = SIGNAL_PASSED.search(line)
                        if m:
                            stats["signals_passed"] += 1
                            sym, dir, score = m.groups()
                            print(f"  📡 Signal: {sym} {dir} Score={score}")
                            continue

                        # Check for errors
                        if ERROR_LINE.search(line):
                            stats["errors"] += 1
                            alert = format_error_alert(line[-500:])
                            print(f"\n  🔴 ERROR: {line[-120:]}")
                            if telegram_enabled and stats["errors"] <= 5:  # Limit error spam
                                send_telegram(alert, args.bot_token, args.chat_id)
                                stats["alerts_sent"] += 1
                            continue

                        # Check for analyst consensus
                        m = ANALYST_CONSENSUS.search(line)
                        if m:
                            count, consensus, agreement = m.groups()
                            print(f"  🧠 Analysts [{count}] consensus={consensus} agreement={agreement}%")
                            continue

                        # Check for skipped symbols
                        m = SKIP_SYMBOL.search(line)
                        if m:
                            sym, reason = m.groups()
                            stats["symbols_skipped"][sym] = reason
                            continue

                        # Print important lines
                        if any(kw in line for kw in ["SIGNAL", "EXECUTED", "CLOSED", "SUMMARY", "DAILY", "ERROR"]):
                            # Trim to readable length
                            print(f"  {line[-150:]}")

            # Periodic summary
            now = time.time()
            if now - last_summary_time >= args.summary_interval:
                summary = format_summary()
                print(f"\n{'='*50}")
                print(summary.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
                print(f"{'='*50}")
                if telegram_enabled:
                    send_telegram(summary, args.bot_token, args.chat_id)
                    stats["alerts_sent"] += 1
                last_summary_time = now

            time.sleep(2)  # Poll every 2 seconds

        except KeyboardInterrupt:
            print("\n\nMonitor stopped by user")
            if telegram_enabled:
                final = format_summary()
                send_telegram(f"⏹ <b>Monitor Stopped</b>\n\n{final}", args.bot_token, args.chat_id)
            break
        except Exception as e:
            print(f"  [Monitor Error] {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
