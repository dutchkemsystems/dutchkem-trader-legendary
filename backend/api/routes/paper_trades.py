"""Paper Trading API routes."""
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()
PAPER_TRADES_DIR = Path("paper_trades")


@router.get("/paper-trades")
async def list_paper_trades():
    """List all paper trades from today."""
    if not PAPER_TRADES_DIR.exists():
        return {"trades": [], "count": 0}

    today = datetime.now().strftime("%Y%m%d")
    filename = PAPER_TRADES_DIR / f"trades_{today}.jsonl"

    if not filename.exists():
        return {"trades": [], "count": 0}

    trades = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))

    return {"trades": trades, "count": len(trades)}


@router.get("/paper-trades/{date}")
async def list_paper_trades_by_date(date: str):
    """List paper trades for a specific date (YYYYMMDD)."""
    if not PAPER_TRADES_DIR.exists():
        return {"trades": [], "count": 0}

    filename = PAPER_TRADES_DIR / f"trades_{date}.jsonl"
    if not filename.exists():
        return {"trades": [], "count": 0}

    trades = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))

    return {"trades": trades, "count": len(trades)}


@router.get("/paper-trades/stats")
async def paper_trades_stats():
    """Get paper trading statistics."""
    if not PAPER_TRADES_DIR.exists():
        return {"total_trades": 0, "win_rate": 0, "symbols": {}}

    all_trades = []
    for filename in sorted(PAPER_TRADES_DIR.glob("trades_*.jsonl")):
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_trades.append(json.loads(line))

    if not all_trades:
        return {"total_trades": 0, "win_rate": 0, "symbols": {}}

    # Stats by symbol
    symbols = {}
    for t in all_trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in symbols:
            symbols[sym] = {"buy": 0, "sell": 0, "hold": 0, "blocked": 0}
        action = t.get("action", "HOLD")
        if action in symbols[sym]:
            symbols[sym][action] += 1
        if not t.get("gates", {}).get("trade_allowed", True):
            symbols[sym]["blocked"] += 1

    total = len(all_trades)
    buys = sum(1 for t in all_trades if t.get("action") == "BUY")
    sells = sum(1 for t in all_trades if t.get("action") == "SELL")
    holds = sum(1 for t in all_trades if t.get("action") == "HOLD")

    return {
        "total_trades": total,
        "buys": buys,
        "sells": sells,
        "holds": holds,
        "symbols": symbols,
        "last_trade": all_trades[-1] if all_trades else None,
    }
